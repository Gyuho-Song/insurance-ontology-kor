import { render, screen } from '@testing-library/react';
import { ChatPanel } from '@/components/chat/ChatPanel';
import { AppProvider } from '@/lib/context';

// Wrapper for AppProvider context
const Wrapper = ({ children }: { children: React.ReactNode }) => (
  <AppProvider>{children}</AppProvider>
);

// Mock useChat hook
const mockAppend = jest.fn().mockResolvedValue(undefined);
const mockSetMessages = jest.fn();
let mockMessages: Array<{ id: string; role: string; content: string; annotations?: unknown[] }> = [];
let mockIsLoading = false;

jest.mock('@ai-sdk/react', () => ({
  useChat: jest.fn(() => ({
    messages: mockMessages,
    append: mockAppend,
    isLoading: mockIsLoading,
    setMessages: mockSetMessages,
  })),
}));

describe('ChatPanel', () => {
  beforeEach(() => {
    mockMessages = [];
    mockIsLoading = false;
    mockAppend.mockClear();
    mockSetMessages.mockClear();
  });

  it('should render chat input', () => {
    render(
      <ChatPanel
        scenarioId={undefined}
        onScenarioConsumed={() => {}}
      />,
      { wrapper: Wrapper }
    );

    expect(screen.getByPlaceholderText(/질문을 입력/)).toBeInTheDocument();
  });

  it('should render messages list', () => {
    mockMessages = [
      { id: '1', role: 'user', content: '테스트 질문' },
      { id: '2', role: 'assistant', content: '테스트 답변' },
    ];

    render(
      <ChatPanel
        scenarioId={undefined}
        onScenarioConsumed={() => {}}
      />,
      { wrapper: Wrapper }
    );

    expect(screen.getByText('테스트 질문')).toBeInTheDocument();
    expect(screen.getByText('테스트 답변')).toBeInTheDocument();
  });

  it('should merge annotations into ExtendedMessage for MessageTrace', () => {
    mockMessages = [
      {
        id: '1',
        role: 'assistant',
        content: '답변입니다.',
        annotations: [
          {
            sources: [
              {
                node_id: 'Coverage#1',
                node_type: 'Coverage',
                node_label: '제5조①',
                source_article: '제5조①',
                source_text: '테스트 출처',
              },
            ],
            topoFaithfulness: 0.95,
            isMockResponse: true,
          },
        ],
      },
    ];

    render(
      <ChatPanel
        scenarioId={undefined}
        onScenarioConsumed={() => {}}
      />,
      { wrapper: Wrapper }
    );

    // MessageTrace should be rendered with annotation data
    expect(screen.getByText(/근거 보기/)).toBeInTheDocument();
  });

  it('should auto-send when scenarioId is provided', () => {
    const mockOnConsumed = jest.fn();

    render(
      <ChatPanel
        scenarioId="A01"
        onScenarioConsumed={mockOnConsumed}
      />,
      { wrapper: Wrapper }
    );

    // useChat append should have been called with scenario query
    expect(mockAppend).toHaveBeenCalled();
    expect(mockOnConsumed).toHaveBeenCalled();
  });
});
