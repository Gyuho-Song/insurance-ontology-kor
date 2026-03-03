import asyncio
import json
import logging
import re
import time
import uuid
from collections import deque
from dataclasses import dataclass, field

from app.clients.opensearch_client import OpenSearchClient
from app.config import settings
from app.core.answer_generator import AnswerGenerator
from app.core.glossary_expander import GlossaryExpander
from app.core.hallucination_validator import HallucinationValidator
from app.core.hybrid_scorer import HybridScorer
from app.core.intent_classifier import IntentClassifier
from app.core.template_router import TEMPLATE_POOL, TemplateRouter
from app.core.traversal_engine import DELAY_MAP, TraversalEngine
from app.middleware.rbac import filter_subgraph
from app.models.intent import IntentType
from app.models.mydata import MergeContext
from app.models.response import ChatRequest, SourceReference
from app.services.mydata_service import MyDataService

logger = logging.getLogger("graphrag.orchestrator")

# ── Security: Input Sanitization Patterns ──────────────────────────────
_GREMLIN_INJECTION_RE = re.compile(
    r"""
      \.drop\s*\(             # .drop()
    | \.addV\s*\(             # .addV()
    | \.addE\s*\(             # .addE()
    | \.property\s*\(         # .property()
    | \.sideEffect\s*\(       # .sideEffect()
    | g\s*\.\s*V\s*\(         # g.V()
    | g\s*\.\s*E\s*\(         # g.E()
    | \.bothE\s*\(            # .bothE()
    | \.outE\s*\(             # .outE()
    | \.inE\s*\(              # .inE()
    """,
    re.VERBOSE | re.IGNORECASE,
)

_PROMPT_INJECTION_RE = re.compile(
    r"""
      ignore\s+(all\s+)?(previous|above|prior)\s+(instructions?|rules?|prompts?)
    | forget\s+(all\s+)?(previous|your)\s+(instructions?|rules?)
    | you\s+are\s+(now|a)\s+
    | (act|behave|respond)\s+as\s+(if\s+you\s+are|a)\s+
    | (system|시스템)\s*(prompt|프롬프트|역할|role)
    | (disregard|override|bypass)\s+(the\s+)?(system|rules?|instructions?)
    | (reveal|show|print|output)\s+(your\s+)?(system\s+)?(prompt|instructions?)
    | 이전\s*(지시|명령|규칙).*무시
    | (역할|모드)\s*(변경|바꿔|전환)
    """,
    re.VERBOSE | re.IGNORECASE,
)

_SECURITY_RESPONSE = (
    "해당 질문은 보험 약관 상담 범위를 벗어나는 것으로 판단됩니다.\n\n"
    "보험상품의 보장 내용, 면책 사유, 해약환급금, 배당, 특약 등 "
    "약관 관련 질문을 해주시면 도움을 드리겠습니다."
)


@dataclass
class PipelineResult:
    answer_text: str = ""
    intent: str | None = None
    confidence: float | None = None
    sources: list[dict] = field(default_factory=list)
    traversal_events: list[dict] = field(default_factory=list)
    subgraph: dict = field(default_factory=lambda: {"nodes": [], "edges": []})
    templates_used: list[str] = field(default_factory=list)
    topo_faithfulness: float | None = None
    validation_status: str = "completed"


class Orchestrator:
    def __init__(self, neptune, opensearch, bedrock, embedding):
        self._neptune = neptune
        self._opensearch = opensearch
        self._bedrock = bedrock
        self._embedding = embedding

        self._classifier = IntentClassifier(bedrock=bedrock, embedding_client=embedding)
        self._glossary = GlossaryExpander()
        self._router = TemplateRouter()
        self._traversal = TraversalEngine(neptune=neptune)
        self._scorer = HybridScorer()
        self._generator = AnswerGenerator(bedrock=bedrock)
        self._validator = HallucinationValidator(bedrock=bedrock)

    async def run(self, request: ChatRequest) -> PipelineResult:
        """Non-streaming pipeline — collects full result. Used by mock endpoint."""
        answer_text = ""
        annotation: dict = {}
        async for event_type, data in self.run_stream(request):
            if event_type == "text":
                answer_text += data
            elif event_type == "annotation":
                annotation = data
        return PipelineResult(
            answer_text=answer_text,
            intent=annotation.get("intent"),
            confidence=annotation.get("confidence"),
            sources=annotation.get("sources", []),
            traversal_events=annotation.get("traversalEvents", []),
            subgraph=annotation.get("subgraph", {"nodes": [], "edges": []}),
            templates_used=annotation.get("templatesUsed", []),
            topo_faithfulness=annotation.get("topoFaithfulness"),
            validation_status=annotation.get("validationStatus", "completed"),
        )

    # Intent type → Korean label mapping for pipeline explorer
    _INTENT_LABELS: dict[str, str] = {
        "coverage_inquiry": "보장 내용 조회",
        "dividend_check": "배당 조회",
        "exclusion_exception": "면책/예외 사항",
        "surrender_value": "해약환급금",
        "discount_eligibility": "할인/우대",
        "regulation_inquiry": "규제/법률 조회",
        "loan_inquiry": "대출 조회",
        "premium_waiver": "납입면제",
        "policy_comparison": "상품 비교",
        "calculation_inquiry": "계산 방법",
        "eligibility_inquiry": "가입 조건",
        "rider_inquiry": "특약 조회",
        "general_inquiry": "일반 문의",
    }

    async def _run_shared_stages(self, query: str):
        """Stages 1-4: shared between GraphRAG and Naive RAG."""
        timings: dict = {}
        search_meta: dict = {}

        # Stage 1: Glossary Expansion
        t0 = time.monotonic()
        expanded = self._glossary.expand(query)
        timings["glossary_ms"] = int((time.monotonic() - t0) * 1000)

        # Stage 2: Embedding (computed early for intent + vector search reuse)
        t0 = time.monotonic()
        query_vector = await self._embedding.embed(expanded.embedding_text)
        timings["embedding_ms"] = int((time.monotonic() - t0) * 1000)

        # Stage 3: Intent Classification (with embedding support)
        t0 = time.monotonic()
        intent = await self._classifier.classify(query, query_vector=query_vector)
        timings["intent_ms"] = int((time.monotonic() - t0) * 1000)

        # Stage 4: Hybrid Vector Search (3-branch)
        # Branch A: product_name entities found → entity-resolved Policy + k-NN
        # Branch B: topic-based query (no product) → BM25 + k-NN RRF fusion
        # Branch C: general query → pure k-NN (legacy)
        t0 = time.monotonic()
        try:
            product_entities = [e for e in intent.entities if e.type == "product_name"]

            if product_entities:
                # ── Branch A: product name explicit → document-filtered k-NN ──
                search_meta["branch"] = "A"
                search_meta["branch_reason"] = (
                    f"product_name '{product_entities[0].value}' 엔티티 추출됨"
                )
                # Step 1: Resolve product names to exact Policy + document_ids
                resolved_policies: list[dict] = []
                resolved_doc_ids: list[str] = []
                for entity in product_entities[:2]:
                    try:
                        matches = await self._opensearch.resolve_product_policy(
                            entity.value, k=1
                        )
                        if matches:
                            resolved_policies.append(matches[0])
                            doc_id = matches[0].get("document_id", "")
                            if doc_id:
                                resolved_doc_ids.append(doc_id)
                    except Exception as ex:
                        logger.warning(f"Product name resolution failed for '{entity.value}': {ex}")

                # Step 2: k-NN with document_id pre-filter
                if resolved_doc_ids:
                    entry_nodes = await self._opensearch.search_knn(
                        query_vector, k=settings.vector_search_top_k,
                        document_ids=resolved_doc_ids,
                    )
                    # Fallback: filtered < 2 → supplement with unfiltered
                    if len(entry_nodes) < 2:
                        unfiltered = await self._opensearch.search_knn(
                            query_vector, k=settings.vector_search_top_k,
                        )
                        seen = {n["node_id"] for n in entry_nodes}
                        for node in unfiltered:
                            if node["node_id"] not in seen:
                                entry_nodes.append(node)
                                seen.add(node["node_id"])
                else:
                    entry_nodes = await self._opensearch.search_knn(
                        query_vector, k=settings.vector_search_top_k,
                    )

                # Step 3: Ensure resolved Policy is in entry_nodes
                if resolved_policies:
                    resolved_ids = {p["node_id"] for p in resolved_policies}
                    existing_ids = {n["node_id"] for n in entry_nodes}
                    for rp in resolved_policies:
                        if rp["node_id"] not in existing_ids:
                            entry_nodes.insert(0, {
                                "node_id": rp["node_id"],
                                "node_type": rp["node_type"],
                                "node_label": rp["node_label"],
                                "score": 1.0,
                                "text_content": rp.get("text_content", ""),
                                "product_name": rp.get("product_name", ""),
                            })
                    search_meta["policy_resolved"] = list(resolved_ids)[:2]
                    logger.info(
                        f"Branch A filtered: resolved {[e.value for e in product_entities]} → "
                        f"Policy IDs {list(resolved_ids)}, "
                        f"doc_ids={resolved_doc_ids}, "
                        f"entry_nodes={[n['node_id'] for n in entry_nodes[:5]]}"
                    )

            elif intent.type in self.TOPIC_SEARCH_INTENTS:
                # ── Branch B: topic-based query → BM25 + k-NN RRF fusion ──
                search_meta["branch"] = "B"
                search_meta["branch_reason"] = "토픽 기반 검색 (BM25 + k-NN 융합)"
                rrf_pool = 50
                bm25_query = self._extract_bm25_keywords(query)
                knn_results, bm25_results = await asyncio.gather(
                    self._opensearch.search_knn(query_vector, k=rrf_pool),
                    self._opensearch.search_text(bm25_query, k=rrf_pool),
                )
                entry_nodes = OpenSearchClient.reciprocal_rank_fusion(
                    knn_results, bm25_results,
                    top_k=settings.vector_search_top_k,
                )
                logger.info(
                    f"Branch B RRF fusion: intent={intent.type.value}, "
                    f"bm25_query='{bm25_query}', "
                    f"knn={len(knn_results)}, bm25={len(bm25_results)}, "
                    f"fused={[n['node_id'] for n in entry_nodes[:5]]}"
                )

            else:
                # ── Branch C: general query → pure k-NN ──
                search_meta["branch"] = "C"
                search_meta["branch_reason"] = "일반 검색 (순수 k-NN)"
                entry_nodes = await self._opensearch.search_knn(
                    query_vector, k=settings.vector_search_top_k
                )

        except Exception as e:
            logger.warning(f"OpenSearch unavailable, graph-only mode: {e}")
            entry_nodes = []
        timings["vector_ms"] = int((time.monotonic() - t0) * 1000)
        search_meta.setdefault("branch", "C")
        search_meta.setdefault("branch_reason", "")

        return expanded, query_vector, intent, entry_nodes, timings, search_meta

    def _extract_naive_sources(self, entry_nodes: list[dict]) -> list[SourceReference]:
        """Build source references from vector search results only."""
        sources = []
        seen: set[str] = set()
        for node in entry_nodes:
            nid = node["node_id"]
            if nid not in seen:
                seen.add(nid)
                sources.append(SourceReference(
                    node_id=nid,
                    node_type=node.get("node_type", ""),
                    node_label=node.get("node_label", ""),
                    source_article="",
                    source_text=(node.get("text_content", "") or "")[:200],
                ))
        return sources

    @staticmethod
    def _check_input_safety(query: str) -> str | None:
        """Return a blocked reason string if the query contains injection
        patterns, or None if the query is safe."""
        if _GREMLIN_INJECTION_RE.search(query):
            return "gremlin_injection"
        if _PROMPT_INJECTION_RE.search(query):
            return "prompt_injection"
        return None

    async def run_stream(self, request: ChatRequest):
        """Stream pipeline: yield ("text", chunk) during generation,
        then ("annotation", dict) at the end.

        Stages 1-7 run before any output.  Stage 8 (answer generation)
        streams tokens as they arrive from Bedrock.  Stage 9 (validation)
        runs after generation and its result is included in the annotation.
        """
        request_id = str(uuid.uuid4())
        start_time = time.monotonic()
        query = request.messages[-1]["content"]
        rag_mode = request.rag_mode

        # ── Stage 0: Input Safety Check ────────────────────────────────
        blocked_reason = self._check_input_safety(query)
        if blocked_reason:
            logger.warning(
                f"[{request_id}] Input blocked: reason={blocked_reason}, "
                f"query={query[:100]!r}"
            )
            yield ("data", {
                "stage": "security", "status": "blocked",
                "ms": 0,
                "data": {"blocked_reason": blocked_reason},
            })
            yield ("text", _SECURITY_RESPONSE)
            yield ("annotation", {
                "intent": "blocked",
                "confidence": 1.0,
                "sources": [],
                "traversalEvents": [],
                "subgraph": {"nodes": [], "edges": []},
                "topoFaithfulness": None,
                "templatesUsed": [],
                "validationStatus": f"blocked_{blocked_reason}",
            })
            return

        # ── Stages 1-4: Shared (glossary, embedding, intent, vector search)
        expanded, query_vector, intent, entry_nodes, timings, search_meta = \
            await self._run_shared_stages(query)

        # ── Pipeline Explorer: emit stage events for stages 0-4 ──
        yield ("data", {
            "stage": "security", "status": "pass",
            "ms": 0,
            "data": {"checks": ["gremlin_injection", "prompt_injection"]},
        })
        yield ("data", {
            "stage": "understand", "status": "done",
            "ms": timings.get("glossary_ms", 0) + timings.get("embedding_ms", 0),
            "data": {
                "original_query": expanded.original,
                "expanded_query": expanded.expanded,
                "added_synonyms": expanded.synonyms_applied[:5],
                "embedding_model": "Titan V2",
                "embedding_dims": 1024,
            },
        })
        yield ("data", {
            "stage": "classify", "status": "done",
            "ms": timings.get("intent_ms", 0),
            "data": {
                "intent": intent.type.value,
                "intent_label": self._INTENT_LABELS.get(intent.type.value, intent.type.value),
                "confidence": round(intent.confidence, 3),
                "entities": [
                    {"value": e.value, "type": e.type}
                    for e in intent.entities[:3]
                ],
            },
        })
        yield ("data", {
            "stage": "search", "status": "done",
            "ms": timings.get("vector_ms", 0),
            "data": {
                "branch": search_meta.get("branch", "C"),
                "branch_reason": search_meta.get("branch_reason", ""),
                "result_count": len(entry_nodes),
                "top_results": [
                    {
                        "label": n.get("node_label", "")[:40],
                        "type": n.get("node_type", ""),
                        "score": round(n.get("score", 0), 3),
                    }
                    for n in entry_nodes[:5]
                ],
                "policy_resolved": search_meta.get("policy_resolved"),
                "traceback_hops": search_meta.get("traceback_hops"),
            },
        })

        entry_node_ids = [n["node_id"] for n in entry_nodes]
        if not entry_node_ids:
            entry_node_ids = ["Policy#unknown"]

        # ── LOAN INQUIRY EARLY RETURN ─────────────────────────────────
        # HAS_LOAN edges = 0 in Neptune. Instead of querying and getting
        # empty results (risking hallucination), return a clear message.
        if intent.type == IntentType.LOAN_INQUIRY and rag_mode != "naive":
            loan_message = (
                "보험계약대출(약관대출) 관련 정보는 현재 시스템에 포함되어 있지 않습니다.\n\n"
                "약관대출에 대한 자세한 사항은 다음을 통해 확인하실 수 있습니다:\n"
                "- 해당 보험상품의 약관 본문 (대출 관련 조항)\n"
                "- 한화생명 고객센터 (☎ 1588-6363)\n"
                "- 한화생명 다이렉트 인터넷보험 (www.direct.hanwhalife.com)"
            )
            yield ("text", loan_message)
            yield ("annotation", {
                "intent": intent.type.value,
                "confidence": intent.confidence,
                "sources": [],
                "traversalEvents": [],
                "subgraph": {"nodes": [], "edges": []},
                "topoFaithfulness": None,
                "templatesUsed": [],
                "validationStatus": "skipped_no_data",
            })
            return

        # ── NAIVE RAG ONLY MODE ──────────────────────────────────────
        if rag_mode == "naive":
            t0 = time.monotonic()
            naive_answer = await self._generator.generate_naive_rag(entry_nodes, query)
            timings["naive_generation_ms"] = int((time.monotonic() - t0) * 1000)

            yield ("text", naive_answer)

            naive_sources = self._extract_naive_sources(entry_nodes)
            total_ms = int((time.monotonic() - start_time) * 1000)
            logger.info(
                json.dumps({
                    "event": "naive_pipeline_complete",
                    "request_id": request_id,
                    "rag_mode": "naive",
                    "total_ms": total_ms,
                    "timings": timings,
                }, ensure_ascii=False)
            )
            yield ("annotation", {
                "intent": intent.type.value,
                "confidence": intent.confidence,
                "sources": [s.model_dump() for s in naive_sources],
                "traversalEvents": [],
                "subgraph": {"nodes": [], "edges": []},
                "topoFaithfulness": None,
                "templatesUsed": [],
                "validationStatus": "skipped",
            })
            return

        # ── GRAPHRAG PATH (stages 4.5-9) ────────────────────────────

        # Stage 4.5: Policy Node Resolution
        t0 = time.monotonic()
        policy_ids = [nid for nid in entry_node_ids if nid.startswith("Policy#")]
        if not policy_ids and entry_node_ids != ["Policy#unknown"]:
            resolved = await self._resolve_policy_nodes(entry_node_ids)
            if resolved:
                logger.info(
                    f"Resolved {len(resolved)} Policy nodes from "
                    f"{len(entry_node_ids)} non-Policy entry nodes: {resolved[:3]}"
                )
                entry_node_ids = resolved + entry_node_ids
            else:
                # Portfolio fallback: no Policy resolved from entry nodes.
                # Log this — the template router may use portfolio-level
                # templates for generic queries instead.
                logger.info(
                    f"No Policy nodes resolved from {len(entry_node_ids)} "
                    f"entry nodes — template router will handle portfolio routing"
                )
        timings["policy_resolve_ms"] = int((time.monotonic() - t0) * 1000)

        # Stage 4.6: Comparison policy enrichment
        if intent.type == IntentType.POLICY_COMPARISON:
            comparison_policy_ids = [
                nid for nid in entry_node_ids if nid.startswith("Policy#")
            ]
            logger.info(
                f"Comparison Stage 4.6: initial policy_ids={comparison_policy_ids}, "
                f"entities={[(e.value, e.type) for e in intent.entities]}"
            )
            if len(comparison_policy_ids) < 2:
                # Try to resolve product names via OpenSearch text search
                product_entities = [
                    e for e in intent.entities if e.type == "product_name"
                ]
                seen = set(comparison_policy_ids)
                for entity in product_entities:
                    if len(seen) >= 2:
                        break
                    try:
                        matches = await self._opensearch.search_by_product_name(
                            entity.value, node_type="Policy", k=1
                        )
                        logger.info(
                            f"Comparison: search '{entity.value}' → "
                            f"{[(m['node_id'], m['node_label']) for m in matches]}"
                        )
                        for m in matches:
                            if m["node_id"] not in seen:
                                entry_node_ids.append(m["node_id"])
                                seen.add(m["node_id"])
                                logger.info(
                                    f"Comparison: resolved '{entity.value}' "
                                    f"→ {m['node_id']}"
                                )
                    except Exception as e:
                        logger.warning(
                            f"Product name search failed for '{entity.value}': {e}"
                        )
                # Fallback: try vector search results
                if len(seen) < 2:
                    for node in entry_nodes:
                        pid = node["node_id"]
                        if pid.startswith("Policy#") and pid not in seen:
                            entry_node_ids.append(pid)
                            seen.add(pid)
                            if len(seen) >= 2:
                                break
                logger.info(
                    f"Comparison Stage 4.6 done: final entry_node_ids with "
                    f"{sum(1 for n in entry_node_ids if n.startswith('Policy#'))} "
                    f"Policy nodes"
                )

        # Stage 5: Template Routing
        t0 = time.monotonic()
        chain = self._router.route(intent, entry_node_ids=entry_node_ids)
        timings["routing_ms"] = int((time.monotonic() - t0) * 1000)

        # Stage 5.5: MyData merge context
        t0 = time.monotonic()
        merge_context = None
        if request.mydata_consent and request.mydata_consent.get("consented"):
            mydata_svc = MyDataService()
            mydata_policy_ids = [
                nid for nid in entry_node_ids if nid.startswith("Policy#")
            ]
            merge_context = mydata_svc.build_merge_context(
                request.mydata_consent["customer_id"], mydata_policy_ids,
                consent_verified=True,
            )
            if merge_context:
                logger.info(
                    f"MyData merge context: customer={merge_context.customer_node['label']}, "
                    f"policies={merge_context.activated_policy_ids}"
                )
        timings["mydata_merge_ms"] = int((time.monotonic() - t0) * 1000)

        # Stage 6: Graph Traversal
        t0 = time.monotonic()
        traversal_result = await self._traversal.traverse(chain.executions)
        timings["traversal_ms"] = int((time.monotonic() - t0) * 1000)

        # Stage 6.5: Enrich sparse or empty traversal results
        # Skip for comparison — the comparison router already handles multi-policy
        if (
            intent.type != IntentType.POLICY_COMPARISON
            and entry_node_ids[0] != "Policy#unknown"
        ):
            # Determine if primary template found its target node types
            primary_template_id = chain.executions[0].template_id if chain.executions else None
            primary_template = TEMPLATE_POOL.get(primary_template_id)
            target_types = primary_template.target_node_types if primary_template else []

            result_types = {n["type"] for n in traversal_result.subgraph_nodes}
            has_target = (
                any(t in result_types for t in target_types) if target_types
                else len(traversal_result.subgraph_nodes) >= 4  # legacy fallback for templates without target_node_types
            )

            if not has_target:
                t0 = time.monotonic()
                # Empty result: try comprehensive fallback
                fallback_chain = self._router.build_comprehensive_fallback(entry_node_ids)
                if fallback_chain:
                    logger.info(
                        f"Target types {target_types} not found in "
                        f"{result_types or 'empty'}, enriching with comprehensive_lookup"
                    )
                    enriched = await self._traversal.traverse(fallback_chain.executions)
                    if len(enriched.subgraph_nodes) > len(traversal_result.subgraph_nodes):
                        traversal_result = enriched
                        chain = fallback_chain

                # Still empty: try neighborhood fallback
                if len(traversal_result.subgraph_nodes) == 0:
                    nb_chain = self._router.build_neighborhood_fallback(entry_node_ids)
                    if nb_chain:
                        logger.info(
                            f"Still empty, enriching with neighborhood_lookup"
                        )
                        enriched = await self._traversal.traverse(nb_chain.executions)
                        if len(enriched.subgraph_nodes) > len(traversal_result.subgraph_nodes):
                            traversal_result = enriched
                            chain = nb_chain
                timings["fallback_ms"] = int((time.monotonic() - t0) * 1000)

        # Stage 6.7: MyData in-memory merge
        if merge_context:
            traversal_result = self._apply_mydata_merge(
                traversal_result, merge_context
            )

        # Stage 7: Hybrid Scoring
        vector_sim = entry_nodes[0]["score"] if entry_nodes else 0.0
        graph_ctx = min(traversal_result.total_hops / 4.0, 1.0)
        reg_weight = 1.0 if traversal_result.constraints_found > 0 else 0.0
        self._scorer.score(vector_sim, graph_ctx, reg_weight)

        # Stage 7.5: Comparison-aware subgraph handling
        is_portfolio = any(
            e.template_id.endswith("_portfolio_check")
            for e in chain.executions
        )
        if intent.type == IntentType.POLICY_COMPARISON:
            subgraph_dict = self._build_comparison_subgraph(
                traversal_result, entry_node_ids
            )
        else:
            subgraph_dict = self._prune_subgraph(
                traversal_result.subgraph_nodes,
                traversal_result.subgraph_edges,
                entry_node_ids=entry_node_ids,
                max_nodes=80 if is_portfolio else None,
            )

        # ── Pipeline Explorer: traverse stage event ──
        primary_template_id_for_event = (
            chain.executions[0].template_id if chain.executions else "unknown"
        )
        primary_template_for_event = TEMPLATE_POOL.get(primary_template_id_for_event)
        traverse_ms = (
            timings.get("traversal_ms", 0) + timings.get("routing_ms", 0)
            + timings.get("fallback_ms", 0) + timings.get("mydata_merge_ms", 0)
        )
        yield ("data", {
            "stage": "traverse", "status": "done",
            "ms": traverse_ms,
            "data": {
                "template": primary_template_id_for_event,
                "template_label": (
                    primary_template_for_event.description
                    if primary_template_for_event else ""
                ),
                "gremlin_query": (
                    chain.executions[0].gremlin_query[:300]
                    if chain.executions else ""
                ),
                "node_count": len(subgraph_dict.get("nodes", [])),
                "edge_count": len(subgraph_dict.get("edges", [])),
                "hops": traversal_result.total_hops,
                "constraints_found": traversal_result.constraints_found,
                "node_types_used": sorted(
                    {n.get("type", "") for n in subgraph_dict.get("nodes", [])}
                ),
                "edge_types_used": sorted(
                    {e.get("type", "") for e in subgraph_dict.get("edges", [])}
                ),
                "fallback_used": "fallback_ms" in timings,
            },
        })

        # ── Stage 8: Stream answer generation ────────────────────────

        yield ("data", {
            "stage": "generate", "status": "streaming",
            "data": {
                "model": "Claude Sonnet",
                "complexity": intent.complexity,
                "context_nodes": len(subgraph_dict.get("nodes", [])),
                "context_edges": len(subgraph_dict.get("edges", [])),
                "prompt_rules": 14,
            },
        })

        t0 = time.monotonic()
        answer_text = ""
        async for chunk in self._generator.generate_with_fallback(
            subgraph=subgraph_dict, query=query, intent=intent,
            merge_context=merge_context,
        ):
            answer_text += chunk
            yield ("text", chunk)
        timings["generation_ms"] = int((time.monotonic() - t0) * 1000)

        yield ("data", {
            "stage": "generate", "status": "done",
            "ms": timings["generation_ms"],
            "data": {},
        })

        # ── Stage 9: Validation + Annotation ─────────────────────────

        sources = self._extract_sources(traversal_result)

        t0 = time.monotonic()
        topo_faithfulness = None
        validation_status = "completed"
        try:
            validation = await asyncio.wait_for(
                self._validate(answer_text, chain.executions, traversal_result),
                timeout=settings.validation_timeout,
            )
            topo_faithfulness = validation.topo_faithfulness
        except asyncio.TimeoutError:
            logger.warning("Validation timed out, sending annotation without score")
            validation_status = "timeout"
            asyncio.create_task(
                self._validate_background(
                    request_id, answer_text, chain.executions, traversal_result
                )
            )
        timings["validation_ms"] = int((time.monotonic() - t0) * 1000)

        # ── Pipeline Explorer: verify stage event ──
        confidence_label = "high" if (topo_faithfulness or 0) >= 0.8 else (
            "medium" if (topo_faithfulness or 0) >= 0.5 else "low"
        )
        yield ("data", {
            "stage": "verify", "status": "done",
            "ms": timings.get("validation_ms", 0),
            "data": {
                "topo_faithfulness": topo_faithfulness,
                "validation_status": validation_status,
                "confidence_label": confidence_label,
            },
        })

        filtered_subgraph = filter_subgraph(request.persona, subgraph_dict)
        total_ms = int((time.monotonic() - start_time) * 1000)

        logger.info(
            json.dumps(
                {
                    "event": "pipeline_complete",
                    "request_id": request_id,
                    "persona": request.persona,
                    "intent": intent.type.value,
                    "templates_used": chain.chain_order,
                    "total_ms": total_ms,
                    "timings": timings,
                    "topo_faithfulness": topo_faithfulness,
                    "validation_status": validation_status,
                },
                ensure_ascii=False,
            )
        )

        annotation = {
            "intent": intent.type.value,
            "confidence": intent.confidence,
            "sources": [s.model_dump() for s in sources],
            "traversalEvents": traversal_result.traversal_events,
            "subgraph": filtered_subgraph,
            "topoFaithfulness": topo_faithfulness,
            "templatesUsed": chain.chain_order,
            "validationStatus": validation_status,
        }

        # ── Comparison mode: also generate naive RAG answer ────────
        if rag_mode == "comparison":
            t0 = time.monotonic()
            naive_answer = await self._generator.generate_naive_rag(
                entry_nodes, query
            )
            naive_time_ms = int((time.monotonic() - t0) * 1000)
            timings["naive_generation_ms"] = naive_time_ms
            naive_sources = self._extract_naive_sources(entry_nodes)
            annotation["naiveRag"] = {
                "answer": naive_answer,
                "sources": [s.model_dump() for s in naive_sources],
                "responseTimeMs": naive_time_ms,
            }
            annotation["comparisonMode"] = True
            annotation["graphRagResponseTimeMs"] = total_ms

        yield ("annotation", annotation)

    async def _validate(self, answer_text, executions, traversal_result):
        return await self._validator.validate(answer_text, executions, traversal_result)

    async def _validate_background(
        self, request_id, answer_text, executions, traversal_result
    ):
        try:
            result = await self._validator.validate(
                answer_text, executions, traversal_result
            )
            logger.info(
                f"Background validation completed: request={request_id}, "
                f"topo={result.topo_faithfulness}"
            )
        except Exception as e:
            logger.error(f"Background validation failed: request={request_id}, error={e}")

    async def _resolve_policy_nodes(self, entry_node_ids: list[str]) -> list[str]:
        """Reverse-traverse from non-Policy nodes to find connected Policy nodes.

        The vector search often returns Regulation#, Coverage#, Exception# nodes
        which are semantically relevant but can't be used directly in templates
        that start from Policy# nodes. This method follows edges backwards
        (1-3 hops) to find the Policy nodes they belong to.
        """
        ids_str = ", ".join(f"'{nid}'" for nid in entry_node_ids[:5])
        # Walk incoming edges toward root Policy nodes.
        # in() follows parent direction only (Policy→Coverage→Exclusion→Exception),
        # unlike both() which causes exponential path explosion.
        # Neptune does not support repeat().until() reliably, so we use
        # explicit union of 1/2/3-hop in() traversals.
        query = (
            f"g.V({ids_str}).union("
            "__.in().hasLabel('Policy'), "
            "__.in().in().hasLabel('Policy'), "
            "__.in().in().in().hasLabel('Policy'), "
            "__.in().has(id, TextP.startingWith('Policy#')), "
            "__.in().in().has(id, TextP.startingWith('Policy#')), "
            "__.in().in().in().has(id, TextP.startingWith('Policy#'))"
            ").dedup().limit(5).id()"
        )
        try:
            raw = await self._neptune.execute(query)
            resolved = self._extract_policy_ids(raw)
            return resolved
        except Exception as e:
            logger.warning(f"Policy node resolution failed: {e}")
            return []

    async def _resolve_portfolio_policies(self, limit: int = 3) -> list[str]:
        """Fetch representative Policy nodes from Neptune (portfolio-level fallback).

        Used when the query is generic (no specific product named) and no Policy
        nodes could be resolved from entry nodes. Returns a few Policy IDs so
        that template traversal can produce useful examples.
        """
        query = f"g.V().hasLabel('Policy').limit({limit}).id()"
        try:
            raw = await self._neptune.execute(query)
            resolved = self._extract_policy_ids(raw)
            if not resolved:
                # Fallback: try ID-prefix match
                query = f"g.V().has(id, TextP.startingWith('Policy#')).limit({limit}).id()"
                raw = await self._neptune.execute(query)
                resolved = self._extract_policy_ids(raw)
            return resolved
        except Exception as e:
            logger.warning(f"Portfolio policy resolution failed: {e}")
            return []

    @staticmethod
    def _extract_policy_ids(raw) -> list[str]:
        """Extract Policy# IDs from Neptune query results."""
        resolved = []
        for item in raw:
            if isinstance(item, str) and item.startswith("Policy#"):
                resolved.append(item)
            elif isinstance(item, list):
                resolved.extend(
                    s for s in item if isinstance(s, str) and s.startswith("Policy#")
                )
        return resolved

    def _apply_mydata_merge(
        self,
        traversal_result,
        merge_context: MergeContext,
    ):
        """Augment traversal result with MyData customer node and OWNS edges.

        This is an in-memory merge — no writes to Neptune.  The Customer node
        and OWNS edges are injected into the subgraph so the answer generator
        can reference the customer's contracts, and the frontend can animate
        the merge with ``merge_node_added`` events.
        """
        from app.models.traversal import TraversalResult

        # Copy mutable lists to avoid side-effects
        new_nodes = list(traversal_result.subgraph_nodes)
        new_edges = list(traversal_result.subgraph_edges)
        new_events = list(traversal_result.traversal_events)

        # Remove the existing traversal_complete event (we'll re-add at end)
        complete_event = None
        if new_events and new_events[-1].get("type") == "traversal_complete":
            complete_event = new_events.pop()

        # Compute current max delay
        current_delay = max(
            (e.get("delay_ms", 0) for e in new_events), default=0
        )
        merge_delay = DELAY_MAP.get("merge_node_added", 350)

        # Add Customer node
        new_nodes.append(merge_context.customer_node)
        current_delay += merge_delay
        new_events.append({
            "type": "merge_node_added",
            "hop": traversal_result.total_hops,
            "delay_ms": current_delay,
            "data": {
                "node_id": merge_context.customer_node["id"],
                "node_type": "Customer",
                "node_label": merge_context.customer_node["label"],
            },
        })

        # Add OWNS edges
        for edge in merge_context.owns_edges:
            new_edges.append(edge)
            current_delay += merge_delay
            new_events.append({
                "type": "merge_node_added",
                "hop": traversal_result.total_hops,
                "delay_ms": current_delay,
                "data": {
                    "node_id": edge["target"],
                    "node_type": "OWNS",
                    "node_label": f"OWNS → {edge['target']}",
                    "edge_type": "OWNS",
                },
            })

        # Re-add traversal_complete
        current_delay += DELAY_MAP.get("traversal_complete", 200)
        new_events.append({
            "type": "traversal_complete",
            "hop": traversal_result.total_hops,
            "delay_ms": current_delay,
            "data": {},
        })

        logger.info(
            f"MyData merge applied: +1 Customer node, "
            f"+{len(merge_context.owns_edges)} OWNS edges, "
            f"+{1 + len(merge_context.owns_edges)} merge events"
        )

        return TraversalResult(
            paths=traversal_result.paths,
            subgraph_nodes=new_nodes,
            subgraph_edges=new_edges,
            traversal_events=new_events,
            total_hops=traversal_result.total_hops,
            constraints_found=traversal_result.constraints_found,
        )

    def _build_comparison_subgraph(
        self,
        traversal_result,
        entry_node_ids: list[str],
    ) -> dict:
        """Build a comparison subgraph that tags nodes with their source policy.

        Splits the pruning budget evenly between the compared policies, then
        adds a 'compared_policy' property to each node so the answer generator
        knows which policy each node belongs to.
        """
        policy_ids = [nid for nid in entry_node_ids if nid.startswith("Policy#")]
        if len(policy_ids) < 2:
            return self._prune_subgraph(
                traversal_result.subgraph_nodes,
                traversal_result.subgraph_edges,
                entry_node_ids=entry_node_ids,
            )

        policy_a, policy_b = policy_ids[0], policy_ids[1]

        # Voronoi partitioning: assign each node to the NEAREST policy root.
        # Using undirected BFS from a single root would claim everything
        # (policies share Regulation nodes), so we compute distances from
        # both roots simultaneously and pick the closer one.
        dist_a = self._compute_distances(
            traversal_result.subgraph_edges, {policy_a}
        )
        dist_b = self._compute_distances(
            traversal_result.subgraph_edges, {policy_b}
        )

        node_to_policy: dict[str, str] = {}
        all_node_ids = {n["id"] for n in traversal_result.subgraph_nodes}
        for nid in all_node_ids:
            da = dist_a.get(nid, float("inf"))
            db = dist_b.get(nid, float("inf"))
            if da < db:
                node_to_policy[nid] = policy_a
            elif db < da:
                node_to_policy[nid] = policy_b
            elif da != float("inf"):
                # Equidistant — mark as shared
                node_to_policy[nid] = "shared"
            # else: unreachable from either → stays out of node_to_policy

        # Split into per-policy groups
        budget_per = self.COMPARISON_BUDGET_PER_POLICY

        nodes_a = [n for n in traversal_result.subgraph_nodes
                    if node_to_policy.get(n["id"]) == policy_a]
        nodes_b = [n for n in traversal_result.subgraph_nodes
                    if node_to_policy.get(n["id"]) == policy_b]
        nodes_shared = [n for n in traversal_result.subgraph_nodes
                        if node_to_policy.get(n["id"]) == "shared"
                        or n["id"] not in node_to_policy]

        edges_a = [e for e in traversal_result.subgraph_edges
                    if node_to_policy.get(e["source"]) == policy_a
                    or node_to_policy.get(e["target"]) == policy_a]
        edges_b = [e for e in traversal_result.subgraph_edges
                    if node_to_policy.get(e["source"]) == policy_b
                    or node_to_policy.get(e["target"]) == policy_b]

        # Prune each group separately
        pruned_a = self._prune_subgraph(
            nodes_a, edges_a, entry_node_ids=[policy_a], max_nodes=budget_per
        )
        pruned_b = self._prune_subgraph(
            nodes_b, edges_b, entry_node_ids=[policy_b], max_nodes=budget_per
        )

        # Tag nodes with policy ownership
        for n in pruned_a["nodes"]:
            n["compared_policy"] = policy_a
        for n in pruned_b["nodes"]:
            n["compared_policy"] = policy_b
        for n in nodes_shared:
            n["compared_policy"] = "shared"

        # Limit shared nodes (mostly Regulation) to avoid drowning per-policy data
        MAX_SHARED = 5
        if len(nodes_shared) > MAX_SHARED:
            # Prefer shared nodes closest to either root
            shared_scored = []
            for n in nodes_shared:
                da = dist_a.get(n["id"], float("inf"))
                db = dist_b.get(n["id"], float("inf"))
                shared_scored.append((min(da, db), n))
            shared_scored.sort(key=lambda x: x[0])
            nodes_shared = [n for _, n in shared_scored[:MAX_SHARED]]

        # Merge
        all_nodes = pruned_a["nodes"] + pruned_b["nodes"] + nodes_shared
        all_node_ids = {n["id"] for n in all_nodes}
        all_edges = [
            e for e in pruned_a["edges"] + pruned_b["edges"]
            if e["source"] in all_node_ids and e["target"] in all_node_ids
        ]

        logger.info(
            f"Comparison subgraph: {policy_a}={len(pruned_a['nodes'])} nodes, "
            f"{policy_b}={len(pruned_b['nodes'])} nodes, "
            f"shared={len(nodes_shared)}"
        )
        return {"nodes": all_nodes, "edges": all_edges}

    # Korean stop words for BM25 topic keyword extraction.
    # Removing these from the query lets BM25 focus on discriminating terms
    # (e.g. "치매" instead of "관련", "어떤", "특약").
    _BM25_STOPWORDS = frozenset({
        # Question words / endings
        "어떤", "어떻게", "무엇", "뭐", "알려주세요", "하나요", "인가요",
        "건가요", "될까요", "있나요", "없나요", "줘", "주세요", "궁금합니다",
        # Function words / verb stems
        "받으려면", "해야", "하면", "할", "있다", "없다", "위해", "대해",
        "통해", "위한", "대한", "것", "때", "경우", "관련", "대하여",
        "가입해야", "가입하면", "가입", "확인", "문의",
        # Common insurance domain terms (appear in virtually every document,
        # so they have near-zero BM25 IDF and only add noise)
        "보험", "보험상품", "상품", "보장", "특약", "보험료", "보험금",
        "계약", "약관", "조건", "내용", "사항",
    })

    @classmethod
    def _extract_bm25_keywords(cls, query: str) -> str:
        """Extract topic keywords from query for BM25 search.

        Strips Korean particles, question endings, and common stop words
        to leave discriminating content words (e.g. "치매 보장 특약 가입").
        """
        import re
        # Strip Korean particles attached to words
        cleaned = re.sub(
            r'([가-힣]+?)(을|를|에|가|이|은|는|의|도|에서|으로|와|과|이나|나|에게|한테|까지|부터)(?=\s|$|[?.])',
            r'\1', query
        )
        # Remove question marks and periods
        cleaned = cleaned.replace("?", "").replace(".", "").strip()
        words = cleaned.split()
        keywords = [
            w for w in words
            if w not in cls._BM25_STOPWORDS and len(w) > 1
        ]
        return " ".join(keywords) if keywords else query

    # Intent types that benefit from BM25 + k-NN hybrid fusion (Branch B)
    # when no product_name entity is extracted from the query.
    # These are topic-based intents where keyword matching supplements
    # vector search (e.g. "치매 관련 보장" should match 치매 in text).
    TOPIC_SEARCH_INTENTS = frozenset({
        IntentType.COVERAGE_INQUIRY,
        IntentType.EXCLUSION_EXCEPTION,
        IntentType.RIDER_INQUIRY,
        IntentType.CALCULATION_INQUIRY,
        IntentType.PREMIUM_WAIVER,
        IntentType.DISCOUNT_ELIGIBILITY,
        IntentType.SURRENDER_VALUE,
        IntentType.ELIGIBILITY_INQUIRY,
    })

    MAX_SUBGRAPH_NODES = 30
    COMPARISON_BUDGET_PER_POLICY = 15
    MIN_REGULATION_SLOTS = 5
    CONSTRAINT_EDGE_TYPES = frozenset({
        "STRICTLY_PROHIBITED", "EXCEPTION_ALLOWED",
        "EXCLUDED_IF", "EXCEPTIONALLY_ALLOWED",
    })

    def _prune_subgraph(
        self,
        nodes: list[dict],
        edges: list[dict],
        entry_node_ids: list[str] | None = None,
        max_nodes: int | None = None,
    ) -> dict:
        """Cap the subgraph while protecting constraint-connected nodes.

        1. Nodes connected via constraint edges are never pruned.
        2. Remaining nodes are ranked by BFS distance from entry nodes.
        3. Regulation slot balance is maintained among unprotected nodes.
        """
        budget = max_nodes if max_nodes is not None else self.MAX_SUBGRAPH_NODES
        if len(nodes) <= budget:
            return {"nodes": nodes, "edges": edges}

        # Step 1: Identify protected nodes (connected via constraint edges)
        protected_ids: set[str] = set()
        for edge in edges:
            if edge["type"] in self.CONSTRAINT_EDGE_TYPES:
                protected_ids.add(edge["source"])
                protected_ids.add(edge["target"])

        protected = [n for n in nodes if n["id"] in protected_ids]
        unprotected = [n for n in nodes if n["id"] not in protected_ids]

        # Step 2: If protected alone exceeds budget, keep all (correctness > size)
        remaining_budget = budget - len(protected)
        if remaining_budget <= 0:
            kept = protected
        else:
            # Step 3: Rank unprotected by BFS distance from entry nodes
            if entry_node_ids:
                distances = self._compute_distances(edges, set(entry_node_ids))
                unprotected.sort(
                    key=lambda n: distances.get(n["id"], float("inf"))
                )

            # Step 4: Regulation slot balance among unprotected
            unprotected_primary = [
                n for n in unprotected if n.get("type") != "Regulation"
            ]
            unprotected_reg = [
                n for n in unprotected if n.get("type") == "Regulation"
            ]

            protected_reg_count = sum(
                1 for n in protected if n.get("type") == "Regulation"
            )
            reg_slots_needed = max(
                0, self.MIN_REGULATION_SLOTS - protected_reg_count
            )
            reg_slots = min(
                reg_slots_needed, len(unprotected_reg), remaining_budget
            )

            primary_slots = remaining_budget - reg_slots
            kept_primary = unprotected_primary[:primary_slots]
            reg_slots_final = remaining_budget - len(kept_primary)
            kept_reg = unprotected_reg[:reg_slots_final]

            kept = protected + kept_primary + kept_reg

        kept_ids = {n["id"] for n in kept}
        pruned_edges = [
            e for e in edges
            if e["source"] in kept_ids and e["target"] in kept_ids
        ]

        logger.info(
            f"Subgraph pruned: {len(nodes)} → {len(kept)} nodes "
            f"(protected={len(protected)}, unprotected_kept="
            f"{len(kept) - len(protected)})"
        )
        return {"nodes": kept, "edges": pruned_edges}

    @staticmethod
    def _compute_distances(
        edges: list[dict], entry_ids: set[str]
    ) -> dict[str, int]:
        """BFS from entry_ids over the edge list."""
        adj: dict[str, list[str]] = {}
        for edge in edges:
            s, t = edge["source"], edge["target"]
            adj.setdefault(s, []).append(t)
            adj.setdefault(t, []).append(s)

        distance: dict[str, int] = {}
        queue = deque()
        for eid in entry_ids:
            distance[eid] = 0
            queue.append(eid)

        while queue:
            current = queue.popleft()
            for neighbor in adj.get(current, []):
                if neighbor not in distance:
                    distance[neighbor] = distance[current] + 1
                    queue.append(neighbor)

        return distance

    def _extract_sources(self, traversal_result) -> list[SourceReference]:
        sources = []
        seen = set()
        for node in traversal_result.subgraph_nodes:
            node_id = node["id"]
            if node_id not in seen:
                seen.add(node_id)
                props = node.get("properties", {})
                sources.append(
                    SourceReference(
                        node_id=node_id,
                        node_type=node.get("type", ""),
                        node_label=node.get("label", ""),
                        source_article=props.get("source_article", "")
                        or props.get("source_section_id", ""),
                        source_text=props.get("source_text", ""),
                    )
                )
        return sources
