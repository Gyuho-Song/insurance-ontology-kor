# Ontology GraphRAG Demo — 완전 배포 가이드

이 문서를 따라하면 새 AWS 리전에 데모 환경을 완전히 재현할 수 있습니다.

## 전체 배포 흐름

```
Phase 1: 인프라 배포 (CDK)
  ┌──────────────┐
  │  VPC Stack   │  10.0.0.0/16, 3-tier, NAT GW, VPC Endpoints
  └──────┬───────┘
         │
  ┌──────┴───────┐
  │  Data Stack  │  Neptune Serverless, OpenSearch Serverless, S3 × 2
  └──────┬───────┘
         │
  ┌──────┴───────┐
  │  EKS Stack   │  EKS 1.33, ALB Controller, ECR × 2, IRSA
  └──────────────┘

Phase 2: 데이터 로딩 (Python 스크립트, VPC 내부)
  ① OpenSearch 인덱스 생성 (create_opensearch_index.py)
  ② Neptune 그래프 + OpenSearch 벡터 로딩 (load_v2_data.py)
  ③ 고립 노드 연결 (connect_isolated_nodes.py)

Phase 3: 애플리케이션 배포 (Docker → ECR → EKS)
  ① Docker 이미지 빌드 (backend-app, frontend-app)
  ② ECR 푸시
  ③ K8s Deployment 업데이트
```

---

## 사전 요구사항

| 도구 | 버전 | 용도 |
|------|------|------|
| AWS CLI v2 | latest | 인프라 관리 |
| Node.js | 20+ | CDK |
| AWS CDK CLI | 2.175+ | `npm install -g aws-cdk` |
| Python | 3.12+ | 데이터 로딩 스크립트 |
| Docker | latest | 앱 이미지 빌드 |
| kubectl | latest | EKS 접근 |

```bash
# 자격증명 확인
aws sts get-caller-identity
```

---

## Phase 1: 인프라 배포 (CDK)

### 1-1. CDK Bootstrap (대상 리전에 최초 1회)

```bash
export CDK_DEFAULT_ACCOUNT=$(aws sts get-caller-identity --query Account --output text)
export CDK_DEFAULT_REGION=us-east-1  # ← 배포 대상 리전

cdk bootstrap aws://$CDK_DEFAULT_ACCOUNT/$CDK_DEFAULT_REGION
```

### 1-2. 의존성 설치 + 환경 변수

```bash
cd cdk-app
npm install

export CDK_DEFAULT_ACCOUNT=$(aws sts get-caller-identity --query Account --output text)
export CDK_DEFAULT_REGION=us-east-1  # ← 배포 대상 리전
```

### 1-3. 환경 설정 (선택)

`lib/config/environments.ts`에서 조정 가능:

| 설정 | 기본값 | 설명 |
|------|--------|------|
| `vpc.maxAzs` | 2 | 가용 영역 수 |
| `vpc.natGateways` | 1 | NAT Gateway 수 (비용 절감: 1) |
| `eks.instanceType` | m5.xlarge | 노드 인스턴스 타입 |
| `eks.minSize/maxSize/desiredSize` | 2/4/2 | 노드 스케일링 |
| `neptune.minCapacity` | 2.5 | Neptune 최소 NCU |
| `neptune.maxCapacity` | 128 | Neptune 최대 NCU |

### 1-4. CDK Synth (검증)

```bash
npx cdk synth --all
```

3개 스택 확인: `ontology-demo-vpc`, `ontology-demo-data`, `ontology-demo-eks`

### 1-5. 배포

```bash
npx cdk deploy --all --require-approval never
```

배포 순서: VPC (~3분) → Data (~15-20분) → EKS (~15-20분)

**총 소요: ~30-40분**

### 1-6. 인프라 검증

```bash
# EKS kubeconfig 설정
aws eks update-kubeconfig \
  --name ontology-demo-cluster \
  --region $CDK_DEFAULT_REGION

# EKS 클러스터
aws eks describe-cluster --name ontology-demo-cluster \
  --region $CDK_DEFAULT_REGION \
  --query 'cluster.{version:version,status:status}'

# 노드
kubectl get nodes -o wide

# Neptune
aws neptune describe-db-clusters \
  --db-cluster-identifier ontology-demo-neptune \
  --region $CDK_DEFAULT_REGION \
  --query 'DBClusters[0].{Status:Status,Endpoint:Endpoint,Port:Port}'

# OpenSearch
aws opensearchserverless list-collections \
  --region $CDK_DEFAULT_REGION \
  --query "collectionSummaries[?name=='ontology-embeddings'].{name:name,status:status}"

# ECR
aws ecr describe-repositories \
  --region $CDK_DEFAULT_REGION \
  --repository-names ontology-demo/backend-app ontology-demo/frontend-app \
  --query 'repositories[].repositoryUri'

# S3
aws s3 ls | grep ontology-demo

# ConfigMap (엔드포인트 확인)
kubectl get configmap app-config -n ontology-demo -o yaml
```

### 1-7. 엔드포인트 수집 (Phase 2에 필요)

```bash
# Neptune 엔드포인트
NEPTUNE_ENDPOINT=$(aws neptune describe-db-clusters \
  --db-cluster-identifier ontology-demo-neptune \
  --region $CDK_DEFAULT_REGION \
  --query 'DBClusters[0].Endpoint' --output text)
NEPTUNE_PORT=$(aws neptune describe-db-clusters \
  --db-cluster-identifier ontology-demo-neptune \
  --region $CDK_DEFAULT_REGION \
  --query 'DBClusters[0].Port' --output text)

# OpenSearch 엔드포인트
OPENSEARCH_ENDPOINT=$(aws opensearchserverless batch-get-collection \
  --names ontology-embeddings \
  --region $CDK_DEFAULT_REGION \
  --query 'collectionDetails[0].collectionEndpoint' --output text)

echo "NEPTUNE_ENDPOINT=$NEPTUNE_ENDPOINT"
echo "NEPTUNE_PORT=$NEPTUNE_PORT"
echo "OPENSEARCH_ENDPOINT=$OPENSEARCH_ENDPOINT"
```

---

## Phase 2: 데이터 로딩 (VPC 내부에서 실행)

### 데이터 소스: v2 graph-ready JSON

모든 데이터의 원본은 **v2 graph-ready JSON 파일** (39개)입니다. Neptune 백업/복원이 아닙니다.

```
원본 PDF (보험 상품 요약서 39개 + 법규)
  ↓ Bedrock Opus (pdf_to_markdown.py)
Markdown
  ↓ Bedrock Sonnet (extract_entities_v2.py, tool_use)
v2 graph-ready JSON ← 이것이 데이터 원본 (S3에 보관)
  ↓ load_v2_data.py
  ├→ Neptune (Gremlin upsert)  — 그래프 노드/엣지
  └→ OpenSearch (k-NN index)   — 벡터 임베딩
```

JSON 파일 구조 (문서 1개 = 파일 1개):
```json
{
  "document_id": "한화생명 H보장보험1 무배당 요약서 20260201",
  "product_name": "...",
  "entities": [
    {
      "id": "Policy#hwl_h보장보험1",
      "type": "Policy",              → Neptune vertex label
      "label": "한화생명 H보장보험Ⅰ",  → Neptune property
      "properties": { "provider": "한화생명", ... },
      "provenance": { "source_text": "...", "confidence": 0.95 }
    }
  ],
  "relations": [
    {
      "source_id": "Policy#...",     → Neptune edge OUT
      "target_id": "Coverage#...",   → Neptune edge IN
      "type": "HAS_COVERAGE",        → Neptune edge label
      "provenance": { ... }
    }
  ]
}
```

`load_v2_data.py`가 이 JSON을 읽어서:
- `entity` → Neptune vertex (properties를 flat하게 펼침, 배열은 JSON 문자열)
- `relation` → Neptune edge
- `entity` + Bedrock Titan 임베딩 → OpenSearch 벡터 문서

**JSON만 있으면 Neptune/OpenSearch 데이터를 100% 재현 가능합니다.**

### 중요: VPC 접근

Neptune과 OpenSearch Serverless는 **private subnet에 있으며 VPC 엔드포인트를 통해서만 접근 가능**합니다. 데이터 로딩 스크립트는 반드시 VPC 내부에서 실행해야 합니다.

**방법 A: EKS 워커 노드에 SSM으로 접속**
```bash
INSTANCE_ID=$(aws ec2 describe-instances \
  --filters "Name=tag:eks:cluster-name,Values=ontology-demo-cluster" \
            "Name=instance-state-name,Values=running" \
  --query 'Reservations[0].Instances[0].InstanceId' --output text \
  --region $CDK_DEFAULT_REGION)

aws ssm start-session --target $INSTANCE_ID --region $CDK_DEFAULT_REGION
```

**방법 B: 임시 EC2 인스턴스를 AppPrivate 서브넷에 생성**

**방법 C: 현재 환경이 이미 VPC 내부라면 (Cloud9, Bastion 등) 그대로 실행**

### 2-1. 스크립트 의존성 설치

```bash
pip3 install boto3 requests requests-aws4auth
```

### 2-2. 소스 JSON 데이터 다운로드 (S3)

v2 graph-ready JSON 39개 파일이 S3에 보관되어 있습니다:

```bash
mkdir -p /tmp/v2-graph-ready

# 원본 S3에서 다운로드 (us-west-2)
aws s3 sync \
  s3://ontology-demo-parsed-data-123456789012/v2-graph-ready/ \
  /tmp/v2-graph-ready/ \
  --region us-west-2

# 확인: 39개 JSON (+ 메타데이터 3개)
ls /tmp/v2-graph-ready/*.json | wc -l   # 42 (39 데이터 + 3 manifest)
```

새 환경의 parsed-data 버킷에도 복사 (보관용):
```bash
aws s3 sync /tmp/v2-graph-ready/ \
  s3://ontology-demo-parsed-data-${CDK_DEFAULT_ACCOUNT}/v2-graph-ready/ \
  --region $CDK_DEFAULT_REGION
```

### 2-3. OpenSearch 인덱스 생성

```bash
cd /path/to/ontology-demo

# 환경 변수 설정
export AWS_REGION=$CDK_DEFAULT_REGION
export OPENSEARCH_ENDPOINT=$OPENSEARCH_ENDPOINT  # Phase 1-7에서 수집

python3 scripts/create_opensearch_index.py
```

예상 출력:
```
Endpoint: https://xxx.us-east-1.aoss.amazonaws.com
Region:   us-east-1
Index:    ontology-vectors

Creating index 'ontology-vectors' with k-NN + Nori mappings...
  Created successfully!

Index settings:
  - k-NN: enabled (HNSW, nmslib, cosinesimil)
  - Embedding dimension: 1536 (Bedrock Titan v2)
  - Text analyzer: Nori (Korean morphological)
  - node_label.raw: keyword (exact match/wildcard)
```

### 2-4. Neptune + OpenSearch 데이터 로딩

```bash
# 환경 변수 설정
export AWS_REGION=$CDK_DEFAULT_REGION
export NEPTUNE_ENDPOINT=$NEPTUNE_ENDPOINT     # Phase 1-7에서 수집
export NEPTUNE_PORT=$NEPTUNE_PORT
export OPENSEARCH_ENDPOINT=$OPENSEARCH_ENDPOINT
export INPUT_DIR=/tmp/v2-graph-ready           # 2-2에서 다운로드한 경로

# 전체 로딩 (Neptune + OpenSearch, ~20-30분)
python3 scripts/load_v2_data.py --force
```

옵션:
```bash
python3 scripts/load_v2_data.py --neptune-only     # Neptune만
python3 scripts/load_v2_data.py --opensearch-only   # OpenSearch만
python3 scripts/load_v2_data.py --file "한화생명*"  # 특정 파일만
python3 scripts/load_v2_data.py --drop-v1           # 기존 데이터 전부 삭제 후 로딩
```

예상 결과:
```
Complete: 39 files, Errors: 0
Neptune: ~1,889 vertices, ~1,771 edges
OpenSearch: ~1,952 vectors indexed
```

### 2-5. 고립 노드 연결

```bash
export AWS_REGION=$CDK_DEFAULT_REGION
export NEPTUNE_ENDPOINT=$NEPTUNE_ENDPOINT
export NEPTUNE_PORT=$NEPTUNE_PORT

python3 scripts/connect_isolated_nodes.py
```

예상 결과:
```
Total edges created: ~44
Total failures: 0
Remaining isolated nodes: 0
```

### 2-6. 데이터 로딩 검증

```bash
# Neptune: 노드 수 확인 (VPC 내부에서)
# Gremlin HTTP API로 직접 확인
curl -s -X POST "https://${NEPTUNE_ENDPOINT}:${NEPTUNE_PORT}/gremlin" \
  -H "Content-Type: application/json" \
  -d '{"gremlin": "g.V().count()"}' \
  --aws-sigv4 "aws:amz:${AWS_REGION}:neptune-db" \
  --insecure \
  | python3 -m json.tool

# OpenSearch: 문서 수 확인
# (opensearch-py 또는 curl + SigV4 필요)
```

---

## Phase 3: 애플리케이션 배포 (Docker → ECR → EKS)

### 3-1. ECR 로그인

```bash
aws ecr get-login-password --region $CDK_DEFAULT_REGION | \
  docker login --username AWS \
  --password-stdin $CDK_DEFAULT_ACCOUNT.dkr.ecr.$CDK_DEFAULT_REGION.amazonaws.com
```

### 3-2. Backend (FastAPI) 이미지 빌드 & 푸시

```bash
cd backend-app

docker build -t ontology-demo/backend-app .
docker tag ontology-demo/backend-app:latest \
  $CDK_DEFAULT_ACCOUNT.dkr.ecr.$CDK_DEFAULT_REGION.amazonaws.com/ontology-demo/backend-app:latest
docker push \
  $CDK_DEFAULT_ACCOUNT.dkr.ecr.$CDK_DEFAULT_REGION.amazonaws.com/ontology-demo/backend-app:latest
```

### 3-3. Frontend (Next.js) 이미지 빌드 & 푸시

```bash
cd frontend-app

docker build -t ontology-demo/frontend-app .
docker tag ontology-demo/frontend-app:latest \
  $CDK_DEFAULT_ACCOUNT.dkr.ecr.$CDK_DEFAULT_REGION.amazonaws.com/ontology-demo/frontend-app:latest
docker push \
  $CDK_DEFAULT_ACCOUNT.dkr.ecr.$CDK_DEFAULT_REGION.amazonaws.com/ontology-demo/frontend-app:latest
```

### 3-4. K8s Deployment 업데이트

CDK가 이미 ECR 이미지를 참조하는 Deployment를 생성했으므로, 이미지 푸시 후 rollout:

```bash
kubectl rollout restart deployment/fastapi -n ontology-demo
kubectl rollout restart deployment/nextjs -n ontology-demo

# 롤아웃 상태 확인
kubectl rollout status deployment/fastapi -n ontology-demo
kubectl rollout status deployment/nextjs -n ontology-demo
```

### 3-5. 기본 검증

```bash
# Pod 상태 (2/2 Running)
kubectl get pods -n ontology-demo -o wide

# Ingress / ALB 확인
kubectl get ingress -n ontology-demo

# ALB DNS 가져오기
ALB_DNS=$(kubectl get ingress app-ingress -n ontology-demo \
  -o jsonpath='{.status.loadBalancer.ingress[0].hostname}')
echo "Frontend: https://$ALB_DNS/"
echo "API:      https://$ALB_DNS/v1/docs"

# API 헬스체크 (-k: self-signed cert 허용)
curl -sk https://$ALB_DNS/v1/health | python3 -m json.tool

# HPA
kubectl get hpa -n ontology-demo
```

### 3-6. E2E 평가: 128 시나리오 테스트

전체 시스템이 정상 동작하는지 128개 시나리오로 자동 검증합니다.

**평가 5개 차원:**

| 차원 | 검증 내용 |
|------|----------|
| Intent | 질문 의도 분류 정확도 |
| Vector | 벡터 검색으로 올바른 Policy 노드 진입 |
| Template | 올바른 Gremlin 템플릿 선택 |
| Subgraph | 필요한 노드 타입이 서브그래프에 포함 |
| Answer | LLM-as-a-Judge (Sonnet)로 답변 품질 평가 |

**실행:**

```bash
# 환경 변수 설정
export ALB_HOST=$(kubectl get ingress app-ingress -n ontology-demo \
  -o jsonpath='{.status.loadBalancer.ingress[0].hostname}')
export AWS_REGION=$CDK_DEFAULT_REGION

# 전체 128 시나리오 실행 (~15분, concurrency=3)
python3 scripts/run_evaluation.py

# 빠른 검증 (LLM Judge 생략, ~8분)
python3 scripts/run_evaluation.py --skip-judge

# 카테고리별 실행
python3 scripts/run_evaluation.py --categories A B C

# 순차 실행 (디버깅용)
python3 scripts/run_evaluation.py --concurrency 1

# 결과 파일 지정
python3 scripts/run_evaluation.py --output eval_results.json
```

**시나리오 카테고리 (128개):**

| 카테고리 | 설명 | 시나리오 수 |
|----------|------|-----------|
| A | 보장 내용 조회 | ~15 |
| B | 면책/부담보 확인 | ~15 |
| C | 가입 자격 조건 | ~10 |
| D | 보험료 할인/환급 | ~10 |
| E | 특약 관련 | ~10 |
| F-L | 배당, 해약환급금, 계산, 비교 등 | ~40 |
| R | 법규 관련 질의 | ~15 |
| S | 보안/엣지 케이스 | ~13 |

**기준선 (us-west-2 환경):**
```
128 시나리오 중 92개 PASS (71.9%)
```

새 환경에서도 동일한 수준이면 배포 성공:
```bash
# 결과 확인
cat scripts/eval_results_*.json | python3 -c "
import json, sys
data = json.load(sys.stdin)
print(f'Total: {data[\"summary\"][\"total\"]}')
print(f'Pass:  {data[\"summary\"][\"passed\"]}')
print(f'Rate:  {data[\"summary\"][\"pass_rate\"]:.1%}')
"
```

---

## HTTPS / TLS 인증서 관리

ALB는 HTTPS:443만 리스닝하며, HTTP:80은 리스너가 없습니다 (응답 없음).

### 현재 구성
- **인증서**: Self-signed (ACM imported), 유효기간 1년
- **ACM ARN**: `arn:aws:acm:us-west-2:123456789012:certificate/00000000-0000-0000-0000-000000000000`
- **CDK 상수**: `cdk-app/lib/config/constants.ts` → `ACM_CERTIFICATE_ARN`

### 인증서 갱신 (만료 전)

```bash
# 1. 새 self-signed 인증서 생성
mkdir -p /tmp/ontology-certs
cat > /tmp/ontology-certs/openssl.cnf << 'CONF'
[req]
default_bits = 2048
prompt = no
distinguished_name = dn
req_extensions = v3_req
x509_extensions = v3_req

[dn]
CN = ontology-demo-alb

[v3_req]
subjectAltName = @alt_names
basicConstraints = CA:FALSE
keyUsage = digitalSignature, keyEncipherment

[alt_names]
DNS.1 = <ALB_HOSTNAME>
DNS.2 = *.us-west-2.elb.amazonaws.com
CONF

openssl req -x509 -nodes -days 365 -newkey rsa:2048 \
  -keyout /tmp/ontology-certs/tls.key \
  -out /tmp/ontology-certs/tls.crt \
  -config /tmp/ontology-certs/openssl.cnf

# 2. ACM에 재import (기존 ARN에 덮어쓰기)
aws acm import-certificate \
  --region us-west-2 \
  --certificate-arn arn:aws:acm:us-west-2:123456789012:certificate/00000000-0000-0000-0000-000000000000 \
  --certificate fileb:///tmp/ontology-certs/tls.crt \
  --private-key fileb:///tmp/ontology-certs/tls.key
```

### 커스텀 도메인으로 전환 시

커스텀 도메인이 있으면 ACM 퍼블릭 인증서를 사용하여 브라우저 경고 없이 운영 가능합니다:
```bash
# 1. ACM 퍼블릭 인증서 요청
aws acm request-certificate --domain-name demo.example.com \
  --validation-method DNS --region us-west-2

# 2. Route53 DNS 검증 후 constants.ts의 ACM_CERTIFICATE_ARN 업데이트
# 3. Ingress 재적용
```

---

## 전체 체크리스트

| # | 단계 | 확인 항목 | 상태 |
|---|------|----------|------|
| 1 | CDK Bootstrap | `cdk bootstrap` 완료 | [ ] |
| 2 | CDK Deploy | 3 스택 배포 완료 | [ ] |
| 3 | EKS Nodes | `kubectl get nodes` — 2 Ready | [ ] |
| 4 | Neptune | Status: available | [ ] |
| 5 | OpenSearch | Collection: ACTIVE | [ ] |
| 6 | ECR | 2 repos 생성 확인 | [ ] |
| 7 | S3 | 2 버킷 확인 | [ ] |
| 8 | OS Index | `ontology-vectors` 인덱스 생성 | [ ] |
| 9 | Neptune Load | ~1,889 vertices, ~1,771 edges | [ ] |
| 10 | OS Load | ~1,952 vectors | [ ] |
| 11 | Isolated Nodes | 0 remaining | [ ] |
| 12 | Backend ECR | 이미지 푸시 완료 | [ ] |
| 13 | Frontend ECR | 이미지 푸시 완료 | [ ] |
| 14 | Pods | fastapi 2/2, nextjs 2/2 Running | [ ] |
| 15 | ALB | Ingress ADDRESS 할당 | [ ] |
| 16 | Health | `/v1/health` 200 OK | [ ] |
| 17 | E2E 평가 | 128 시나리오 ~92/128 (71.9%+) | [ ] |

---

## 환경 삭제 (Teardown)

```bash
export CDK_DEFAULT_REGION=us-east-1  # 삭제할 리전

# CDK 스택 삭제 (역순: EKS → Data → VPC)
cd cdk-app
npx cdk destroy --all --force

# ECR 레포 수동 삭제 (RemovalPolicy.RETAIN)
aws ecr delete-repository --repository-name ontology-demo/backend-app \
  --force --region $CDK_DEFAULT_REGION
aws ecr delete-repository --repository-name ontology-demo/frontend-app \
  --force --region $CDK_DEFAULT_REGION
```

---

## 리소스 목록

| 리소스 | 이름 | 비고 |
|--------|------|------|
| VPC | 10.0.0.0/16 | 3-tier (Public/AppPrivate/DataPrivate) |
| NAT Gateway | × 1 | |
| VPC Endpoints | STS, ECR, ECR Docker, CW Logs, SSM, EC2, SQS, S3 | |
| Neptune Serverless | ontology-demo-neptune | 2.5-128 NCU, IAM auth |
| OpenSearch Serverless | ontology-embeddings | VECTORSEARCH, VPC endpoint |
| S3: parsed-data | ontology-demo-parsed-data-{account} | 그래프 데이터 JSON |
| S3: mock-cache | ontology-demo-mock-cache-{account} | 프론트엔드 캐시 |
| EKS Cluster | ontology-demo-cluster | v1.33, Private endpoint |
| Node Group | WorkerNodes | m5.xlarge × 2, AL2023 |
| ALB Controller | v2.8.2 | 자동 설치 |
| ECR: backend | ontology-demo/backend-app | RETAIN |
| ECR: frontend | ontology-demo/frontend-app | RETAIN |
| K8s Namespace | ontology-demo | |
| K8s Deployments | fastapi (×2), nextjs (×2) | |
| K8s Ingress | app-ingress | ALB internet-facing, HTTPS:443 only |
| ACM Certificate | self-signed (imported) | ALB TLS termination, 365일 유효 |
| K8s HPA | fastapi-hpa | CPU 70%, 2-6 replicas |
| IRSA: fastapi-sa | Neptune, OpenSearch, Bedrock, S3 | |
| IRSA: nextjs-sa | S3 mock-cache read | |

## 데이터 사양

| 항목 | 수치 |
|------|------|
| 소스 문서 | 39개 (보험 상품 요약서 + 법규) |
| Neptune 노드 수 | ~1,889 vertices |
| Neptune 엣지 수 | ~1,815 edges (1,771 + 44 isolated fix) |
| 엔티티 타입 | 12종 (Policy, Coverage, Exclusion 등) |
| 관계 타입 | 14종 (HAS_COVERAGE, EXCLUDED_IF 등) |
| OpenSearch 벡터 수 | ~1,952 documents |
| 벡터 차원 | 1536 (Bedrock Titan v2) |
| 인덱스 알고리즘 | HNSW (nmslib, cosinesimil) |
| 텍스트 분석기 | Nori (한국어 형태소) |

## 비용 추정 (월간)

| 리소스 | 예상 비용 |
|--------|----------|
| EKS Control Plane | ~$73 |
| EC2 m5.xlarge × 2 | ~$281 |
| NAT Gateway | ~$32 + 데이터 전송 |
| Neptune Serverless (idle 2.5 NCU) | ~$90 |
| OpenSearch Serverless (2 OCU min) | ~$346 |
| VPC Endpoints (7 interface) | ~$51 |
| S3, ECR | ~$5 |
| ALB | ~$16 + 데이터 전송 |
| **합계** | **~$894/월** |

## 주요 스크립트 목록

| 스크립트 | 용도 | Phase |
|----------|------|-------|
| `scripts/create_opensearch_index.py` | OpenSearch k-NN + Nori 인덱스 생성 | 2-3 |
| `scripts/load_v2_data.py` | Neptune 그래프 + OpenSearch 벡터 일괄 로딩 | 2-4 |
| `scripts/connect_isolated_nodes.py` | 고립 노드 → Regulation 노드 연결 | 2-5 |
| `scripts/run_evaluation.py` | 128 시나리오 E2E 평가 (5차원) | 3-6 |

환경 변수:
```bash
# Phase 2: 데이터 로딩
export AWS_REGION=us-east-1
export NEPTUNE_ENDPOINT=<neptune-endpoint>
export NEPTUNE_PORT=8182
export OPENSEARCH_ENDPOINT=https://<collection-id>.us-east-1.aoss.amazonaws.com
export INPUT_DIR=/tmp/v2-graph-ready

# Phase 3-6: E2E 평가
export ALB_HOST=<alb-dns-name>
```
