#!/bin/bash
# FC9 frontend(nextjs) 배포 — buildx linux/amd64 → ECR push → set image. 백엔드 deploy 패턴 복제.
set -o pipefail
CTX=arn:aws:eks:us-west-2:123456789012:cluster/ontology-demo-cluster
NS=ontology-demo
ECR=123456789012.dkr.ecr.us-west-2.amazonaws.com/ontology-demo/frontend-app
TAG=fc9-$(date +%Y%m%d%H%M 2>/dev/null||echo build)
ROOT=/mnt/data/projects/ontology-demo
LOG=/tmp/fc9_deploy_frontend.log
exec >> "$LOG" 2>&1
cd "$ROOT/frontend-app"
step(){ echo ""; echo "═══ [$(TZ=UTC date '+%H:%M:%S' 2>/dev/null||echo .)] $1 ═══"; }

step "F1. ECR 로그인"
aws ecr get-login-password --region us-west-2 | docker login --username AWS --password-stdin "$ECR" 2>&1 | tail -1

step "F2. 이미지 빌드 (linux/amd64) + push"
docker buildx build --platform linux/amd64 --builder arm-builder \
  -t "$ECR:$TAG" --push . 2>&1 | tail -15 || { echo "FAIL F2 build"; exit 2; }
echo "pushed: $ECR:$TAG"

step "F3. 신규 이미지 배포"
kubectl --context $CTX set image deploy/nextjs nextjs="$ECR:$TAG" -n $NS 2>&1 | tail -1
kubectl --context $CTX rollout status deploy/nextjs -n $NS --timeout=420s 2>&1 | tail -3
echo "배포 완료: $ECR:$TAG"
