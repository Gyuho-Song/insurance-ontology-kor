#!/bin/bash
# U7 Phase B — fastapi 파드 경유 Neptune 재로드 + OpenSearch 재인덱싱 + eval.
# 전제: Phase A 완료(ResolvedGraph 존재). 파드는 VPC 내부(Neptune 도달 OK).
# 안전: snapshot 이미 있음(ontology-demo-presnap-YYYYMMDDHHMM). baseline 403/403.
set -o pipefail
CTX=arn:aws:eks:us-west-2:123456789012:cluster/ontology-demo-cluster
NS=ontology-demo
ROOT=/mnt/data/projects/ontology-demo
RESOLVED=/mnt/data/v3-graph-ready-resolved/_resolved.json
LOG=/tmp/fc9_phaseb.log
exec >> "$LOG" 2>&1
cd "$ROOT"
step(){ echo ""; echo "═══ [$(TZ=UTC date '+%H:%M:%S' 2>/dev/null||echo .)] $1 ═══"; }

# Ready 상태 파드만 선택 (rollout 중 terminating 파드 회피). 매 단계 직전 재조회 권장.
get_ready_pod(){
  kubectl --context $CTX get pods -n $NS -l app=fastapi \
    --field-selector=status.phase=Running \
    -o jsonpath='{range .items[?(@.status.containerStatuses[0].ready==true)]}{.metadata.name}{"\n"}{end}' 2>/dev/null | head -1
}
# rollout 안정 대기 후 Ready 파드 확보
kubectl --context $CTX rollout status deploy/fastapi -n $NS --timeout=300s 2>&1 | tail -1
POD=$(get_ready_pod)
[ -z "$POD" ] && POD=$(kubectl --context $CTX get pods -n $NS --no-headers 2>/dev/null | grep fastapi | grep Running | head -1 | awk '{print $1}')
echo "대상 파드(Ready): $POD"
[ -z "$POD" ] && { echo "FAIL: Ready 파드 없음"; exit 1; }

# ── B0. ResolvedGraph 존재 확인 ──
step "B0. ResolvedGraph 확인"
[ -f "$RESOLVED" ] || { echo "FAIL: ResolvedGraph 없음 ($RESOLVED) — Phase A 미완"; exit 1; }
echo "ResolvedGraph: $(du -h $RESOLVED | cut -f1)"

# ── B1. 파드에 스크립트 + 데이터 복사 ──
step "B1. 파드로 복사 (load_v2_data, create_opensearch_index, ResolvedGraph)"
kubectl --context $CTX exec -n $NS $POD -- mkdir -p /tmp/fc9/in
kubectl --context $CTX cp scripts/load_v2_data.py $NS/$POD:/tmp/fc9/load_v2_data.py
kubectl --context $CTX cp scripts/create_opensearch_index.py $NS/$POD:/tmp/fc9/create_opensearch_index.py
kubectl --context $CTX cp scripts/connect_orphan_regulations.py $NS/$POD:/tmp/fc9/connect_orphan_regulations.py
# ⚠ load_v2_data가 '_' 시작 파일을 제외하므로 resolved.json(언더스코어 없이)으로 복사.
kubectl --context $CTX cp "$RESOLVED" $NS/$POD:/tmp/fc9/in/resolved.json

# ── B1.5 OpenSearch 인덱스 recreate (C5: 옛 빌드 잔존 제거) ──
# ⚠ load_v2_data는 document_id별 _delete_by_query만 하므로 옛 per-doc 인덱스(다른 id체계)가
#   잔존 → Neptune과 id 불일치. recreate로 완전 초기화 후 적재해야 두 저장소 id 일치(C5).
step "B1.5 OpenSearch 인덱스 recreate (옛 빌드 전량 제거)"
kubectl --context $CTX exec -n $NS $POD -- sh -c \
  'cd /tmp/fc9 && python create_opensearch_index.py --recreate 2>&1 | tail -8' || echo "WARN B1.5"

# ── B2. Neptune 재로드 (파드 안, INPUT_DIR=/tmp/fc9/in) ──
# --drop-v1: 기존 그래프 전체 삭제 후 신규 적재. --force: manifest 무시. OpenSearch는 위서 비워진 인덱스에 적재.
step "B2. Neptune+OpenSearch 적재 (파드 내 load_v2_data, drop-v1 + force)"
kubectl --context $CTX exec -n $NS $POD -- sh -c \
  'cd /tmp/fc9 && INPUT_DIR=/tmp/fc9/in python load_v2_data.py --file resolved.json --drop-v1 --force 2>&1 | tail -25' || echo "WARN B2"

# ── B2.5 Regulation 연결 (P1-B RC5): 고립 Regulation을 전 Policy에 GOVERNED_BY ──
step "B2.5 connect_orphan_regulations (고립 Regulation → Policy GOVERNED_BY)"
kubectl --context $CTX exec -n $NS $POD -- sh -c \
  'cd /tmp/fc9 && python connect_orphan_regulations.py 2>&1 | tail -12' || echo "WARN B2.5"

# ── B3. 재로드 후 count 검증 ──
# ⚠ 앱의 NeptuneClient(SigV4Auth) 사용. requests_aws4auth는 Neptune에서 403(서명 불일치) →
#   과거 'count=403'은 실제 HTTP 403을 count로 오인쇄한 것. 앱 client로 정확히 조회.
step "B3. Neptune count 검증 (앱 NeptuneClient/SigV4)"
kubectl --context $CTX exec -n $NS $POD -- sh -c 'cd /app && python -c "
import asyncio, os
from app.clients.neptune_client import NeptuneClient
async def main():
    c=NeptuneClient(os.environ[\"NEPTUNE_ENDPOINT\"], 8182); c.connect()
    for q in [\"g.V().count()\",\"g.E().count()\",\"g.V().groupCount().by(label)\"]:
        print(q, \"=>\", str(await c.execute(q))[:300])
asyncio.run(main())
" 2>&1' | grep -v "Insecure\|warn"

# ── B4. C5 정합성 검증 (Neptune id ≡ OpenSearch entity_id) ──
step "B4. C5 정합성 검증 (Neptune vertex == OpenSearch entity_id 샘플)"
kubectl --context $CTX exec -n $NS $POD -- sh -c 'cd /app && python -c "
import asyncio, os
from app.clients.neptune_client import NeptuneClient
from app.clients.opensearch_client import OpenSearchClient
async def main():
    nc=NeptuneClient(os.environ[\"NEPTUNE_ENDPOINT\"],8182); nc.connect()
    oc=OpenSearchClient(os.environ[\"OPENSEARCH_ENDPOINT\"])
    nv=(await nc.execute(\"g.V().count()\"))[0]
    osc=await asyncio.get_event_loop().run_in_executor(None, lambda: oc._client.count(index=\"ontology-vectors\"))
    print(\"Neptune V:\", nv, \"| OpenSearch docs:\", osc.get(\"count\"))
    # 샘플 Policy id가 양쪽에 동일 형식인지
    r=await asyncio.get_event_loop().run_in_executor(None, lambda: oc._client.search(index=\"ontology-vectors\", body={\"size\":2,\"query\":{\"term\":{\"node_type\":\"Policy\"}}}))
    for h in r[\"hits\"][\"hits\"]:
        eid=h[\"_source\"].get(\"entity_id\")
        cnt=(await nc.execute(f\"g.V(_x).count()\".replace(\"_x\", repr(eid))))[0]
        print(f\"  OS entity_id={eid} -> Neptune match={cnt}\")
asyncio.run(main())
" 2>&1' | grep -v "Insecure\|warn"

# ── B5. backend 재시작 (HonestyPolicy 주입은 이미지 빌드 필요 — 데이터만 우선 반영) ──
step "B5. backend rollout restart (신규 그래프 반영)"
kubectl --context $CTX rollout restart deploy/fastapi -n $NS 2>&1 | head -2
kubectl --context $CTX rollout status deploy/fastapi -n $NS --timeout=300s 2>&1 | tail -2

# ── B6. eval v11 (deployed backend, 파드 외부서 ALB 통해서도 가능하나 파드 내서) ──
step "B6. eval v11 준비 — run_evaluation은 ALB 통해 호출(이 환경서 실행 가능)"
echo "eval은 fc9_eval.sh에서 별도 실행(ALB_HOST 필요)"

step "Phase B 완료"
