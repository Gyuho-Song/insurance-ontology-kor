# Frontend App — Insurance Ontology GraphRAG Demo

보험 온톨로지 GraphRAG 데모의 Next.js 프론트엔드입니다. 채팅 인터페이스와 실시간 그래프 탐색 시각화를 제공합니다.

## 기술 스택

- **Next.js 15** (App Router, standalone output)
- **React 19**, TypeScript
- **Tailwind CSS**, shadcn/ui 컴포넌트
- **Cytoscape.js** — 온톨로지 그래프 시각화 및 탐색 애니메이션
- **Vercel AI SDK** — 스트리밍 채팅 UI

## 프로젝트 구조

```
├── app/
│   ├── layout.tsx            # 루트 레이아웃 (AppProvider, ErrorBoundary)
│   ├── page.tsx              # 메인 페이지 (DualPanelLayout)
│   ├── globals.css           # 글로벌 스타일
│   └── api/mydata/           # Next.js API Routes (마이데이터 프록시)
│       ├── consent/route.ts
│       ├── contracts/route.ts
│       └── customer/route.ts
├── components/
│   ├── chat/                 # 채팅 UI
│   │   ├── ChatPanel.tsx     # 채팅 패널 (메시지 목록 + 입력)
│   │   ├── ChatInput.tsx     # 메시지 입력 컴포넌트
│   │   ├── ChatMessage.tsx   # 메시지 렌더링
│   │   ├── MarkdownContent.tsx # Markdown 렌더링
│   │   ├── MessageTrace.tsx  # 파이프라인 트레이스 표시
│   │   └── ComparisonCard.tsx # 비교 카드
│   ├── graph/                # 그래프 시각화
│   │   ├── GraphPanel.tsx    # 그래프 패널 (시각화 + 파이프라인)
│   │   ├── GraphVisualizer.tsx # Cytoscape.js 그래프 렌더링
│   │   ├── AnimationController.tsx # 탐색 애니메이션 컨트롤러
│   │   ├── PipelineExplorer.tsx  # 7단계 파이프라인 시각화
│   │   ├── PipelineTrack.tsx     # 파이프라인 트랙
│   │   ├── DetailPanel.tsx       # 단계별 상세 패널
│   │   ├── DefaultOverview.tsx   # 기본 개요
│   │   ├── GraphPlaceholder.tsx  # 빈 상태 플레이스홀더
│   │   ├── graph-styles.ts       # 그래프 스타일 정의
│   │   └── stage-details/        # 파이프라인 단계별 상세
│   │       ├── SecurityDetail.tsx
│   │       ├── ClassifyDetail.tsx
│   │       ├── SearchDetail.tsx
│   │       ├── TraverseDetail.tsx
│   │       ├── VerifyDetail.tsx
│   │       ├── GenerateDetail.tsx
│   │       └── UnderstandDetail.tsx
│   ├── controls/             # 제어 UI
│   │   ├── CustomerSwitcher.tsx  # 고객 전환
│   │   ├── ScenarioPresets.tsx   # 시나리오 프리셋 선택
│   │   └── RagModeToggle.tsx     # RAG 모드 토글
│   ├── layout/
│   │   └── DualPanelLayout.tsx   # 좌우 분할 레이아웃
│   ├── ui/                   # shadcn/ui 기본 컴포넌트
│   └── ErrorBoundary.tsx     # 에러 경계
├── lib/
│   ├── context.tsx           # AppContext (전역 상태)
│   ├── graph-utils.ts        # 그래프 데이터 변환 유틸리티
│   ├── useGraphAnimation.ts  # 그래프 애니메이션 훅
│   ├── utils.ts              # 공통 유틸리티
│   ├── types.ts              # 타입 정의
│   └── customers.ts          # 데모 고객 데이터
├── types/                    # 외부 라이브러리 타입 선언
└── __tests__/                # Jest 테스트
```

## 주요 기능

- **듀얼 패널 레이아웃** — 왼쪽 채팅 + 오른쪽 그래프 시각화
- **스트리밍 응답** — 백엔드 SSE 스트림을 실시간 렌더링
- **그래프 탐색 애니메이션** — 노드 활성화, 엣지 탐색, 제약 조건 시각화
- **7단계 파이프라인 탐색기** — Security → Classify → Search → Traverse → Verify → Generate → Understand
- **고객 전환** — 마이데이터 기반 고객별 맞춤 시나리오
- **RAG 모드 토글** — GraphRAG vs 일반 RAG 비교

## 로컬 실행

```bash
# 의존성 설치
npm install

# 개발 서버 (Turbopack)
npm run dev

# http://localhost:3000
```

## Docker

```bash
docker build -t ontology-frontend .
docker run -p 3000:3000 ontology-frontend
```

## 테스트

```bash
npm test
```

## 환경 설정

백엔드 API 주소는 `app/api/` 내 Route Handler에서 프록시됩니다. 백엔드 주소 변경 시 해당 파일을 수정하세요.
