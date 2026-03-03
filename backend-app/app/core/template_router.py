import logging

from app.models.intent import Intent, IntentType
from app.models.template import ChainResult, GremlinTemplate, TemplateExecution

logger = logging.getLogger("graphrag.router")


def escape_gremlin_param(value: str) -> str:
    return (
        value.replace("\\", "\\\\")
        .replace("'", "\\'")
        .replace("`", "\\`")
        .replace('"', '\\"')
    )


def bind_params(template: GremlinTemplate, params: dict[str, str]) -> str:
    query = template.gremlin
    for key, value in params.items():
        safe_value = escape_gremlin_param(value)
        query = query.replace(f"'{{{key}}}'", f"'{safe_value}'")
    return query


TEMPLATE_POOL: dict[str, GremlinTemplate] = {
    "coverage_lookup": GremlinTemplate(
        id="coverage_lookup",
        description="보장항목 및 지급사유/금액 조회",
        intent_type="coverage_inquiry",
        gremlin=(
            "g.V('{policy_id}').as('policy')"
            ".outE('HAS_COVERAGE').inV().as('coverage')"
            ".optional(outE('EXCLUDED_IF').inV().as('exclusion')"
            ".optional(outE('EXCEPTION_ALLOWED').inV().as('exception')))"
            ".path().by(elementMap())"
        ),
        params=["policy_id"],
        max_depth=3,
        complexity="simple",
        target_node_types=["Coverage"],
    ),
    "dividend_eligibility_check": GremlinTemplate(
        id="dividend_eligibility_check",
        description="배당 가능 여부 및 규제 제약 확인",
        intent_type="dividend_check",
        gremlin=(
            "g.V('{policy_id}').as('policy')"
            ".union("
            "outE('NO_DIVIDEND_STRUCTURE').inV().as('dividend'),"
            "outE('GOVERNED_BY').inV().as('regulation')"
            ".optional(outE('EXCEPTIONALLY_ALLOWED').inV().as('exception_type'))"
            ").path().by(elementMap())"
        ),
        params=["policy_id"],
        max_depth=3,
        complexity="complex",
        target_node_types=["Dividend_Method"],
    ),
    "exclusion_exception_traverse": GremlinTemplate(
        id="exclusion_exception_traverse",
        description="면책사유 및 단서예외 조건부 분기 탐색 (키워드 필터)",
        intent_type="exclusion_exception",
        gremlin=(
            "g.V('{policy_id}')"
            ".outE('HAS_COVERAGE').inV()"
            ".outE('EXCLUDED_IF').inV()"
            ".has('label', TextP.containing('{exclusion_keyword}'))"
            ".as('exclusion')"
            ".optional(outE('EXCEPTION_ALLOWED').inV().as('exception'))"
            ".path().by(elementMap())"
        ),
        params=["policy_id", "exclusion_keyword"],
        max_depth=3,
        complexity="complex",
        target_node_types=["Exclusion"],
    ),
    "exclusion_full_traverse": GremlinTemplate(
        id="exclusion_full_traverse",
        description="면책사유 전체 탐색 (키워드 없을 때 사용)",
        intent_type="exclusion_exception",
        gremlin=(
            "g.V('{policy_id}')"
            ".outE('HAS_COVERAGE').inV()"
            ".outE('EXCLUDED_IF').inV()"
            ".as('exclusion')"
            ".optional(outE('EXCEPTION_ALLOWED').inV().as('exception'))"
            ".path().by(elementMap())"
        ),
        params=["policy_id"],
        max_depth=3,
        complexity="complex",
        target_node_types=["Exclusion"],
    ),
    "surrender_value_lookup": GremlinTemplate(
        id="surrender_value_lookup",
        description="해약환급금 경과기간별 조건 조회",
        intent_type="surrender_value",
        gremlin=(
            "g.V('{policy_id}')"
            ".outE('SURRENDER_PAYS').inV()"
            ".order().by('label', Order.asc)"
            ".path().by(elementMap())"
        ),
        params=["policy_id"],
        max_depth=1,
        complexity="simple",
        target_node_types=["Surrender_Value"],
    ),
    "discount_eligibility": GremlinTemplate(
        id="discount_eligibility",
        description="보험료 할인 조건 및 할인율 조회",
        intent_type="discount_eligibility",
        gremlin=(
            "g.V('{policy_id}')"
            ".outE('HAS_DISCOUNT').inV()"
            ".project('id', 'label', 'discount_rate_text', 'source_text')"
            ".by(id).by('label').by('discount_rate_text').by('source_text')"
        ),
        params=["policy_id"],
        max_depth=1,
        complexity="simple",
        target_node_types=["Premium_Discount"],
    ),
    "regulation_lookup": GremlinTemplate(
        id="regulation_lookup",
        description="보험상품에 적용되는 규제/법령 조회",
        intent_type="regulation_inquiry",
        gremlin=(
            "g.V('{policy_id}').as('policy')"
            ".outE('GOVERNED_BY').inV().as('regulation')"
            ".optional(outE('STRICTLY_PROHIBITED').inV().as('prohibition'))"
            ".optional(outE('EXCEPTIONALLY_ALLOWED').inV().as('exception'))"
            ".path().by(elementMap())"
        ),
        params=["policy_id"],
        max_depth=3,
        complexity="complex",
        target_node_types=["Regulation"],
    ),
    "regulation_reverse_lookup": GremlinTemplate(
        id="regulation_reverse_lookup",
        description="규제 조항이 적용되는 보험상품 역탐색",
        intent_type="regulation_inquiry",
        gremlin=(
            "g.V('{regulation_id}').as('regulation')"
            ".inE('GOVERNED_BY').outV().as('policy')"
            ".path().by(elementMap())"
        ),
        params=["regulation_id"],
        max_depth=2,
        complexity="simple",
        target_node_types=["Regulation", "Policy"],
    ),
    "calculation_lookup": GremlinTemplate(
        id="calculation_lookup",
        description="보험료/환급금 계산식 및 산출 공식 조회",
        intent_type="calculation_inquiry",
        gremlin=(
            "g.V('{policy_id}').as('policy').union("
            "outE('HAS_COVERAGE').inV().outE('CALCULATED_BY').inV().as('calc_cov'),"
            "outE('SURRENDER_PAYS').inV().outE('CALCULATED_BY').inV().as('calc_surr'),"
            "outE('HAS_DISCOUNT').inV().outE('CALCULATED_BY').inV().as('calc_disc'),"
            "outE('HAS_RIDER').inV().outE('CALCULATED_BY').inV().as('calc_rider')"
            ").path().by(elementMap())"
        ),
        params=["policy_id"],
        max_depth=3,
        complexity="complex",
        target_node_types=["Calculation"],
    ),
    "premium_waiver_lookup": GremlinTemplate(
        id="premium_waiver_lookup",
        description="보험료 납입면제 조건 조회",
        intent_type="premium_waiver",
        gremlin=(
            "g.V('{policy_id}').as('policy')"
            ".outE('WAIVES_PREMIUM').inV().as('waiver')"
            ".optional(outE('EXCLUDED_IF').inV().as('exclusion')"
            ".optional(outE('EXCEPTION_ALLOWED').inV().as('exception')))"
            ".path().by(elementMap())"
        ),
        params=["policy_id"],
        max_depth=3,
        complexity="simple",
        target_node_types=["Coverage"],
    ),
    "eligibility_lookup": GremlinTemplate(
        id="eligibility_lookup",
        description="보험 가입자격 및 심사기준 조회",
        intent_type="eligibility_inquiry",
        gremlin=(
            "g.V('{policy_id}').as('policy')"
            ".outE('REQUIRES_ELIGIBILITY').inV().as('eligibility')"
            ".path().by(elementMap())"
        ),
        params=["policy_id"],
        max_depth=2,
        complexity="simple",
        target_node_types=["Eligibility"],
    ),
    "rider_lookup": GremlinTemplate(
        id="rider_lookup",
        description="보험 특약(Rider) 목록 및 내용 조회",
        intent_type="rider_inquiry",
        gremlin=(
            "g.V('{policy_id}').as('policy')"
            ".outE('HAS_RIDER').inV().as('rider')"
            ".path().by(elementMap())"
        ),
        params=["policy_id"],
        max_depth=2,
        complexity="simple",
        target_node_types=["Rider"],
    ),
    "dividend_portfolio_check": GremlinTemplate(
        id="dividend_portfolio_check",
        description="전체 보험상품의 배당 가능 여부 일괄 확인 (상품 미지정 시)",
        intent_type="dividend_check",
        gremlin=(
            "g.V().has(id, TextP.startingWith('Policy#')).limit(30).as('policy')"
            ".optional(outE('NO_DIVIDEND_STRUCTURE').inV().as('dividend'))"
            ".path().by(elementMap())"
        ),
        params=[],
        max_depth=2,
        complexity="complex",
        target_node_types=["Dividend_Method"],
    ),
    "comprehensive_lookup": GremlinTemplate(
        id="comprehensive_lookup",
        description="보험상품의 모든 연결 관계 종합 탐색 (폴백용)",
        intent_type="general_inquiry",
        gremlin=(
            "g.V('{policy_id}').as('policy').union("
            "outE('HAS_COVERAGE').inV().as('coverage')"
            ".optional(outE('EXCLUDED_IF').inV().as('exclusion')"
            ".optional(outE('EXCEPTION_ALLOWED').inV().as('exception'))),"
            "outE('HAS_COVERAGE').inV().optional(outE('CALCULATED_BY').inV().as('calc')),"
            "outE('NO_DIVIDEND_STRUCTURE').inV().as('dividend'),"
            "outE('GOVERNED_BY').inV().as('regulation')"
            ".optional(outE('EXCEPTIONALLY_ALLOWED').inV().as('exception_type')),"
            "outE('SURRENDER_PAYS').inV().as('surrender'),"
            "outE('REQUIRES_ELIGIBILITY').inV().as('eligibility'),"
            "outE('HAS_RIDER').inV().as('rider'),"
            "outE('WAIVES_PREMIUM').inV().as('waiver'),"
            "outE('OWNS').inV().as('category')"
            ").path().by(elementMap())"
        ),
        params=["policy_id"],
        max_depth=4,
        complexity="complex",
    ),
}

NEIGHBORHOOD_TEMPLATE = GremlinTemplate(
    id="neighborhood_lookup",
    description="벡터 검색 결과 노드의 직접 이웃 탐색 (Policy 없을 때 폴백)",
    intent_type="general_inquiry",
    gremlin="__placeholder__",  # dynamically built per-request
    params=[],
    max_depth=2,
    complexity="simple",
)

INTENT_TO_TEMPLATE: dict[str, str] = {
    "coverage_inquiry": "coverage_lookup",
    "dividend_check": "dividend_eligibility_check",
    "exclusion_exception": "exclusion_exception_traverse",
    "surrender_value": "surrender_value_lookup",
    "discount_eligibility": "discount_eligibility",
    "regulation_inquiry": "regulation_lookup",
    "loan_inquiry": "comprehensive_lookup",
    "premium_waiver": "premium_waiver_lookup",
    "policy_comparison": "comprehensive_lookup",
    "calculation_inquiry": "calculation_lookup",
    "eligibility_inquiry": "eligibility_lookup",
    "rider_inquiry": "rider_lookup",
}

CHAIN_MAP: dict[str, str] = {
    "coverage_inquiry": "exclusion_exception_traverse",
}


class TemplateRouter:
    def route(self, intent: Intent, entry_node_ids: list[str]) -> ChainResult:
        # Classify entry nodes by type
        policy_ids = [nid for nid in entry_node_ids if nid.startswith("Policy#")]
        regulation_ids = [nid for nid in entry_node_ids if nid.startswith("Regulation#")]

        # Resolve primary template
        template_id = INTENT_TO_TEMPLATE.get(intent.type.value, "coverage_lookup")

        # For regulation_inquiry: decide direction based on entry node types
        if intent.type.value == "regulation_inquiry":
            return self._route_regulation(
                policy_ids, regulation_ids, entry_node_ids
            )

        # For policy_comparison: run same template for each policy
        if intent.type == IntentType.POLICY_COMPARISON:
            return self._route_comparison(intent, policy_ids, entry_node_ids)

        # Portfolio-level query: no specific product entity → query all products
        product_entities = [e for e in intent.entities if e.type == "product_name"]
        portfolio_template_id = self._get_portfolio_template(intent, product_entities)
        if portfolio_template_id:
            return self._route_portfolio(portfolio_template_id, entry_node_ids)

        # Default: prefer Policy-type nodes as entry point
        policy_id = policy_ids[0] if policy_ids else (
            entry_node_ids[0] if entry_node_ids else "Policy#unknown"
        )

        template = TEMPLATE_POOL[template_id]

        # Build params
        params = {"policy_id": policy_id}
        for entity in intent.entities:
            if entity.type == "exclusion_keyword" or entity.type == "exclusion_type":
                params["exclusion_keyword"] = entity.value

        # QW5: When exclusion_keyword is empty, use full traversal (no keyword filter)
        if "exclusion_keyword" not in params and "exclusion_keyword" in template.params:
            if template_id == "exclusion_exception_traverse":
                template_id = "exclusion_full_traverse"
                template = TEMPLATE_POOL[template_id]
                logger.info(
                    "exclusion_keyword empty — switching to exclusion_full_traverse"
                )
            else:
                params["exclusion_keyword"] = ""

        gremlin_query = bind_params(template, params)

        executions = [
            TemplateExecution(
                template_id=template_id,
                gremlin_query=gremlin_query,
                params=params,
                max_depth=template.max_depth,
                entry_node_ids=entry_node_ids,
            )
        ]

        # Chain template if applicable
        chain_template_id = CHAIN_MAP.get(intent.type.value)
        if chain_template_id and chain_template_id != template_id:
            chain_params = {**params}
            # QW5: Use full traverse for chained exclusion when no keyword
            if (
                chain_template_id == "exclusion_exception_traverse"
                and ("exclusion_keyword" not in chain_params
                     or not chain_params.get("exclusion_keyword"))
            ):
                chain_template_id = "exclusion_full_traverse"
                chain_params.pop("exclusion_keyword", None)
            elif (
                "exclusion_keyword" not in chain_params
                or not chain_params["exclusion_keyword"]
            ):
                chain_params["exclusion_keyword"] = ""
            chain_template = TEMPLATE_POOL[chain_template_id]
            chain_query = bind_params(chain_template, chain_params)
            executions.append(
                TemplateExecution(
                    template_id=chain_template_id,
                    gremlin_query=chain_query,
                    params=chain_params,
                    max_depth=chain_template.max_depth,
                    entry_node_ids=entry_node_ids,
                )
            )

        chain_order = [e.template_id for e in executions]
        return ChainResult(executions=executions, chain_order=chain_order)

    def build_comprehensive_fallback(
        self, entry_node_ids: list[str]
    ) -> ChainResult | None:
        """Build a comprehensive fallback that traverses all edge types.

        Used when the primary template returns empty results — the Policy node
        may not have the specific edge type (e.g. HAS_COVERAGE) but does have
        other useful connections (GOVERNED_BY, NO_DIVIDEND_STRUCTURE, etc.).
        """
        policy_ids = [nid for nid in entry_node_ids if nid.startswith("Policy#")]
        if not policy_ids:
            return None

        template = TEMPLATE_POOL["comprehensive_lookup"]
        executions = []
        for pid in policy_ids[:2]:  # Try up to 2 Policy nodes
            params = {"policy_id": pid}
            executions.append(
                TemplateExecution(
                    template_id="comprehensive_lookup",
                    gremlin_query=bind_params(template, params),
                    params=params,
                    max_depth=template.max_depth,
                    entry_node_ids=[pid],
                )
            )
        return ChainResult(
            executions=executions,
            chain_order=[e.template_id for e in executions],
        )

    def build_neighborhood_fallback(
        self, entry_node_ids: list[str]
    ) -> ChainResult | None:
        """Explore direct neighbors of vector search result nodes.

        Used as a last-resort fallback when no Policy nodes can be found,
        so that the subgraph is never completely empty as long as the entry
        nodes exist in Neptune.
        """
        if not entry_node_ids or entry_node_ids == ["Policy#unknown"]:
            return None

        ids_str = ", ".join(
            f"'{escape_gremlin_param(nid)}'" for nid in entry_node_ids[:5]
        )
        query = (
            f"g.V({ids_str}).as('start').union("
            "__.outE().inV().as('out_neighbor'), "
            "__.inE().outV().as('in_neighbor')"
            ").path().by(elementMap())"
        )
        executions = [
            TemplateExecution(
                template_id="neighborhood_lookup",
                gremlin_query=query,
                params={},
                max_depth=2,
                entry_node_ids=entry_node_ids[:5],
            )
        ]
        return ChainResult(
            executions=executions,
            chain_order=["neighborhood_lookup"],
        )

    # Map of intent types that have portfolio-level templates
    _PORTFOLIO_TEMPLATES: dict[str, str] = {
        "dividend_check": "dividend_portfolio_check",
    }

    # Generic terms that are not specific product names
    _GENERIC_PRODUCT_SUFFIXES = ("보험상품", "보험 상품", "상품")

    def _get_portfolio_template(
        self, intent: Intent, product_entities: list
    ) -> str | None:
        """Return portfolio template ID if query is generic (no specific product)."""
        # Filter out generic product references like "한화생명 보험상품"
        specific = [
            e for e in product_entities
            if not any(e.value.endswith(s) for s in self._GENERIC_PRODUCT_SUFFIXES)
        ]
        if specific:
            return None
        return self._PORTFOLIO_TEMPLATES.get(intent.type.value)

    def _route_portfolio(
        self, template_id: str, entry_node_ids: list[str]
    ) -> ChainResult:
        """Route to a portfolio-level template (no params, scans all policies)."""
        template = TEMPLATE_POOL[template_id]
        executions = [
            TemplateExecution(
                template_id=template_id,
                gremlin_query=template.gremlin,
                params={},
                max_depth=template.max_depth,
                entry_node_ids=entry_node_ids,
            )
        ]
        logger.info(f"Portfolio routing: using {template_id} (no specific product)")
        return ChainResult(
            executions=executions,
            chain_order=[template_id],
        )

    def _route_regulation(
        self,
        policy_ids: list[str],
        regulation_ids: list[str],
        all_entry_ids: list[str],
    ) -> ChainResult:
        executions = []

        # Forward: Policy → GOVERNED_BY → Regulation (limit to 3 to avoid explosion)
        if policy_ids:
            template = TEMPLATE_POOL["regulation_lookup"]
            for pid in policy_ids[:3]:
                params = {"policy_id": pid}
                executions.append(
                    TemplateExecution(
                        template_id="regulation_lookup",
                        gremlin_query=bind_params(template, params),
                        params=params,
                        max_depth=template.max_depth,
                        entry_node_ids=[pid],
                    )
                )

        # Reverse: Regulation ← GOVERNED_BY ← Policy (limit to 3)
        if regulation_ids:
            template = TEMPLATE_POOL["regulation_reverse_lookup"]
            for rid in regulation_ids[:3]:
                params = {"regulation_id": rid}
                executions.append(
                    TemplateExecution(
                        template_id="regulation_reverse_lookup",
                        gremlin_query=bind_params(template, params),
                        params=params,
                        max_depth=template.max_depth,
                        entry_node_ids=[rid],
                    )
                )

        # Fallback: if no Policy or Regulation nodes, try all entry nodes as policy
        if not executions:
            template = TEMPLATE_POOL["regulation_lookup"]
            fallback_id = all_entry_ids[0] if all_entry_ids else "Policy#unknown"
            params = {"policy_id": fallback_id}
            executions.append(
                TemplateExecution(
                    template_id="regulation_lookup",
                    gremlin_query=bind_params(template, params),
                    params=params,
                    max_depth=template.max_depth,
                    entry_node_ids=all_entry_ids,
                )
            )

        chain_order = [e.template_id for e in executions]
        return ChainResult(executions=executions, chain_order=chain_order)

    def _route_comparison(
        self,
        intent: Intent,
        policy_ids: list[str],
        all_entry_ids: list[str],
    ) -> ChainResult:
        """Route comparison by running the same template once per policy.

        Always uses ``comprehensive_lookup`` because different policies may
        have different edge types (e.g. one has HAS_COVERAGE, another does
        not).  Comprehensive ensures both policies return their full data.
        """
        comparison_template_id = "comprehensive_lookup"

        # Use up to 2 policy IDs for comparison
        target_policies = policy_ids[:2] if policy_ids else []

        # If fewer than 2 policies, look for more in entry nodes
        if len(target_policies) < 2:
            seen = set(target_policies)
            for nid in all_entry_ids:
                if nid.startswith("Policy#") and nid not in seen:
                    target_policies.append(nid)
                    seen.add(nid)
                    if len(seen) >= 2:
                        break

        # Still no policies? Use first entry node as fallback
        if not target_policies:
            target_policies = [
                all_entry_ids[0] if all_entry_ids else "Policy#unknown"
            ]

        template = TEMPLATE_POOL[comparison_template_id]
        executions = []

        for pid in target_policies:
            params = {"policy_id": pid}
            if "exclusion_keyword" in template.params:
                params["exclusion_keyword"] = ""

            executions.append(
                TemplateExecution(
                    template_id=comparison_template_id,
                    gremlin_query=bind_params(template, params),
                    params=params,
                    max_depth=template.max_depth,
                    entry_node_ids=[pid],
                )
            )

        chain_order = [e.template_id for e in executions]
        return ChainResult(executions=executions, chain_order=chain_order)

    def _detect_comparison_aspect(self, intent: Intent) -> str:
        """Detect which aspect is being compared from entities/keywords."""
        entity_text = " ".join(e.value for e in intent.entities)

        aspect_keywords = {
            "coverage_lookup": ["보장", "보장항목", "보험금"],
            "exclusion_exception_traverse": ["면책", "예외", "제외"],
            "dividend_eligibility_check": ["배당", "무배당"],
            "surrender_value_lookup": ["해약", "환급금", "해지"],
            "discount_eligibility": ["할인"],
            "calculation_lookup": ["계산", "계산식", "산출", "공식"],
        }

        for template_id, keywords in aspect_keywords.items():
            for kw in keywords:
                if kw in entity_text:
                    return template_id

        return "comprehensive_lookup"
