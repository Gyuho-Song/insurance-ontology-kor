import { render, screen, fireEvent } from '@testing-library/react';
import { ChatInput } from '@/components/chat/ChatInput';

describe('ChatInput', () => {
  const mockOnSend = jest.fn();

  beforeEach(() => {
    mockOnSend.mockClear();
  });

  it('should render input field and send button', () => {
    render(<ChatInput onSend={mockOnSend} isLoading={false} />);

    expect(screen.getByPlaceholderText(/질문을 입력/)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /전송/ })).toBeInTheDocument();
  });

  it('should call onSend with input value when send button is clicked', () => {
    render(<ChatInput onSend={mockOnSend} isLoading={false} />);

    const input = screen.getByPlaceholderText(/질문을 입력/);
    fireEvent.change(input, { target: { value: '테스트 질문' } });
    fireEvent.click(screen.getByRole('button', { name: /전송/ }));

    expect(mockOnSend).toHaveBeenCalledWith('테스트 질문');
  });

  it('should clear input after sending', () => {
    render(<ChatInput onSend={mockOnSend} isLoading={false} />);

    const input = screen.getByPlaceholderText(/질문을 입력/) as HTMLInputElement;
    fireEvent.change(input, { target: { value: '테스트 질문' } });
    fireEvent.click(screen.getByRole('button', { name: /전송/ }));

    expect(input.value).toBe('');
  });

  it('should disable input and button when isLoading is true', () => {
    render(<ChatInput onSend={mockOnSend} isLoading={true} />);

    expect(screen.getByPlaceholderText(/질문을 입력/)).toBeDisabled();
    expect(screen.getByRole('button', { name: /전송/ })).toBeDisabled();
  });

  it('should not send empty messages', () => {
    render(<ChatInput onSend={mockOnSend} isLoading={false} />);

    fireEvent.click(screen.getByRole('button', { name: /전송/ }));
    expect(mockOnSend).not.toHaveBeenCalled();
  });

  it('should send on Enter key press', () => {
    render(<ChatInput onSend={mockOnSend} isLoading={false} />);

    const input = screen.getByPlaceholderText(/질문을 입력/);
    fireEvent.change(input, { target: { value: '엔터 테스트' } });
    fireEvent.keyDown(input, { key: 'Enter' });

    expect(mockOnSend).toHaveBeenCalledWith('엔터 테스트');
  });
});
