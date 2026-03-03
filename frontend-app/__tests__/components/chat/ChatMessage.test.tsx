import { render, screen, fireEvent } from '@testing-library/react';
import { ChatMessage } from '@/components/chat/ChatMessage';
import type { ExtendedMessage } from '@/lib/types';

describe('ChatMessage', () => {
  it('should render user message', () => {
    const message: ExtendedMessage = {
      id: '1',
      role: 'user',
      content: '무배당 종신보험에 배당금이 있나요?',
    };

    render(<ChatMessage message={message} />);
    expect(screen.getByText('무배당 종신보험에 배당금이 있나요?')).toBeInTheDocument();
  });

  it('should render assistant message', () => {
    const message: ExtendedMessage = {
      id: '2',
      role: 'assistant',
      content: '고객님, 무배당 상품입니다.',
    };

    render(<ChatMessage message={message} />);
    expect(screen.getByText('고객님, 무배당 상품입니다.')).toBeInTheDocument();
  });

  it('should show inline trace accordion for assistant message with sources', () => {
    const message: ExtendedMessage = {
      id: '3',
      role: 'assistant',
      content: '답변 텍스트',
      sources: [
        {
          node_id: 'Coverage#1',
          node_type: 'Coverage',
          node_label: '제5조①',
          source_article: '제5조①',
          source_text: '무배당 보험으로 배당금이 없습니다.',
        },
      ],
      topoFaithfulness: 0.985,
    };

    render(<ChatMessage message={message} />);
    // Trace accordion trigger should be visible
    expect(screen.getByText(/근거 보기/)).toBeInTheDocument();
  });

  it('should not show trace accordion for user messages', () => {
    const message: ExtendedMessage = {
      id: '4',
      role: 'user',
      content: '질문입니다.',
    };

    render(<ChatMessage message={message} />);
    expect(screen.queryByText(/근거 보기/)).not.toBeInTheDocument();
  });

  it('should not show trace accordion for assistant messages without sources', () => {
    const message: ExtendedMessage = {
      id: '5',
      role: 'assistant',
      content: '답변입니다.',
    };

    render(<ChatMessage message={message} />);
    expect(screen.queryByText(/근거 보기/)).not.toBeInTheDocument();
  });

  it('should expand trace to show source details', () => {
    const message: ExtendedMessage = {
      id: '6',
      role: 'assistant',
      content: '답변 텍스트',
      sources: [
        {
          node_id: 'Coverage#1',
          node_type: 'Coverage',
          node_label: '제5조①',
          source_article: '제5조①',
          source_text: '무배당 보험으로 배당금이 없습니다.',
        },
      ],
      topoFaithfulness: 0.985,
    };

    render(<ChatMessage message={message} />);
    fireEvent.click(screen.getByText(/근거 보기/));

    // After expanding, source details should be visible
    expect(screen.getByText('제5조①')).toBeInTheDocument();
    expect(screen.getByText('0.985')).toBeInTheDocument();
  });

  it('should render assistant message with markdown bold', () => {
    const message: ExtendedMessage = {
      id: '7',
      role: 'assistant',
      content: '**중요한** 내용입니다.',
    };

    const { container } = render(<ChatMessage message={message} />);
    const strong = container.querySelector('strong');
    expect(strong).not.toBeNull();
    expect(strong?.textContent).toBe('중요한');
  });

  it('should auto-expand trace when citation badge is clicked', () => {
    const message: ExtendedMessage = {
      id: '8',
      role: 'assistant',
      content: '보장됩니다 [출처: 제5조①]',
      sources: [
        {
          node_id: 'Coverage#1',
          node_type: 'Coverage',
          node_label: '제5조①',
          source_article: '제5조①',
          source_text: '보장 내용 텍스트입니다.',
        },
      ],
    };

    render(<ChatMessage message={message} />);

    // Citation badge should be visible
    const badge = screen.getByRole('button', { name: /제5조①/ });
    expect(badge).toBeInTheDocument();

    // Click citation → MessageTrace should auto-expand showing source text
    fireEvent.click(badge);
    expect(screen.getByText('보장 내용 텍스트입니다.')).toBeInTheDocument();
  });

  it('should not render markdown for user messages', () => {
    const message: ExtendedMessage = {
      id: '9',
      role: 'user',
      content: '**this** should stay plain',
    };

    const { container } = render(<ChatMessage message={message} />);
    // User messages should not have <strong> — rendered as plain text
    const strong = container.querySelector('strong');
    expect(strong).toBeNull();
  });
});
