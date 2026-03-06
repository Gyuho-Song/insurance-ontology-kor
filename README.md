# Insurance Ontology GraphRAG Demo

보험 온톨로지 기반 GraphRAG(Graph Retrieval-Augmented Generation) 데모 애플리케이션입니다. 보험 약관의 복잡한 보장/면책 관계를 지식 그래프로 모델링하고, 자연어 질의에 대해 그래프 탐색 기반의 정확한 답변을 생성합니다.

## 아키텍처

```
┌─────────────┐     ┌─────────────────┐     ┌──────────────────┐
│  Next.js 15  │────▶│  FastAPI Backend │────▶│  Amazon Neptune   │
│  (React 19)  │     │                 │     │  (Knowledge Graph)│
│  Cytoscape.js│     │  Claude Sonnet  │     ├──────────────────┤
│  그래프 시각화 │     │  (Bedrock LLM)  │     │  OpenSearch       │
└─────────────┘     └─────────────────┘     │  (Vector Search)  │
                                            └──────────────────┘
```

### 주요 기능

- **GraphRAG 질의 응답** — 온톨로지 그래프 탐색 + 벡터 검색을 결합한 하이브리드 RAG
- **실시간 그래프 시각화** — 탐색 경로를 Cytoscape.js로 애니메이션 렌더링
- **보장/면책 제약 추론** — `STRICTLY_PROHIBITED`, `EXCEPTIONALLY_ALLOWED` 등 관계 기반 추론
- **마이데이터 연동** — 고객별 보험 계약 데이터 기반 맞춤 응답
- **시나리오 프리셋** — 사전 정의된 보험 상담 시나리오
- **Hallucination 검증** — 토폴로지 기반 답변 신뢰도 검증

## 기술 스택

| 계층 | 기술 |
|------|------|
| Frontend | Next.js 15, React 19, TypeScript, Tailwind CSS, Cytoscape.js |
| Backend | FastAPI, Python 3.12+, Pydantic |
| LLM | Amazon Bedrock (Claude Sonnet 4.5, Claude Haiku 4.5) |
| Embedding | Amazon Titan Embed Text v2 |
| Graph DB | Amazon Neptune Serverless (Gremlin) |
| Vector DB | Amazon OpenSearch Serverless |
| Infra | AWS CDK (TypeScript), EKS, ALB, ECR |

## 프로젝트 구조

```
├── backend-app/          # FastAPI 백엔드
│   ├── app/
│   │   ├── api/          # REST API 엔드포인트 (chat, mydata, personas, scenarios)
│   │   ├── clients/      # Neptune, OpenSearch, Bedrock, S3 클라이언트
│   │   ├── core/         # GraphRAG 핵심 로직 (traversal, scoring, hallucination)
│   │   ├── models/       # Pydantic 데이터 모델
│   │   └── services/     # 비즈니스 로직 서비스
│   └── tests/            # 단위 테스트
├── frontend-app/         # Next.js 프론트엔드
│   ├── app/              # App Router 페이지
│   ├── components/       # UI 컴포넌트 (chat, graph, controls)
│   ├── lib/              # 유틸리티 및 훅
│   └── __tests__/        # Jest 테스트
├── cdk-app/              # AWS CDK 인프라
│   └── lib/stacks/       # VPC, Data, EKS 스택
├── scripts/              # 데이터 로딩 스크립트
│   ├── extract_entities_v2.py    # 온톨로지 엔티티 추출
│   ├── load_v2_data.py           # Neptune/OpenSearch 데이터 로딩
│   └── create_opensearch_index.py # 벡터 인덱스 생성
├── data/                 # 그래프 데이터
└── docs/                 # 배포 가이드
```

## 배포

전체 배포 과정은 [배포 가이드](docs/deployment-guide.md)를 참고하세요.

### 요약

```
Phase 1: CDK 인프라 배포 (VPC → Data → EKS)
Phase 2: 데이터 로딩 (OpenSearch 인덱스 → Neptune 그래프 → 벡터 임베딩)
Phase 3: 앱 배포 (Docker 빌드 → ECR 푸시 → EKS 배포)
```

### 사전 요구사항

- AWS CLI v2, AWS CDK 2.175+
- Node.js 20+, Python 3.12+
- Docker, kubectl

## 라이선스

이 프로젝트는 데모 목적으로 공개되었습니다.
