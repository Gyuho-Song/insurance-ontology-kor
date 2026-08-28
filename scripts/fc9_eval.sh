#!/bin/bash
# U7 eval v11 — deployed backend(ALB) 기준. Phase B(재로드+배포) 후 실행.
set -o pipefail
VENV=/tmp/u2venv/bin/python
ROOT=/mnt/data/projects/ontology-demo
LOG=/tmp/fc9_eval.log
# ALB는 이 환경서 직접 불가(SG: CloudFront만). eval은 CloudFront 경유. backend AUTH_DISABLED=true 전제.
CF=xxxxxxxxxxxxxx.cloudfront.net
exec >> "$LOG" 2>&1
cd "$ROOT"
echo "═══ eval v11 (CloudFront=$CF, https) ═══"
$VENV -m pip install -q httpx 2>&1 | tail -1
# run_evaluation은 http://{ALB_HOST}/v1/chat → API_URL로 https CloudFront 직접 지정
API_URL="https://$CF/v1/chat" ALB_HOST=$CF $VENV scripts/run_evaluation.py --output /tmp/eval_results_v11.json 2>&1 | tail -25
echo "═══ eval v11 완료 → /tmp/eval_results_v11.json ═══"
# v10 대비 비교
$VENV -c "
import json
try:
    v11=json.load(open('/tmp/eval_results_v11.json'))
    s=v11.get('summary',{})
    print('v11 overall:', s.get('total_scenarios'), s.get('dimension_pass_rates',{}))
except Exception as e: print('eval 결과 파싱:', e)
"
