# CDK App — Insurance Ontology GraphRAG 인프라

AWS CDK(TypeScript)로 작성된 인프라 코드입니다. 3개의 스택을 순서대로 배포하여 전체 데모 환경을 구성합니다.

## 스택 구조

```
┌──────────────────┐
│    VPC Stack     │  10.0.0.0/16, 2 AZ, 3-tier 서브넷, NAT GW
│                  │  Security Groups (Neptune, OpenSearch, EKS)
└────────┬─────────┘
         │
┌────────┴─────────┐
│    Data Stack    │  Neptune Serverless (2.5~128 NCU)
│                  │  OpenSearch Serverless (벡터 검색)
│                  │  S3 × 2 (parsed-data, mock-cache)
└────────┬─────────┘
         │
┌────────┴─────────┐
│    EKS Stack     │  EKS 1.33, m5.xlarge × 2~4
│                  │  ALB Ingress Controller
│                  │  ECR × 2 (backend, frontend)
│                  │  IRSA (Neptune, OpenSearch, Bedrock, S3 권한)
│                  │  K8s Manifests (Namespace, Deployment, Service, Ingress)
└──────────────────┘
```

## 프로젝트 구조

```
├── bin/
│   └── app.ts                    # CDK 앱 진입점 (스택 연결)
├── lib/
│   ├── config/
│   │   ├── constants.ts          # 리소스 이름, 태그, 프리픽스
│   │   └── environments.ts       # 환경별 설정 (VPC, EKS, Neptune 파라미터)
│   └── stacks/
│       ├── vpc-stack.ts          # VPC, 서브넷, Security Groups, VPC Endpoints
│       ├── data-stack.ts         # Neptune, OpenSearch, S3
│       └── eks-stack.ts          # EKS, ALB Controller, ECR, IRSA, K8s Manifests
├── test/stacks/                  # Jest 단위 테스트
│   ├── vpc-stack.test.ts
│   ├── data-stack.test.ts
│   └── eks-stack.test.ts
├── iam/                          # CDK 배포용 최소 권한 IAM 정책
│   ├── cdk-deploy-policy.json
│   ├── cdk-deploy-policy-1.json
│   ├── cdk-deploy-policy-2.json
│   └── create-policy.sh
├── scripts/
│   ├── warmup.sh                 # Neptune warm-up 스크립트
│   └── teardown.sh               # 전체 스택 삭제
├── deploy.sh                     # 원클릭 배포 스크립트
├── cdk.json                      # CDK 설정
└── package.json
```

## 주요 리소스

| 리소스 | 이름 | 설명 |
|--------|------|------|
| Neptune Cluster | `ontology-demo-neptune` | Serverless 그래프 DB (Gremlin) |
| OpenSearch Collection | `ontology-embeddings` | Serverless 벡터 검색 |
| S3 Bucket | `ontology-demo-parsed-data` | 파싱된 문서 저장 |
| S3 Bucket | `ontology-demo-mock-cache` | Mock 응답 캐시 |
| EKS Cluster | `ontology-demo-cluster` | Kubernetes 클러스터 |
| ECR | `ontology-demo/backend-app` | 백엔드 Docker 이미지 |
| ECR | `ontology-demo/frontend-app` | 프론트엔드 Docker 이미지 |

## 기본 환경 설정

| 항목 | 값 |
|------|------|
| 리전 | `ap-northeast-2` (환경변수로 변경 가능) |
| VPC | 2 AZ, NAT Gateway 1개 |
| EKS 노드 | m5.xlarge, 2~4대 |
| Neptune | 2.5~128 NCU (Serverless) |

## 배포

### 원클릭 배포

```bash
# 기본 리전 (ap-northeast-2)
./deploy.sh

# 리전 변경
AWS_DEFAULT_REGION=us-west-2 ./deploy.sh
```

### 수동 배포

```bash
# 의존성 설치
npm ci

# CDK Bootstrap (최초 1회)
npx cdk bootstrap

# 전체 스택 배포
npx cdk deploy --all --require-approval never

# kubectl 설정
aws eks update-kubeconfig --name ontology-demo-cluster --region ap-northeast-2
```

### 개별 스택 배포

```bash
npx cdk deploy ontology-demo-vpc
npx cdk deploy ontology-demo-data
npx cdk deploy ontology-demo-eks
```

## 유용한 명령어

```bash
npm run build      # TypeScript 컴파일
npm run test       # 단위 테스트
npm run synth      # CloudFormation 템플릿 생성
npm run diff       # 변경사항 비교
npm run deploy     # 전체 배포
npm run destroy    # 전체 삭제
```

## 리소스 정리

```bash
# 전체 삭제 (비용 절감)
./scripts/teardown.sh
```
