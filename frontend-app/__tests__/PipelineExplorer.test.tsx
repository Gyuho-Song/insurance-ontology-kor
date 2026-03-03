import { render, screen, fireEvent } from '@testing-library/react';
import type { StageEvent } from '@/lib/types';
import { PipelineTrack } from '@/components/graph/PipelineTrack';
import { DefaultOverview } from '@/components/graph/DefaultOverview';
import { SecurityDetail } from '@/components/graph/stage-details/SecurityDetail';
import { ClassifyDetail } from '@/components/graph/stage-details/ClassifyDetail';
import { SearchDetail } from '@/components/graph/stage-details/SearchDetail';
import { TraverseDetail } from '@/components/graph/stage-details/TraverseDetail';
import { VerifyDetail } from '@/components/graph/stage-details/VerifyDetail';
import { DetailPanel } from '@/components/graph/DetailPanel';
import { PipelineExplorer } from '@/components/graph/PipelineExplorer';

// ── Test fixtures ──────────────────────────────────────────────────

const COMPLETED_STAGES: StageEvent[] = [
  { stage: 'security', status: 'pass', ms: 2, data: { checks: ['gremlin_injection', 'prompt_injection'] } },
  { stage: 'understand', status: 'done', ms: 45, data: { original_query: '보장항목 알려주세요', expanded_query: '보장항목 보장 알려주세요', added_synonyms: [], embedding_model: 'Titan V2', embedding_dims: 1024 } },
  { stage: 'classify', status: 'done', ms: 82, data: { intent: 'coverage_inquiry', intent_label: '보장 내용 조회', confidence: 0.95, entities: [{ value: 'H종신보험', type: 'product_name' }] } },
  { stage: 'search', status: 'done', ms: 156, data: { branch: 'A', branch_reason: "product_name 'H종신보험' 추출됨", result_count: 5, top_results: [{ label: '사망보험금', type: 'Coverage', score: 0.94 }, { label: '면책사유', type: 'Exclusion', score: 0.91 }] } },
  { stage: 'traverse', status: 'done', ms: 234, data: { template: 'coverage_lookup', template_label: '보장항목 조회', gremlin_query: "g.V().has('id','test')", node_count: 12, edge_count: 15, hops: 4, constraints_found: 2, node_types_used: ['Policy', 'Coverage', 'Exclusion'], edge_types_used: ['HAS_COVERAGE', 'EXCLUDED_IF'], fallback_used: false } },
  { stage: 'generate', status: 'streaming', data: { model: 'Claude Sonnet', complexity: 'complex', context_nodes: 12, context_edges: 15, prompt_rules: 14 } },
  { stage: 'generate', status: 'done', ms: 1200, data: {} },
  { stage: 'verify', status: 'done', ms: 180, data: { topo_faithfulness: 0.92, validation_status: 'completed', confidence_label: 'high' } },
];

const BLOCKED_STAGES: StageEvent[] = [
  { stage: 'security', status: 'blocked', ms: 0, data: { blocked_reason: 'gremlin_injection' } },
];

// ── PipelineTrack tests ────────────────────────────────────────────

describe('PipelineTrack', () => {
  test('renders 7 stage nodes', () => {
    render(<PipelineTrack stages={[]} onStageSelect={() => {}} selectedStage={null} />);
    const stages = screen.getAllByTestId(/^stage-node-/);
    expect(stages).toHaveLength(7);
  });

  test('all stages show pending when no events', () => {
    render(<PipelineTrack stages={[]} onStageSelect={() => {}} selectedStage={null} />);
    const pendingNodes = screen.getAllByTestId(/^stage-node-/);
    pendingNodes.forEach((node) => {
      expect(node).toHaveAttribute('data-status', 'pending');
    });
  });

  test('completed stages show done status', () => {
    render(<PipelineTrack stages={COMPLETED_STAGES} onStageSelect={() => {}} selectedStage={null} />);
    const securityNode = screen.getByTestId('stage-node-security');
    expect(securityNode).toHaveAttribute('data-status', 'done');
  });

  test('shows timing for completed stages', () => {
    render(<PipelineTrack stages={COMPLETED_STAGES} onStageSelect={() => {}} selectedStage={null} />);
    expect(screen.getByText('2ms')).toBeTruthy();
    expect(screen.getByText('1.2s')).toBeTruthy();
  });

  test('clicking stage calls onStageSelect', () => {
    const onSelect = jest.fn();
    render(<PipelineTrack stages={COMPLETED_STAGES} onStageSelect={onSelect} selectedStage={null} />);
    fireEvent.click(screen.getByTestId('stage-node-search'));
    expect(onSelect).toHaveBeenCalledWith('search');
  });

  test('blocked stage shows blocked status', () => {
    render(<PipelineTrack stages={BLOCKED_STAGES} onStageSelect={() => {}} selectedStage={null} />);
    const securityNode = screen.getByTestId('stage-node-security');
    expect(securityNode).toHaveAttribute('data-status', 'blocked');
  });
});

// ── DefaultOverview tests ──────────────────────────────────────────

describe('DefaultOverview', () => {
  test('renders ontology overview with storage info', () => {
    render(<DefaultOverview />);
    expect(screen.getByText('보험 온톨로지 지식 그래프')).toBeTruthy();
    expect(screen.getByText(/Neptune/)).toBeTruthy();
    expect(screen.getByText(/OpenSearch/)).toBeTruthy();
  });

  test('shows vertex and edge counts', () => {
    render(<DefaultOverview />);
    expect(screen.getAllByText(/1,885/).length).toBeGreaterThan(0);
    expect(screen.getAllByText(/1,771/).length).toBeGreaterThan(0);
  });

  test('shows node type list with descriptions', () => {
    render(<DefaultOverview />);
    expect(screen.getAllByText(/Coverage/).length).toBeGreaterThan(0);
    expect(screen.getAllByText(/Policy/).length).toBeGreaterThan(0);
  });
});

// ── Stage Detail Component tests ───────────────────────────────────

describe('SecurityDetail', () => {
  test('renders pass state with check items', () => {
    const stage = COMPLETED_STAGES[0];
    render(<SecurityDetail stage={stage} />);
    expect(screen.getByText(/Gremlin Injection/)).toBeTruthy();
    expect(screen.getByText(/Prompt Injection/)).toBeTruthy();
  });

  test('renders blocked state', () => {
    render(<SecurityDetail stage={BLOCKED_STAGES[0]} />);
    expect(screen.getByText(/BLOCKED/)).toBeTruthy();
  });
});

describe('ClassifyDetail', () => {
  test('renders intent label and confidence', () => {
    const stage = COMPLETED_STAGES[2];
    render(<ClassifyDetail stage={stage} />);
    expect(screen.getAllByText(/보장 내용 조회/).length).toBeGreaterThan(0);
    expect(screen.getByText('95%')).toBeTruthy();
  });

  test('renders extracted entities', () => {
    const stage = COMPLETED_STAGES[2];
    render(<ClassifyDetail stage={stage} />);
    expect(screen.getByText('H종신보험')).toBeTruthy();
  });

  test('renders data flow chain', () => {
    const stage = COMPLETED_STAGES[2];
    render(<ClassifyDetail stage={stage} />);
    expect(screen.getByText('coverage_lookup')).toBeTruthy();
    expect(screen.getByText(/다음 단계 연결/)).toBeTruthy();
  });
});

describe('SearchDetail', () => {
  test('renders branch selection', () => {
    const stage = COMPLETED_STAGES[3];
    render(<SearchDetail stage={stage} />);
    expect(screen.getByText(/Branch A/)).toBeTruthy();
  });

  test('renders top results with Entry Node badge', () => {
    const stage = COMPLETED_STAGES[3];
    render(<SearchDetail stage={stage} />);
    expect(screen.getByText('사망보험금')).toBeTruthy();
    expect(screen.getByText('0.940')).toBeTruthy();
    expect(screen.getByText('Entry Node')).toBeTruthy();
  });
});

describe('TraverseDetail', () => {
  test('renders template info and gremlin query', () => {
    const stage = COMPLETED_STAGES[4];
    render(<TraverseDetail stage={stage} />);
    expect(screen.getByText('보장항목 조회')).toBeTruthy();
    expect(screen.getByText(/g\.V\(\)/)).toBeTruthy();
  });

  test('renders node and edge counts', () => {
    const stage = COMPLETED_STAGES[4];
    render(<TraverseDetail stage={stage} />);
    const allTwelves = screen.getAllByText('12');
    expect(allTwelves.length).toBeGreaterThan(0);
    const allFifteens = screen.getAllByText('15');
    expect(allFifteens.length).toBeGreaterThan(0);
  });

  test('renders node type chain with Korean labels', () => {
    const stage = COMPLETED_STAGES[4];
    const { container } = render(<TraverseDetail stage={stage} />);
    const chips = container.querySelectorAll('.bg-emerald-50');
    const chipTexts = Array.from(chips).map(c => c.textContent);
    expect(chipTexts.some(t => t?.includes('Policy'))).toBe(true);
    expect(chipTexts.some(t => t?.includes('보험상품'))).toBe(true);
  });

  test('renders gremlin query explanation', () => {
    const stage = COMPLETED_STAGES[4];
    render(<TraverseDetail stage={stage} />);
    expect(screen.getByText('쿼리 해설')).toBeTruthy();
    expect(screen.getByText(/Policy 노드에서 시작/)).toBeTruthy();
  });
});

describe('VerifyDetail', () => {
  test('renders faithfulness score', () => {
    const stage = COMPLETED_STAGES[7];
    render(<VerifyDetail stage={stage} />);
    expect(screen.getByText('0.92')).toBeTruthy();
  });

  test('renders confidence label', () => {
    const stage = COMPLETED_STAGES[7];
    const { container } = render(<VerifyDetail stage={stage} />);
    const badge = container.querySelector('.rounded-full.uppercase');
    expect(badge?.textContent).toBe('high');
  });
});

// ── DetailPanel routing tests ──────────────────────────────────────

describe('DetailPanel', () => {
  test('shows DefaultOverview when no stage selected', () => {
    render(<DetailPanel stages={[]} selectedStage={null} />);
    expect(screen.getByText('보험 온톨로지 지식 그래프')).toBeTruthy();
  });

  test('shows SecurityDetail when security selected', () => {
    render(<DetailPanel stages={COMPLETED_STAGES} selectedStage="security" />);
    expect(screen.getByText(/Gremlin Injection/)).toBeTruthy();
  });

  test('shows TraverseDetail when traverse selected', () => {
    render(<DetailPanel stages={COMPLETED_STAGES} selectedStage="traverse" />);
    expect(screen.getByText('보장항목 조회')).toBeTruthy();
  });
});

// ── PipelineExplorer container tests ───────────────────────────────

describe('PipelineExplorer', () => {
  test('renders PipelineTrack and DetailPanel', () => {
    render(<PipelineExplorer stages={[]} />);
    const stageNodes = screen.getAllByTestId(/^stage-node-/);
    expect(stageNodes).toHaveLength(7);
    expect(screen.getByText('보험 온톨로지 지식 그래프')).toBeTruthy();
  });

  test('clicking a stage shows its detail', () => {
    render(<PipelineExplorer stages={COMPLETED_STAGES} />);
    fireEvent.click(screen.getByTestId('stage-node-traverse'));
    expect(screen.getByText('보장항목 조회')).toBeTruthy();
  });
});
