// === Scenario ===

export type ScenarioCategory =
  | 'coverage'      // 보장 조회
  | 'exclusion'     // 면책/예외
  | 'surrender'     // 해약환급금
  | 'dividend'      // 배당
  | 'regulation'    // 규제/법률
  | 'rider'         // 특약
  | 'eligibility'   // 가입 조건
  | 'comparison'    // 상품 비교
  | 'loan'          // 대출
  | 'mydata'        // 마이데이터
  | 'multi'         // 복합 질의
  | 'edge'          // 엣지 케이스
  | 'boundary'      // 경계값
  | 'temporal'      // 시점
  | 'security';     // 보안

export interface Scenario {
  id: string;
  title: string;
  query: string;
  category: ScenarioCategory;
}

export interface SourceReference {
  node_id: string;
  node_type: string;
  node_label: string;
  source_article: string;
  source_text: string;
}

export interface TraversalEvent {
  type:
    | 'node_activated'
    | 'edge_traversed'
    | 'constraint_blocked'
    | 'constraint_opened'
    | 'merge_node_added'
    | 'traversal_complete';
  hop: number;
  delay_ms: number;
  data: {
    node_id?: string;
    node_type?: string;
    node_label?: string;
    edge_type?: string;
    edge_style?:
      | 'red_blocked'
      | 'green_opened'
      | 'orange_warning'
      | 'blue_exception'
      | 'purple_formula'
      | 'default';
    blocked_reason?: string;
    regulation_id?: string;
    provenance?: {
      source_article: string;
      source_text: string;
    };
  };
}

export interface SubgraphNode {
  id: string;
  type: string;
  label: string;
  properties: Record<string, unknown>;
}

export interface SubgraphEdge {
  source: string;
  target: string;
  type: string;
  properties: Record<string, unknown>;
}

// === RAG Mode ===

export type RagMode = 'graphrag' | 'naive' | 'comparison';

// === Naive RAG Result (embedded in annotation for comparison mode) ===

export interface NaiveRagResult {
  answer: string;
  sources: SourceReference[];
  responseTimeMs: number;
}

// === Pipeline Explorer Stage Events ===

export type PipelineStageId =
  | 'security'
  | 'understand'
  | 'classify'
  | 'search'
  | 'traverse'
  | 'generate'
  | 'verify';

export interface StageEvent {
  stage: PipelineStageId;
  status: 'pass' | 'done' | 'streaming' | 'blocked';
  ms?: number;
  data: Record<string, unknown>;
}

// === Data Stream Metadata Annotation ===

export interface MessageAnnotation {
  sources?: SourceReference[];
  traversalEvents?: TraversalEvent[];
  subgraph?: { nodes: SubgraphNode[]; edges: SubgraphEdge[] };
  topoFaithfulness?: number;
  templatesUsed?: string[];
  isMockResponse?: boolean;
  naiveRag?: NaiveRagResult;
  comparisonMode?: boolean;
  graphRagResponseTimeMs?: number;
}

// === Chat Message (Vercel AI SDK Extended) ===

export interface ExtendedMessage {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  sources?: SourceReference[];
  traversalEvents?: TraversalEvent[];
  subgraph?: { nodes: SubgraphNode[]; edges: SubgraphEdge[] };
  topoFaithfulness?: number;
  templatesUsed?: string[];
  isMockResponse?: boolean;
  naiveRag?: NaiveRagResult;
  comparisonMode?: boolean;
  graphRagResponseTimeMs?: number;
}
