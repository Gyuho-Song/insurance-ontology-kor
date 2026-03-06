# Backend App — Insurance Ontology GraphRAG Engine

보험 온톨로지 GraphRAG 엔진의 FastAPI 백엔드입니다. 자연어 질의를 받아 그래프 탐색과 벡터 검색을 수행하고, LLM을 통해 스트리밍 응답을 생성합니다.

## 기술 스택

- **Python 3.12+**, FastAPI, Pydantic
- **Amazon Bedrock** — Claude Sonnet 4.5 (응답 생성), Claude Haiku 4.5 (분류/검증), Titan Embed v2 (임베딩)
- **Amazon Neptune** — Gremlin 기반 온톨로지 그래프 탐색
- **Amazon OpenSearch Serverless** — 벡터 유사도 검색
- **Amazon S3** — Mock 캐시 및 파싱 데이터 저장

## 프로젝트 구조

```
app/
├── main.py               # FastAPI 앱 진입점, lifespan 관리
├── config.py             # 환경변수 기반 설정 (pydantic-settings)
├── dependencies.py       # FastAPI 의존성 주입
├── api/                  # API 엔드포인트
│   ├── chat.py           # POST /v1/chat — 스트리밍 GraphRAG 응답
│   ├── mydata.py         # 마이데이터 (고객 정보, 계약, 동의)
│   ├── personas.py       # 데모 페르소나 목록
│   ├── scenarios.py      # 시나리오 프리셋 목록
│   ├── mock.py           # Mock 모드 (S3 캐시 재생)
│   └── health.py         # 헬스체크
├── clients/              # 외부 서비스 클라이언트
│   ├── neptune_client.py # Neptune Gremlin 연결 풀
│   ├── opensearch_client.py # OpenSearch 벡터 검색
│   ├── bedrock_client.py # Bedrock LLM 호출
│   ├── embedding_client.py  # 임베딩 생성 (LRU 캐시)
│   └── s3_client.py      # S3 읽기/쓰기
├── core/                 # 핵심 비즈니스 로직
│   ├── orchestrator.py   # 7단계 파이프라인 오케스트레이션
│   ├── traversal_engine.py  # 그래프 탐색 엔진
│   ├── hybrid_scorer.py  # 하이브리드 스코어링 (그래프 + 벡터)
│   ├── glossary_expander.py # 보험 용어 확장
│   └── hallucination_validator.py # 토폴로지 기반 답변 검증
├── models/               # Pydantic 데이터 모델
│   ├── query.py          # 질의 모델
│   ├── traversal.py      # 탐색 결과 모델
│   ├── scoring.py        # 스코어링 모델
│   └── validation.py     # 검증 모델
├── services/             # 서비스 레이어
│   └── mydata_service.py # 마이데이터 비즈니스 로직
├── middleware/
│   └── rbac.py           # 역할 기반 접근 제어
└── data/                 # 정적 데이터
    ├── personas.json     # 데모 페르소나
    └── scenarios.json    # 시나리오 프리셋
```

## API 엔드포인트

| Method | Path | 설명 |
|--------|------|------|
| `POST` | `/v1/chat` | GraphRAG 스트리밍 채팅 |
| `GET` | `/v1/personas` | 페르소나 목록 |
| `GET` | `/v1/scenarios` | 시나리오 프리셋 목록 |
| `GET` | `/v1/mydata/customer` | 고객 정보 조회 |
| `GET` | `/v1/mydata/contracts` | 보험 계약 목록 |
| `POST` | `/v1/mydata/consent` | 마이데이터 동의 처리 |
| `GET` | `/health` | 헬스체크 |

## 로컬 실행

```bash
# 의존성 설치
pip install -r requirements.txt

# 환경변수 설정
export NEPTUNE_ENDPOINT=<neptune-endpoint>
export OPENSEARCH_ENDPOINT=<opensearch-endpoint>
export BEDROCK_REGION=us-west-2

# 서버 실행
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

## Docker

```bash
docker build -t ontology-backend .
docker run -p 8000:8000 ontology-backend
```

## 테스트

```bash
pytest
```

## 환경변수

| 변수 | 기본값 | 설명 |
|------|--------|------|
| `NEPTUNE_ENDPOINT` | `localhost` | Neptune 엔드포인트 |
| `NEPTUNE_PORT` | `8182` | Neptune 포트 |
| `OPENSEARCH_ENDPOINT` | `localhost` | OpenSearch 엔드포인트 |
| `OPENSEARCH_INDEX` | `ontology-vectors` | 벡터 인덱스 이름 |
| `BEDROCK_REGION` | `us-west-2` | Bedrock 리전 |
| `VECTOR_SEARCH_TOP_K` | `5` | 벡터 검색 상위 K개 |
| `MAX_TRAVERSAL_DEPTH` | `4` | 최대 그래프 탐색 깊이 |
| `TOPO_FAITHFULNESS_THRESHOLD` | `0.85` | Hallucination 검증 임계값 |
| `LOG_LEVEL` | `INFO` | 로그 레벨 |
