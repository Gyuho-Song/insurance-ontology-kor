#!/bin/bash
# U7 무인 재구축 파이프라인 (2-phase)
# Phase A (이 환경, VPC 외부): 재추출 → build_graph(Opus4.8) → U6 ER → 검증 → gold 채점. 데이터 정확성 완주.
# Phase B (VPC 내부 필요, 준비만): Neptune 재로드 → OpenSearch → EKS 배포 → eval v11.
#   ※ Neptune/OpenSearch는 VPC-only → 이 환경 도달 불가. 산출물+실행명령 준비 후 기록하고 정지.
set -o pipefail
VENV=/tmp/u2venv/bin/python
ROOT=/mnt/data/projects/ontology-demo
LOG=/tmp/fc9_pipeline.log
PARSED=/tmp/dp_opus_full
V3=/mnt/data/v3-graph-ready
RESOLVED=/mnt/data/v3-graph-ready-resolved/_resolved.json
exec >> "$LOG" 2>&1
cd "$ROOT"
step() { echo ""; echo "═══ [$(TZ=UTC date '+%H:%M:%S' 2>/dev/null||echo .)] $1 ═══"; }

# ── A1. 재추출 완료 대기 (39개) ──
step "A1. doc-parser Opus4.8 재추출 완료 대기"
while [ "$(grep -cE 'Done →|🎉' /tmp/dp_opus_full.log 2>/dev/null)" -lt 39 ]; do sleep 60; done
echo "재추출 완료: $(grep -cE 'Done →|🎉' /tmp/dp_opus_full.log)/39"

# ── A2. build_graph (표 + LLM Opus4.8) ──
step "A2. build_graph_from_parsed (표 deterministic + LLM Opus4.8)"
mkdir -p "$V3"
EXTRACT_MODEL_ID=us.anthropic.claude-opus-4-8 PYTHONPATH=scripts $VENV scripts/build_graph_from_parsed.py \
  --parsed-dir "$PARSED" --out-dir "$V3" || { echo "FAIL A2"; exit 2; }
echo "v3-graph-ready: $(ls $V3/*.graph.json 2>/dev/null | wc -l) docs"

# ── A3. U6 resolve_entities (cross-doc ER + embedding) ──
step "A3. U6 resolve_entities (ER + Titan embedding)"
mkdir -p "$(dirname $RESOLVED)"
PYTHONPATH=scripts $VENV scripts/resolve_entities.py \
  --input-dir "$V3" --output "$RESOLVED" --merge-report /tmp/fc9_merge_report.json \
  --glossary backend-app/app/data/glossary.json || { echo "FAIL A3 (embedding 실패 시 --no-embedding 재시도)"; \
  PYTHONPATH=scripts $VENV scripts/resolve_entities.py --input-dir "$V3" --output "$RESOLVED" \
    --merge-report /tmp/fc9_merge_report.json --glossary backend-app/app/data/glossary.json --no-embedding || { echo "FAIL A3 hard"; exit 3; } ; }

# ── A4. U2 validator (domain/range 검증) ──
step "A4. U2 validator (ResolvedGraph 품질)"
PYTHONPATH=scripts $VENV -m lib.tbox validate --input "$RESOLVED" --profile report > /tmp/fc9_validation.txt 2>&1
echo "ERROR: $(grep -c '^ERROR' /tmp/fc9_validation.txt 2>/dev/null||echo 0), 상위:"; head -8 /tmp/fc9_validation.txt

# ── A5. gold 채점 (U3, 추출 정확도 정량화) ──
step "A5. U3 gold 채점 (eval_extraction, fact-level F1)"
PYTHONPATH=scripts $VENV scripts/eval_extraction.py --gold gold \
  --extracted-dir "$V3" --glob '*.graph.json' --category P --report-json /tmp/fc9_extract_score.json \
  2>&1 | tail -20 || echo "WARN A5 (gold 매칭 — document_id 정합 확인)"

step "A6. Phase A 완료 — Phase B(Neptune/배포/eval)는 VPC 내부 실행 필요. fc9-phase2-handoff.md 참조"
echo "Phase A 산출물: $V3 (build_graph), $RESOLVED (ER), /tmp/fc9_*.json/txt"
