import { render, screen, fireEvent } from '@testing-library/react';
import { MarkdownContent } from '@/components/chat/MarkdownContent';

describe('MarkdownContent', () => {
  // ── Markdown rendering ──────────────────────────────────────────

  test('renders plain text', () => {
    render(<MarkdownContent content="Hello world" />);
    expect(screen.getByText('Hello world')).toBeInTheDocument();
  });

  test('renders bold text as <strong>', () => {
    const { container } = render(<MarkdownContent content="**bold text**" />);
    const strong = container.querySelector('strong');
    expect(strong).not.toBeNull();
    expect(strong?.textContent).toBe('bold text');
  });

  test('renders markdown table', () => {
    const table = '| 항목 | 금액 |\n|---|---|\n| 사망보험금 | 1억원 |';
    const { container } = render(<MarkdownContent content={table} />);
    expect(container.querySelector('table')).not.toBeNull();
    expect(screen.getByText('사망보험금')).toBeInTheDocument();
    expect(screen.getByText('1억원')).toBeInTheDocument();
  });

  test('renders markdown list', () => {
    const list = '- 항목 A\n- 항목 B\n- 항목 C';
    const { container } = render(<MarkdownContent content={list} />);
    expect(container.querySelector('ul')).not.toBeNull();
    expect(screen.getByText('항목 A')).toBeInTheDocument();
    expect(screen.getByText('항목 C')).toBeInTheDocument();
  });

  test('renders heading', () => {
    const { container } = render(<MarkdownContent content="### 보장항목" />);
    const h3 = container.querySelector('h3');
    expect(h3).not.toBeNull();
    expect(h3?.textContent).toBe('보장항목');
  });

  test('wraps table in overflow container', () => {
    const table = '| A | B |\n|---|---|\n| 1 | 2 |';
    const { container } = render(<MarkdownContent content={table} />);
    const tableEl = container.querySelector('table');
    expect(tableEl?.parentElement?.classList.contains('overflow-x-auto')).toBe(true);
  });

  // ── Citation preprocessing ──────────────────────────────────────

  test('converts citation tag to clickable badge', () => {
    const handler = jest.fn();
    render(
      <MarkdownContent
        content="보장됩니다 [출처: 제5조①]"
        onCitationClick={handler}
      />
    );
    const badge = screen.getByRole('button', { name: /제5조①/ });
    expect(badge).toBeInTheDocument();
    fireEvent.click(badge);
    expect(handler).toHaveBeenCalledWith('제5조①');
  });

  test('handles multiple citations independently', () => {
    const handler = jest.fn();
    render(
      <MarkdownContent
        content="A [출처: 제1조] B [출처: 제2조]"
        onCitationClick={handler}
      />
    );
    const buttons = screen.getAllByRole('button');
    expect(buttons).toHaveLength(2);

    fireEvent.click(buttons[0]);
    expect(handler).toHaveBeenCalledWith('제1조');

    fireEvent.click(buttons[1]);
    expect(handler).toHaveBeenCalledWith('제2조');
  });

  test('renders citation badge without crashing when no handler', () => {
    render(<MarkdownContent content="[출처: 제3조]" />);
    const badge = screen.getByRole('button', { name: /제3조/ });
    fireEvent.click(badge); // should not throw
  });

  test('handles citation with compound article reference', () => {
    const handler = jest.fn();
    render(
      <MarkdownContent
        content="[출처: 제10조제2항]"
        onCitationClick={handler}
      />
    );
    const badge = screen.getByRole('button', { name: /제10조제2항/ });
    fireEvent.click(badge);
    expect(handler).toHaveBeenCalledWith('제10조제2항');
  });

  // ── className passthrough ───────────────────────────────────────

  test('applies className to wrapper div', () => {
    const { container } = render(
      <MarkdownContent content="test" className="chat-markdown" />
    );
    expect(container.firstChild).toHaveClass('chat-markdown');
  });
});
