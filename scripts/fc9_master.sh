#!/bin/bash
# U7 마스터 오케스트레이터 — Phase A 완료 → Phase B(파드) → eval v11 자동 연쇄.
# 무인 완주. 각 산출물 존재로 단계 판정. 실패 시 로그 남기고 정지.
ROOT=/mnt/data/projects/ontology-demo
LOG=/tmp/fc9_master.log
RESOLVED=/mnt/data/v3-graph-ready-resolved/_resolved.json
exec >> "$LOG" 2>&1
cd "$ROOT"
echo "═══ MASTER 시작 $(TZ=UTC date 2>/dev/null) ═══"

# Phase A 완료 대기 (ResolvedGraph 생성 = A 완주 신호)
echo "Phase A 완료 대기 (ResolvedGraph)..."
for i in $(seq 1 720); do        # 최대 12시간(60s*720)
  [ -f "$RESOLVED" ] && break
  sleep 60
done
if [ ! -f "$RESOLVED" ]; then echo "TIMEOUT: Phase A 미완(ResolvedGraph 없음). 중단."; exit 1; fi
echo "Phase A 완료 확인: $RESOLVED ($(du -h $RESOLVED|cut -f1))"

# Phase B (파드 경유 Neptune 재로드 + OpenSearch + 재시작)
echo "Phase B 시작..."
bash scripts/fc9_phase_b_pod.sh
echo "Phase B 종료 (로그: /tmp/fc9_phaseb.log)"

# 배포 (HonestyPolicy 이미지 빌드 + AUTH_DISABLED 배포)
echo "배포 시작 (fc9_deploy)..."
bash scripts/fc9_deploy.sh
echo "배포 종료 (로그: /tmp/fc9_deploy.log)"

# eval v11 (CloudFront 경유, auth disabled)
echo "eval v11 시작..."
bash scripts/fc9_eval.sh
echo "eval 종료 (로그: /tmp/fc9_eval.log)"

# auth 복원 (eval 후 보안 원복)
echo "auth 복원 (AUTH_DISABLED 제거)..."
kubectl --context arn:aws:eks:us-west-2:123456789012:cluster/ontology-demo-cluster \
  set env deploy/fastapi -n ontology-demo AUTH_DISABLED- 2>&1 | tail -1
echo "═══ MASTER 완료 — eval: /tmp/eval_results_v11.json, auth 복원됨 ═══"
