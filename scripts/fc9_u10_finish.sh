#!/bin/bash
# U10 P1 마무리 — build 완료 대기 → 품질게이트(C1~C3) → resolve(embedding+R1)
#   → auth off → 클린 동시재적재(OpenSearch recreate + Neptune drop, C5) → 정합검증 → eval v15 → auth 복원.
set -o pipefail
VENV=/tmp/u2venv/bin/python
ROOT=/mnt/data/projects/ontology-demo
CTX=arn:aws:eks:us-west-2:123456789012:cluster/ontology-demo-cluster
NS=ontology-demo
V3=/mnt/data/v3-graph-ready
RESOLVED=/mnt/data/v3-graph-ready-resolved/_resolved.json
CF=xxxxxxxxxxxxxx.cloudfront.net
LOG=/tmp/u10_finish.log
exec >> "$LOG" 2>&1
cd "$ROOT"
step(){ echo ""; echo "═══ [$(TZ=UTC date '+%H:%M:%S' 2>/dev/null||echo .)] $1 ═══"; }

step "0. build 완료 대기 (39 + TOTAL)"
for i in $(seq 1 900); do
  n=$(ls $V3/*.graph.json 2>/dev/null | wc -l)
  grep -q '^TOTAL:' /tmp/u10_build.log 2>/dev/null && [ "$n" -ge 39 ] && break
  sleep 60
done
n=$(ls $V3/*.graph.json 2>/dev/null | wc -l)
echo "build: $n/39, Failed parse: $(grep -c 'Failed to parse entity' /tmp/u10_build.log)"
[ "$n" -lt 39 ] && { echo "FAIL build 미완"; exit 1; }

step "0b. 빌드 품질게이트 (C1 결정론 제외 — dangling/broken/법령Policy/문서당Policy)"
$VENV - <<'PY'
import json, glob, sys
from collections import Counter
te=tr=td=tb=0; law_policy=0; multi_policy=0; docs=0
for f in glob.glob('/mnt/data/v3-graph-ready/*.graph.json'):
    g=json.load(open(f)); docs+=1
    ids={e['id'] for e in g['entities']}
    td+=sum(1 for r in g['relations'] if r['source_id'] not in ids or r['target_id'] not in ids)
    tb+=sum(1 for e in g['entities'] if str(e['id']).startswith('EntityType.') or str(e['type']).startswith('EntityType.'))
    pol=[e for e in g['entities'] if e['type']=='Policy']
    is_law=any(k in f for k in ('법','세칙','시행령','시행규칙','관리법','의료법'))
    if is_law and len(pol)>0: law_policy+=len(pol)
    if (not is_law) and len(pol)>1: multi_policy+=1
    te+=len(g['entities']); tr+=len(g['relations'])
print(f"  docs={docs} ents={te} rels={tr} dangling={td} broken={tb} 법령Policy={law_policy} 다중Policy문서={multi_policy}")
sys.exit(1 if (td>0 or tb>0 or law_policy>0 or multi_policy>0) else 0)
PY
[ $? -ne 0 ] && { echo "FAIL 빌드 품질게이트(C2/C3 위반 또는 dangling/broken>0)"; exit 2; }
echo "빌드 게이트 통과"

step "1. resolve (embedding + R1 필터)"
mkdir -p "$(dirname $RESOLVED)"
PYTHONPATH=scripts $VENV scripts/resolve_entities.py \
  --input-dir "$V3" --output "$RESOLVED" --merge-report /tmp/u10_merge.json \
  --glossary backend-app/app/data/glossary.json --tbox tbox.yaml \
  || { echo "FAIL resolve(embedding) — no-embedding 폴백"; \
  PYTHONPATH=scripts $VENV scripts/resolve_entities.py --input-dir "$V3" --output "$RESOLVED" \
    --merge-report /tmp/u10_merge.json --glossary backend-app/app/data/glossary.json --tbox tbox.yaml --no-embedding \
    || { echo "FAIL resolve hard"; exit 3; }; }

step "2. validator (R1/R3=0 기대)"
PYTHONPATH=scripts $VENV -m lib.tbox validate --input "$RESOLVED" --profile report > /tmp/u10_val.txt 2>&1
echo "ERROR 총: $(grep -c '^ERROR' /tmp/u10_val.txt)"
grep '^ERROR' /tmp/u10_val.txt | grep -oE '\[R[0-9]\]' | sort | uniq -c

step "2b. resolved 품질 + 법령Policy 0 최종 확인"
$VENV - <<'PY'
import json
from collections import Counter
g=json.load(open('/mnt/data/v3-graph-ready-resolved/_resolved.json'))
ents=g['entities']; rels=g['relations']
ids={e['id'] for e in ents}
d=sum(1 for r in rels if r['source_id'] not in ids or r['target_id'] not in ids)
tc=Counter(e['type'] for e in ents)
law_pol=sum(1 for e in ents if e['type']=='Policy' and any(k in e.get('label','') for k in ('법률','시행령','시행규칙','세칙','관리법','의료법')))
print(f"  ents={len(ents)} rels={len(rels)} dangling={d} Policy={tc.get('Policy')} 법령Policy={law_pol} Calc={tc.get('Calculation')} SIMILAR_TO={Counter(r['type'] for r in rels).get('SIMILAR_TO')}")
PY

step "3. auth off"
kubectl --context $CTX set env deploy/fastapi -n $NS AUTH_DISABLED=true 2>&1 | tail -1
kubectl --context $CTX rollout status deploy/fastapi -n $NS --timeout=300s 2>&1 | tail -1

step "4. Phase B (OpenSearch recreate + Neptune drop 동시적재, C5)"
bash scripts/fc9_phase_b_pod.sh
echo "Phase B 로그: /tmp/fc9_phaseb.log"
kubectl --context $CTX rollout status deploy/fastapi -n $NS --timeout=300s 2>&1 | tail -1
sleep 20

step "5. eval v15 (CloudFront, 라벨매칭 eval)"
$VENV -m pip install -q httpx 2>&1 | tail -1
API_URL="https://$CF/v1/chat" ALB_HOST=$CF $VENV scripts/run_evaluation.py --output /tmp/eval_results_v15.json 2>&1 | tail -20

step "6. auth 복원"
kubectl --context $CTX set env deploy/fastapi -n $NS AUTH_DISABLED- 2>&1 | tail -1

step "7. 점수 비교"
$VENV - <<'PY'
import json
def official(d):
    r=d.get('results') or []
    return sum(1 for x in r if not any(dd['status']=='FAIL' for dd in x['dimensions'])), len(r)
for v in ('v11','v14','v15'):
    for p in (f'/tmp/eval_results_{v}.json', f'scripts/eval_results_{v}.json'):
        try: d=json.load(open(p)); break
        except: d=None
    if d:
        p,t=official(d)
        print(f"  {v}: 공식 {p}/{t} | {d.get('summary',{}).get('dimension_pass_rates',{})}")
PY
echo "═══ U10 P1 완료 — eval v15, auth 복원 ═══"
