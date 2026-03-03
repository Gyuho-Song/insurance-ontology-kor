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

### 1-1. 환경 변수 설정 (필수)

> **주의**: `CDK_DEFAULT_REGION`과 `AWS_REGION`을 **모두** 설정해야 합니다.
> CDK는 `CDK_DEFAULT_REGION`을, boto3/AWS SDK는 `AWS_REGION`을 참조합니다.
> 둘 중 하나만 설정하면 다른 리전에 배포될 수 있습니다.

```bash
export CDK_DEFAULT_ACCOUNT=$(aws sts get-caller-identity --query Account --output text)
export CDK_DEFAULT_REGION=us-east-1  # ← 배포 대상 리전
export AWS_REGION=$CDK_DEFAULT_REGION  # ← 반드시 동일하게 설정
```

### 1-2. 의존성 설치

```bash
cd cdk-app
npm install
```

### 1-3. cdk.context.json 삭제

> **주의**: 다른 리전에서 사용한 `cdk.context.json`이 있으면 삭제하세요.
> CDK가 AZ(Availability Zone) 조회 결과를 캐싱하므로, 이전 리전의 AZ가 남아있으면
> 새 리전에서 배포가 실패합니다.

```bash
rm -f cdk.context.json
```

### 1-4. CDK Bootstrap (대상 리전에 최초 1회)

```bash
cdk bootstrap aws://$CDK_DEFAULT_ACCOUNT/$CDK_DEFAULT_REGION
```

### 1-5. 환경 설정 (선택)

`lib/config/environments.ts`에서 조정 가능:

| 설정 | 기본값 | 설명 |
|------|--------|------|
| `vpc.maxAzs` | 2 | 가용 영역 수 |
| `vpc.natGateways` | 1 | NAT Gateway 수 (비용 절감: 1) |
| `eks.instanceType` | m5.xlarge | 노드 인스턴스 타입 |
| `eks.minSize/maxSize/desiredSize` | 2/4/2 | 노드 스케일링 |
| `neptune.minCapacity` | 2.5 | Neptune 최소 NCU |
| `neptune.maxCapacity` | 128 | Neptune 최대 NCU |

### 1-6. CDK Synth (검증)

```bash
npx cdk synth --all
```

3개 스택 확인: `ontology-demo-vpc`, `ontology-demo-data`, `ontology-demo-eks`

### 1-7. 배포

```bash
npx cdk deploy --all --require-approval never
```

배포 순서: VPC (~3분) → Data (~15-20분) → EKS (~15-20분)

**총 소요: ~30-40분**

### 1-8. EKS 접근 설정

```bash
# kubeconfig 설정
aws eks update-kubeconfig \
  --name ontology-demo-cluster \
  --region $CDK_DEFAULT_REGION
```

> **EKS 접근 권한**: CDK가 클러스터를 생성하면 CDK 실행 역할이 자동으로 관리자 권한을 갖습니다.
> 다른 IAM 역할에서 kubectl을 사용하려면 **EKS 접근 항목**을 추가해야 합니다:
>
> ```bash
> # 1. 인증 모드를 API_AND_CONFIG_MAP으로 변경
> aws eks update-cluster-config \
>   --name ontology-demo-cluster \
>   --region $CDK_DEFAULT_REGION \
>   --access-config authenticationMode=API_AND_CONFIG_MAP
>
> # 2. 현재 역할의 접근 항목 생성
> CURRENT_ROLE_ARN=$(aws sts get-caller-identity --query Arn --output text | sed 's|:sts::|:iam::|;s|assumed-role/\(.*\)/.*|role/\1|')
>
> aws eks create-access-entry \
>   --cluster-name ontology-demo-cluster \
>   --region $CDK_DEFAULT_REGION \
>   --principal-arn $CURRENT_ROLE_ARN
>
> aws eks associate-access-policy \
>   --cluster-name ontology-demo-cluster \
>   --region $CDK_DEFAULT_REGION \
>   --principal-arn $CURRENT_ROLE_ARN \
>   --policy-arn arn:aws:eks::aws:cluster-access-policy/AmazonEKSClusterAdminPolicy \
>   --access-scope type=cluster
> ```

### 1-9. 인프라 검증

```bash
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

# ConfigMap (엔드포인트 + 필수 환경변수 확인)
kubectl get configmap app-config -n ontology-demo -o yaml
```

**ConfigMap 필수 항목 확인:**

CDK가 자동으로 생성하는 ConfigMap(`app-config`)에 아래 항목이 모두 있어야 합니다:

| 키 | 용도 | 예시 |
|----|------|------|
| `NEPTUNE_ENDPOINT` | Neptune 클러스터 엔드포인트 | `ontology-demo-neptune.cluster-xxx.us-east-1.neptune.amazonaws.com` |
| `NEPTUNE_PORT` | Neptune 포트 | `8182` |
| `OPENSEARCH_ENDPOINT` | OpenSearch Serverless 엔드포인트 | `https://xxx.us-east-1.aoss.amazonaws.com` |
| `PARSED_BUCKET` | 그래프 데이터 JSON 버킷 | `ontology-demo-parsed-data-{account}-{region}` |
| `MOCK_CACHE_BUCKET` | 프론트엔드 캐시 버킷 | `ontology-demo-mock-cache-{account}-{region}` |
| `AWS_REGION` | AWS 리전 | `us-east-1` |
| `BEDROCK_REGION` | SigV4 서명 리전 (Neptune/OpenSearch/Bedrock) | `us-east-1` |
| `GRAPHRAG_BACKEND_URL` | Next.js → FastAPI 내부 연결 URL | `http://fastapi.ontology-demo.svc.cluster.local:80` |

> **주의 — `BEDROCK_REGION`**: 백엔드 앱의 `config.py`에서 `bedrock_region` 기본값이 `us-west-2`입니다.
> Neptune/OpenSearch 클라이언트가 이 값으로 SigV4 서명을 하므로, 배포 리전과 다르면
> **Neptune 403, OpenSearch 403** 에러가 발생합니다. 반드시 배포 리전과 동일하게 설정하세요.
>
> **주의 — `GRAPHRAG_BACKEND_URL`**: Next.js 프론트엔드가 이 URL로 FastAPI 백엔드에 연결합니다.
> 설정하지 않으면 `http://localhost:8000`으로 fallback하여 **"백엔드 서비스에 연결할 수 없습니다"** 에러가 발생합니다.

### 1-10. 엔드포인트 수집 (Phase 2에 필요)

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
      "type": "Policy",
      "label": "한화생명 H보장보험Ⅰ",
      "properties": { "provider": "한화생명", ... },
      "provenance": { "source_text": "...", "confidence": 0.95 }
    }
  ],
  "relations": [
    {
      "source_id": "Policy#...",
      "target_id": "Coverage#...",
      "type": "HAS_COVERAGE",
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

**권장 방법: FastAPI 파드에서 실행 (kubectl exec)**

가장 간단하고 추가 인프라가 필요 없는 방법입니다. IRSA로 Neptune/OpenSearch/Bedrock 접근 권한이 이미 설정되어 있습니다.

```bash
# 1. 스크립트와 데이터를 tar로 묶기
tar czf /tmp/deploy-data.tar.gz scripts/ data/v2-graph-ready/

# 2. 파드로 복사
FASTAPI_POD=$(kubectl get pods -n ontology-demo -l app=fastapi -o jsonpath='{.items[0].metadata.name}')
kubectl cp /tmp/deploy-data.tar.gz ontology-demo/$FASTAPI_POD:/tmp/deploy-data.tar.gz

# 3. 파드에서 풀기
kubectl exec -n ontology-demo $FASTAPI_POD -- tar xzf /tmp/deploy-data.tar.gz -C /tmp/

# 4. 의존성 설치
kubectl exec -n ontology-demo $FASTAPI_POD -- \
  pip install boto3 gremlinpython requests-aws4auth opensearch-py
```

기타 방법:
- **SSM으로 EKS 워커 노드 접속**: `aws ssm start-session --target <instance-id>`
- **임시 EC2 인스턴스**: AppPrivate 서브넷에 생성
- **Cloud9/Bastion**: VPC 내부에서 직접 실행

### 2-1. Neptune IAM 인증 정책 확인

> **중요**: Neptune IAM 인증은 **클러스터 리소스 ID** (`cluster-XXXXX...`)를 사용합니다.
> CDK의 `CfnDBCluster.ref`는 클러스터 식별자 (`ontology-demo-neptune`)를 반환하므로 다릅니다.
> 현재 CDK 코드는 와일드카드(`arn:aws:neptune-db:{region}:{account}:*`)를 사용합니다.
>
> 더 제한적인 리소스 ARN을 원하면 Neptune 에러 메시지에서 클러스터 리소스 ID를 추출하여
> IAM 정책을 수동으로 업데이트할 수 있습니다.

```bash
# 방법 1: describe-db-clusters로 리소스 ID 확인
aws neptune describe-db-clusters \
  --db-cluster-identifier ontology-demo-neptune \
  --region $CDK_DEFAULT_REGION \
  --query 'DBClusters[0].DbClusterResourceId' --output text
# 출력 예: cluster-EDMJL3EN3KFVXUQG67IOKFUECI

# 방법 2: 앱 로그에서 AccessDeniedException의 resource ARN 확인
```

### 2-2. OpenSearch 인덱스 생성

```bash
# 파드 내부에서 실행
kubectl exec -n ontology-demo $FASTAPI_POD -- \
  env OPENSEARCH_ENDPOINT=$OPENSEARCH_ENDPOINT AWS_REGION=$CDK_DEFAULT_REGION \
  python3 /tmp/scripts/create_opensearch_index.py
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
  - Embedding dimension: 1024 (Bedrock Titan Embed V2)
  - Text analyzer: Nori (Korean morphological)
  - node_label.raw: keyword (exact match/wildcard)
```

### 2-3. Neptune + OpenSearch 데이터 로딩

```bash
kubectl exec -n ontology-demo $FASTAPI_POD -- \
  env INPUT_DIR=/tmp/data/v2-graph-ready \
  python3 /tmp/scripts/load_v2_data.py --force
```

옵션:
```bash
# Neptune만
kubectl exec -n ontology-demo $FASTAPI_POD -- \
  env INPUT_DIR=/tmp/data/v2-graph-ready \
  python3 /tmp/scripts/load_v2_data.py --neptune-only

# OpenSearch만
kubectl exec -n ontology-demo $FASTAPI_POD -- \
  env INPUT_DIR=/tmp/data/v2-graph-ready \
  python3 /tmp/scripts/load_v2_data.py --opensearch-only

# 특정 파일만
kubectl exec -n ontology-demo $FASTAPI_POD -- \
  env INPUT_DIR=/tmp/data/v2-graph-ready \
  python3 /tmp/scripts/load_v2_data.py --file "한화생명*"
```

예상 결과 (~10분):
```
Complete: 39 files, Errors: 0
Neptune: 1,955 vertices, 1,720 edges
OpenSearch: 1,955 vectors indexed
```

### 2-4. 고립 노드 연결

```bash
kubectl exec -n ontology-demo $FASTAPI_POD -- \
  python3 /tmp/scripts/connect_isolated_nodes.py
```

예상 결과:
```
Total edges created: ~44
Total failures: 0
Remaining isolated nodes: 0
```

### 2-5. 데이터 로딩 검증

```bash
# Neptune: 노드/엣지 수 확인
kubectl exec -n ontology-demo $FASTAPI_POD -- python3 -c "
import os, boto3, requests
from botocore.auth import SigV4Auth
from botocore.awsrequest import AWSRequest

endpoint = os.environ['NEPTUNE_ENDPOINT']
port = os.environ['NEPTUNE_PORT']
session = boto3.Session()
creds = session.get_credentials().get_frozen_credentials()

url = f'https://{endpoint}:{port}/gremlin'
for label, query in [('vertices', 'g.V().count()'), ('edges', 'g.E().count()')]:
    data = '{\"gremlin\": \"' + query + '\"}'
    req = AWSRequest(method='POST', url=url, data=data, headers={'Content-Type': 'application/json'})
    SigV4Auth(creds, 'neptune-db', os.environ.get('AWS_REGION', 'us-east-1')).add_auth(req)
    resp = requests.post(url, data=data, headers=dict(req.headers), verify=False, timeout=30)
    print(f'{label}: {resp.json()[\"result\"][\"data\"][\"@value\"]}')
"
```

---

## Phase 3: 애플리케이션 배포 (Docker → ECR → EKS)

> Phase 3은 VPC 내부일 필요 없습니다. Docker 빌드와 ECR 푸시는 어디서든 가능합니다.

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
echo "Frontend: http://$ALB_DNS/"
echo "API:      http://$ALB_DNS/v1/docs"

# API 헬스체크 — 반드시 "healthy"여야 함
curl -s http://$ALB_DNS/v1/health | python3 -m json.tool
# 기대값: {"status": "healthy", "checks": {"neptune": "ok", "opensearch": "ok"}}

# HPA
kubectl get hpa -n ontology-demo
```

> **헬스체크 결과가 `degraded`인 경우:**
> `neptune: error` 또는 `opensearch: error`가 나오면 `BEDROCK_REGION`이 배포 리전과 일치하는지 확인하세요.
> ```bash
> kubectl exec -n ontology-demo deployment/fastapi -- env | grep BEDROCK_REGION
> ```
> 값이 없거나 다른 리전이면 ConfigMap을 패치하고 Pod를 재시작합니다:
> ```bash
> kubectl patch configmap app-config -n ontology-demo \
>   --type merge -p '{"data":{"BEDROCK_REGION":"us-east-1"}}'
> kubectl rollout restart deployment/fastapi -n ontology-demo
> ```

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

## 전체 체크리스트

| # | 단계 | 확인 항목 | 상태 |
|---|------|----------|------|
| 1 | 환경 변수 | `AWS_REGION` + `CDK_DEFAULT_REGION` 모두 설정 | [ ] |
| 2 | cdk.context.json | 기존 캐시 삭제 | [ ] |
| 3 | CDK Bootstrap | `cdk bootstrap` 완료 | [ ] |
| 4 | CDK Deploy | 3 스택 배포 완료 | [ ] |
| 5 | EKS 접근 | kubeconfig + 접근 항목 설정 | [ ] |
| 6 | EKS Nodes | `kubectl get nodes` — 2 Ready | [ ] |
| 7 | Neptune | Status: available | [ ] |
| 8 | OpenSearch | Collection: ACTIVE | [ ] |
| 9 | ECR | 2 repos 생성 확인 | [ ] |
| 10 | S3 | 2 버킷 확인 | [ ] |
| 11 | ConfigMap | `BEDROCK_REGION` + `GRAPHRAG_BACKEND_URL` 포함 확인 | [ ] |
| 12 | OS Index | `ontology-vectors` 인덱스 생성 (1024 dim) | [ ] |
| 13 | Neptune Load | ~1,955 vertices, ~1,720 edges | [ ] |
| 14 | OS Load | ~1,955 vectors | [ ] |
| 15 | Isolated Nodes | 0 remaining | [ ] |
| 16 | Backend ECR | 이미지 푸시 완료 | [ ] |
| 17 | Frontend ECR | 이미지 푸시 완료 | [ ] |
| 18 | Pods | fastapi 2/2, nextjs 2/2 Running | [ ] |
| 19 | ALB | Ingress ADDRESS 할당 + 리스너 존재 | [ ] |
| 20 | Health | `/v1/health` → `healthy` (neptune: ok, opensearch: ok) | [ ] |
| 21 | 프론트엔드 | 브라우저에서 질의 → 서브그래프 포함된 답변 확인 | [ ] |
| 22 | E2E 평가 | 128 시나리오 ~92/128 (71.9%+) | [ ] |

---

## 트러블슈팅

### CDK가 잘못된 리전에 배포됨
**원인**: `AWS_REGION` 환경변수가 시스템 기본값으로 설정되어 있거나 `cdk.context.json`에 이전 리전 캐시가 남아있음.
**해결**: `AWS_REGION`과 `CDK_DEFAULT_REGION`을 동일하게 설정하고, `cdk.context.json`을 삭제.

### kubectl 접근 거부 (`Unauthorized`)
**원인**: CDK 실행 역할이 아닌 다른 IAM 역할에서 접근 시도.
**해결**: 1-8 단계의 EKS 접근 항목 추가 절차 수행.

### Neptune `AccessDeniedException`
**원인**: IRSA 정책의 리소스 ARN에 클러스터 식별자(`ontology-demo-neptune`)가 사용됨. Neptune IAM 인증은 클러스터 리소스 ID(`cluster-XXXXX`)를 요구.
**해결**: CDK는 와일드카드(`*`)를 사용하므로 정상 동작. 수동 정책이라면 `neptune describe-db-clusters`로 리소스 ID 확인 후 수정.

### OpenSearch 인덱싱 실패 (`mapper_parsing_exception`)
**원인**: 인덱스 임베딩 차원이 데이터와 불일치. Titan Embed V2 기본 출력은 **1024차원**.
**해결**: `create_opensearch_index.py`의 `dimension`이 1024인지 확인. 잘못 생성했으면 `--recreate` 옵션으로 재생성.

### Pod에서 Neptune/OpenSearch 연결 타임아웃
**원인**: EKS는 노드에 클러스터 전용 보안 그룹(auto-created)을 할당하며, VPC 스택의 `EksWorkersSg`와 다름.
CDK가 `CfnSecurityGroupIngress`로 클러스터 SG를 Neptune/OpenSearch SG에 추가합니다.
**확인**: `aws eks describe-cluster --query 'cluster.resourcesVpcConfig.clusterSecurityGroupId'`로 클러스터 SG ID 확인 후, Neptune/OpenSearch SG의 인바운드 규칙에 포함되어 있는지 확인.

### ALB에 리스너 없음 (Connection refused)
**원인**: CDK 롤백 또는 ingress 리소스 손상으로 ALB Controller가 리스너를 삭제.
**해결**: ingress 삭제 → ALB Controller 재시작 → ingress 재생성.
> **참고**: `spec.ingressClassName: alb`를 사용합니다. 구 방식인 `kubernetes.io/ingress.class` 어노테이션은
> ALB Controller v2.8+에서 리스너가 사라지는 문제가 있습니다.
```bash
# 1. 기존 ingress 삭제 (ALB도 자동 삭제됨)
kubectl delete ingress app-ingress -n ontology-demo

# 2. ALB Controller 재시작 (stale 상태 초기화)
kubectl rollout restart deployment/aws-load-balancer-controller -n kube-system
kubectl rollout status deployment/aws-load-balancer-controller -n kube-system

# 3. ingress 재생성
kubectl apply -f - <<'EOF'
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: app-ingress
  namespace: ontology-demo
  annotations:
    alb.ingress.kubernetes.io/scheme: internet-facing
    alb.ingress.kubernetes.io/target-type: ip
    alb.ingress.kubernetes.io/listen-ports: '[{"HTTP": 80}]'
spec:
  ingressClassName: alb
  rules:
    - http:
        paths:
          - path: /v1
            pathType: Prefix
            backend:
              service:
                name: fastapi
                port:
                  number: 80
          - path: /
            pathType: Prefix
            backend:
              service:
                name: nextjs
                port:
                  number: 80
EOF

# 4. ALB 생성 확인 (1-2분 대기)
kubectl get ingress app-ingress -n ontology-demo -w
```

### 프론트엔드에서 "백엔드 서비스에 연결할 수 없습니다" 에러
**원인**: Next.js의 server-side API route가 `GRAPHRAG_BACKEND_URL` 환경변수로 FastAPI 백엔드 주소를 결정.
설정하지 않으면 `http://localhost:8000`으로 fallback → Pod 내부에 FastAPI가 없으므로 연결 실패.
**해결**: ConfigMap에 `GRAPHRAG_BACKEND_URL` 추가 후 nextjs Pod 재시작.
```bash
kubectl patch configmap app-config -n ontology-demo \
  --type merge -p '{"data":{"GRAPHRAG_BACKEND_URL":"http://fastapi.ontology-demo.svc.cluster.local:80"}}'
kubectl rollout restart deployment/nextjs -n ontology-demo
```

### Neptune/OpenSearch 403 Forbidden (SigV4 리전 불일치)
**원인**: 백엔드 앱(`config.py`)의 `bedrock_region` 기본값이 `us-west-2`. Neptune/OpenSearch 클라이언트가
이 리전으로 SigV4 서명하므로, 실제 서비스가 다른 리전(예: `us-east-1`)에 있으면 403 발생.
`kubectl exec`로 직접 SigV4 테스트하면 정상이지만 앱에서만 403이 나는 경우 이것이 원인.
**증상**: `/v1/health`가 `{"status":"degraded","checks":{"neptune":"error","opensearch":"error"}}` 반환.
질의 시 서브그래프 데이터 없이 저품질 답변만 생성됨.
**해결**: ConfigMap에 `BEDROCK_REGION`을 배포 리전으로 설정 후 fastapi Pod 재시작.
```bash
kubectl patch configmap app-config -n ontology-demo \
  --type merge -p '{"data":{"BEDROCK_REGION":"us-east-1"}}'
kubectl rollout restart deployment/fastapi -n ontology-demo

# 확인
curl -s http://$ALB_DNS/v1/health
# 기대값: {"status":"healthy","checks":{"neptune":"ok","opensearch":"ok"}}
```

---

## 환경 삭제 (Teardown)

```bash
export CDK_DEFAULT_REGION=us-east-1  # 삭제할 리전
export AWS_REGION=$CDK_DEFAULT_REGION

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
| S3: parsed-data | ontology-demo-parsed-data-{account}-{region} | 그래프 데이터 JSON |
| S3: mock-cache | ontology-demo-mock-cache-{account}-{region} | 프론트엔드 캐시 |
| EKS Cluster | ontology-demo-cluster | v1.33, Public+Private endpoint |
| Node Group | WorkerNodes | m5.xlarge × 2, AL2023 |
| ALB Controller | v2.8.2 | 자동 설치 |
| ECR: backend | ontology-demo/backend-app | RETAIN |
| ECR: frontend | ontology-demo/frontend-app | RETAIN |
| K8s Namespace | ontology-demo | |
| K8s Deployments | fastapi (×2), nextjs (×2) | |
| K8s Ingress | app-ingress | ALB internet-facing |
| K8s HPA | fastapi-hpa | CPU 70%, 2-6 replicas |
| IRSA: fastapi-sa | Neptune, OpenSearch, Bedrock, S3 | |
| IRSA: nextjs-sa | S3 mock-cache read | |

## IAM 역할 및 권한

CDK가 IRSA(IAM Roles for Service Accounts)를 통해 2개의 역할을 자동 생성합니다.
데모 환경이므로 서비스별 와일드카드를 사용하여 권한 부족으로 인한 배포 오류를 방지합니다.

### fastapi-sa (백엔드 파드)

| 서비스 | Actions | Resource | 비고 |
|--------|---------|----------|------|
| Neptune | `neptune-db:*` | `arn:aws:neptune-db:{region}:{account}:*` | 클러스터 리소스 ID가 배포마다 다르므로 와일드카드 필수 |
| OpenSearch Serverless | `aoss:*` | `arn:aws:aoss:{region}:{account}:collection/{id}` | 컬렉션 ARN 자동 참조 |
| Bedrock | `bedrock:InvokeModel`, `bedrock:InvokeModelWithResponseStream` | `*` | 모든 모델 호출 |
| S3 (parsed-data) | Read/Write (CDK `grantReadWrite`) | `ontology-demo-parsed-data-*` | 그래프 데이터 JSON |
| S3 (mock-cache) | Read/Write (CDK `grantReadWrite`) | `ontology-demo-mock-cache-*` | 프론트엔드 캐시 |

**Neptune 권한 참고:**
- Neptune IAM 인증은 **클러스터 리소스 ID** (`cluster-XXXXX...`)를 사용합니다.
- 이 ID는 `CfnDBCluster.ref`(클러스터 식별자 `ontology-demo-neptune`)와 다르고, CDK에서 직접 참조할 수 없습니다.
- 따라서 리소스를 `arn:aws:neptune-db:{region}:{account}:*` 와일드카드로 설정합니다.
- 리소스 ID 확인: `aws neptune describe-db-clusters --db-cluster-identifier ontology-demo-neptune --query 'DBClusters[0].DbClusterResourceId'`

### nextjs-sa (프론트엔드 파드)

| 서비스 | Actions | Resource | 비고 |
|--------|---------|----------|------|
| S3 (mock-cache) | Read (CDK `grantRead`) | `ontology-demo-mock-cache-*` | 프론트엔드 캐시 읽기만 |

### OpenSearch Serverless Data Access Policy

IRSA의 IAM 정책과 별도로, OpenSearch Serverless는 자체 **Data Access Policy**가 필요합니다.
CDK가 `arn:aws:iam::{account}:root`를 Principal로 설정하여 계정 내 모든 IAM 역할에 접근을 허용합니다.

| 리소스 타입 | Resource | Permission |
|------------|----------|------------|
| index | `index/ontology-embeddings/*` | `aoss:*` |
| collection | `collection/ontology-embeddings` | `aoss:*` |

> **참고**: OpenSearch Serverless 접근에는 **두 가지** 권한이 모두 필요합니다:
> 1. **IAM 정책** (IRSA 역할): `aoss:*` — AWS API 수준 인가
> 2. **Data Access Policy** (컬렉션): `aoss:*` — 데이터 수준 인가
> 둘 중 하나라도 없으면 403 Forbidden이 발생합니다.

### 보안 그룹 (네트워크 수준)

| SG | 인바운드 규칙 | 비고 |
|----|-------------|------|
| Neptune SG | TCP 8182 ← EKS Workers SG | VPC 스택에서 생성 |
| Neptune SG | TCP 8182 ← EKS Cluster SG | EKS 스택에서 `CfnSecurityGroupIngress`로 추가 |
| OpenSearch SG | TCP 443 ← EKS Workers SG | VPC 스택에서 생성 |
| OpenSearch SG | TCP 443 ← EKS Cluster SG | EKS 스택에서 `CfnSecurityGroupIngress`로 추가 |

> **중요**: EKS는 노드에 **클러스터 전용 보안 그룹**(auto-created)을 할당합니다.
> VPC 스택의 `EksWorkersSg`만으로는 부족하며, EKS 클러스터 SG도 Neptune/OpenSearch SG에 추가해야 합니다.
> CDK가 `CfnSecurityGroupIngress`로 자동 처리합니다. (`addIngressRule`은 cross-stack 순환 참조를 유발하므로 사용 불가)

### 권한 검증 명령어

```bash
# 1. IRSA 역할 확인
kubectl get sa fastapi-sa -n ontology-demo -o jsonpath='{.metadata.annotations.eks\.amazonaws\.com/role-arn}'

# 2. Pod에서 실제 사용 중인 역할 확인
FASTAPI_POD=$(kubectl get pods -n ontology-demo -l app=fastapi -o jsonpath='{.items[0].metadata.name}')
kubectl exec -n ontology-demo $FASTAPI_POD -- \
  python3 -c "import boto3; print(boto3.client('sts').get_caller_identity()['Arn'])"

# 3. IRSA 역할의 IAM 정책 확인
ROLE_NAME=$(kubectl get sa fastapi-sa -n ontology-demo \
  -o jsonpath='{.metadata.annotations.eks\.amazonaws\.com/role-arn}' | awk -F/ '{print $NF}')
aws iam list-role-policies --role-name $ROLE_NAME
aws iam get-role-policy --role-name $ROLE_NAME --policy-name $(aws iam list-role-policies --role-name $ROLE_NAME --query 'PolicyNames[0]' --output text)

# 4. OpenSearch Data Access Policy 확인
aws opensearchserverless get-access-policy \
  --name ontology-embeddings-access --type data \
  --region $CDK_DEFAULT_REGION

# 5. Neptune 클러스터 리소스 ID 확인
aws neptune describe-db-clusters \
  --db-cluster-identifier ontology-demo-neptune \
  --region $CDK_DEFAULT_REGION \
  --query 'DBClusters[0].DbClusterResourceId' --output text

# 6. 보안 그룹 인바운드 규칙 확인
EKS_CLUSTER_SG=$(aws eks describe-cluster --name ontology-demo-cluster \
  --region $CDK_DEFAULT_REGION \
  --query 'cluster.resourcesVpcConfig.clusterSecurityGroupId' --output text)
echo "EKS Cluster SG: $EKS_CLUSTER_SG"
# Neptune SG에 이 SG가 인바운드로 포함되어 있는지 확인
```

## 데이터 사양

| 항목 | 수치 |
|------|------|
| 소스 문서 | 39개 (보험 상품 요약서 + 법규) |
| Neptune 노드 수 | ~1,955 vertices |
| Neptune 엣지 수 | ~1,764 edges (1,720 + 44 isolated fix) |
| 엔티티 타입 | 12종 (Policy, Coverage, Exclusion 등) |
| 관계 타입 | 14종 (HAS_COVERAGE, EXCLUDED_IF 등) |
| OpenSearch 벡터 수 | ~1,955 documents |
| 벡터 차원 | 1024 (Bedrock Titan Embed V2) |
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
| `scripts/create_opensearch_index.py` | OpenSearch k-NN + Nori 인덱스 생성 (1024d) | 2-2 |
| `scripts/load_v2_data.py` | Neptune 그래프 + OpenSearch 벡터 일괄 로딩 | 2-3 |
| `scripts/connect_isolated_nodes.py` | 고립 노드 → Regulation 노드 연결 | 2-4 |
| `scripts/run_evaluation.py` | 128 시나리오 E2E 평가 (5차원) | 3-6 |

환경 변수:
```bash
# Phase 1: CDK 배포 (모두 필수)
export CDK_DEFAULT_ACCOUNT=$(aws sts get-caller-identity --query Account --output text)
export CDK_DEFAULT_REGION=us-east-1
export AWS_REGION=$CDK_DEFAULT_REGION

# Phase 2: 데이터 로딩 (kubectl exec 사용 시 ConfigMap에서 자동 설정)
export INPUT_DIR=/tmp/data/v2-graph-ready

# Phase 3-6: E2E 평가
export ALB_HOST=<alb-dns-name>
```
