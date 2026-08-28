#!/bin/bash
# U9 Phase 1 마무리 오케스트레이터 — build 완료 대기 → resolve(embedding) → validate
#   → auth off → Neptune 재로드(파드) → eval v12 → auth 복원. 무인 완주.
set -o pipefail
VENV=/tmp/u2venv/bin/python
ROOT=/mnt/data/projects/ontology-demo
CTX=arn:aws:eks:us-west-2:123456789012:cluster/ontology-demo-cluster
NS=ontology-demo
V3=/mnt/data/v3-graph-ready
RESOLVED=/mnt/data/v3-graph-ready-resolved/_resolved.json
CF=xxxxxxxxxxxxxx.cloudfront.net
LOG=/tmp/u9_finish.log
exec >> "$LOG" 2>&1
cd "$ROOT"
step(){ echo ""; echo "═══ [$(TZ=UTC date '+%H:%M:%S' 2>/dev/null||echo .)] $1 ═══"; }

step "0. build 완료 대기 (39 graph.json + TOTAL 라인)"
for i in $(seq 1 720); do   # 최대 12h
  n=$(ls $V3/*.graph.json 2>/dev/null | wc -l)
  grep -q '^TOTAL:' /tmp/u9_build2.log 2>/dev/null && [ "$n" -ge 39 ] && break
  sleep 60
done
n=$(ls $V3/*.graph.json 2>/dev/null | wc -l)
echo "build 완료: $n/39 docs, Failed parse: $(grep -c 'Failed to parse entity' /tmp/u9_build2.log)"
[ "$n" -lt 39 ] && { echo "FAIL: build 미완"; exit 1; }

step "0b. build 품질 게이트 (dangling/broken/calc)"
$VENV - <<'PY'
import json, glob, sys
te=tr=td=tb=tc=0
for f in glob.glob('/mnt/data/v3-graph-ready/*.graph.json'):
    g=json.load(open(f)); ids={e['id'] for e in g['entities']}
    td+=sum(1 for r in g['relations'] if r['source_id'] not in ids or r['target_id'] not in ids)
    tb+=sum(1 for e in g['entities'] if str(e['id']).startswith('EntityType.') or str(e['type']).startswith('EntityType.'))
    tc+=sum(1 for e in g['entities'] if e['type']=='Calculation')
    te+=len(g['entities']); tr+=len(g['relations'])
print(f"  ents={te} rels={tr} dangling={td} broken={tb} calc={tc}({tc*100//max(te,1)}%)")
sys.exit(1 if (td>0 or tb>0) else 0)
PY
[ $? -ne 0 ] && { echo "FAIL: build 품질 게이트(dangling/broken>0)"; exit 2; }

step "1. resolve_entities (embedding 복구판)"
mkdir -p "$(dirname $RESOLVED)"
PYTHONPATH=scripts $VENV scripts/resolve_entities.py \
  --input-dir "$V3" --output "$RESOLVED" --merge-report /tmp/u9_merge_report.json \
  --glossary backend-app/app/data/glossary.json || { echo "FAIL resolve(embedding) — no-embedding 폴백"; \
  PYTHONPATH=scripts $VENV scripts/resolve_entities.py --input-dir "$V3" --output "$RESOLVED" \
    --merge-report /tmp/u9_merge_report.json --glossary backend-app/app/data/glossary.json --no-embedding || { echo "FAIL resolve hard"; exit 3; }; }
echo "resolved: $(du -h $RESOLVED|cut -f1)"

step "2. validator (R3=0 기대)"
PYTHONPATH=scripts $VENV -m lib.tbox validate --input "$RESOLVED" --profile report > /tmp/u9_validation.txt 2>&1
echo "ERROR 총: $(grep -c '^ERROR' /tmp/u9_validation.txt), R3: $(grep -c 'R3' /tmp/u9_validation.txt)"
head -6 /tmp/u9_validation.txt

step "3. auth off (eval 위해 일시 비활성)"
kubectl --context $CTX set env deploy/fastapi -n $NS AUTH_DISABLED=true 2>&1 | tail -1
kubectl --context $CTX rollout status deploy/fastapi -n $NS --timeout=300s 2>&1 | tail -1

step "4. Phase B (파드 경유 Neptune 재로드 + OpenSearch + restart)"
bash scripts/fc9_phase_b_pod.sh
echo "Phase B 로그: /tmp/fc9_phaseb.log"
kubectl --context $CTX rollout status deploy/fastapi -n $NS --timeout=300s 2>&1 | tail -1
sleep 20

step "5. eval v12 (CloudFront)"
$VENV -m pip install -q httpx 2>&1 | tail -1
API_URL="https://$CF/v1/chat" ALB_HOST=$CF $VENV scripts/run_evaluation.py --output /tmp/eval_results_v12.json 2>&1 | tail -25

step "6. auth 복원"
kubectl --context $CTX set env deploy/fastapi -n $NS AUTH_DISABLED- 2>&1 | tail -1

step "7. v11 vs v12 비교"
$VENV - <<'PY'
import json
def load(p):
    try: return json.load(open(p))
    except: return None
def official(d):
    if not d: return None
    r=d.get('results') or []
    p=sum(1 for x in r if not any(dd['status']=='FAIL' for dd in x['dimensions']))
    return p, len(r)
for v in ('v11','v12'):
    d=load(f'/tmp/eval_results_{v}.json') or load(f'scripts/eval_results_{v}.json')
    o=official(d)
    if o: print(f"  {v}: 공식 {o[0]}/{o[1]}", d.get('summary',{}).get('dimension_pass_rates',{}))
PY
echo "═══ U9 finish 완료 — eval: /tmp/eval_results_v12.json, auth 복원됨 ═══"
