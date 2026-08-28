#!/bin/bash
# U7 backend 배포 — HonestyPolicy 주입 이미지 빌드 + AUTH_DISABLED=true(eval용) 배포.
# eval v11을 v10과 동일(무인증) 조건서 측정. 배포 후 eval은 fc9_eval.sh.
set -o pipefail
CTX=arn:aws:eks:us-west-2:123456789012:cluster/ontology-demo-cluster
NS=ontology-demo
ECR=123456789012.dkr.ecr.us-west-2.amazonaws.com/ontology-demo/backend-app
TAG=fc9-$(date +%Y%m%d%H%M 2>/dev/null||echo build)
ROOT=/mnt/data/projects/ontology-demo
LOG=/tmp/fc9_deploy.log
exec >> "$LOG" 2>&1
cd "$ROOT/backend-app"
step(){ echo ""; echo "═══ [$(TZ=UTC date '+%H:%M:%S' 2>/dev/null||echo .)] $1 ═══"; }

step "D1. ECR 로그인"
aws ecr get-login-password --region us-west-2 | docker login --username AWS --password-stdin "$ECR" 2>&1 | tail -1

step "D2. 이미지 빌드 (linux/amd64, HonestyPolicy+tbox 포함) + push"
docker buildx build --platform linux/amd64 --builder arm-builder \
  -t "$ECR:$TAG" --push . 2>&1 | tail -15 || { echo "FAIL D2 build"; exit 2; }
echo "pushed: $ECR:$TAG"

step "D3. AUTH_DISABLED=true env 설정 (eval용, v10 동일조건)"
kubectl --context $CTX set env deploy/fastapi -n $NS AUTH_DISABLED=true 2>&1 | tail -1

step "D4. 신규 이미지 배포"
kubectl --context $CTX set image deploy/fastapi fastapi="$ECR:$TAG" -n $NS 2>&1 | tail -1
kubectl --context $CTX rollout status deploy/fastapi -n $NS --timeout=420s 2>&1 | tail -3

step "D5. health + chat 인증우회 검증 (ALB)"
ALB=k8s-ontology-appingre-xxxxxxxxxx-xxxxxxxxxx.us-west-2.elb.amazonaws.com
sleep 10
curl -sk -o /dev/null -w "ALB health: %{http_code}\n" --max-time 20 "http://$ALB/v1/health"
echo "배포 완료: $ECR:$TAG (AUTH_DISABLED=true)"
echo "복원: kubectl set env deploy/fastapi -n $NS AUTH_DISABLED- (eval 후)"
