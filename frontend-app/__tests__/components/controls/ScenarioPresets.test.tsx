import { render, screen, fireEvent } from '@testing-library/react';
import { ScenarioPresets } from '@/components/controls/ScenarioPresets';

describe('ScenarioPresets', () => {
  const mockOnSelect = jest.fn();

  beforeEach(() => {
    mockOnSelect.mockClear();
  });

  it('should render category chips', () => {
    render(<ScenarioPresets onSelect={mockOnSelect} />);

    // Should have category labels visible
    expect(screen.getByText(/보장 조회/)).toBeInTheDocument();
    expect(screen.getByText(/면책\/예외/)).toBeInTheDocument();
  });

  it('should show scenario chips when a category is clicked', () => {
    render(<ScenarioPresets onSelect={mockOnSelect} />);

    // Click coverage category
    fireEvent.click(screen.getByText(/보장 조회/));

    // Should show scenario chips within that category
    expect(screen.getByText('A01')).toBeInTheDocument();
  });

  it('should hide scenario chips when category is clicked again', () => {
    render(<ScenarioPresets onSelect={mockOnSelect} />);

    const categoryBtn = screen.getByText(/보장 조회/);
    fireEvent.click(categoryBtn);
    expect(screen.getByText('A01')).toBeInTheDocument();

    // Click again to collapse
    fireEvent.click(categoryBtn);
    expect(screen.queryByText('A01')).not.toBeInTheDocument();
  });

  it('should call onSelect with scenario when a scenario chip is clicked', () => {
    render(<ScenarioPresets onSelect={mockOnSelect} />);

    // Open coverage category
    fireEvent.click(screen.getByText(/보장 조회/));

    // Click a scenario chip
    fireEvent.click(screen.getByText('A01'));
    expect(mockOnSelect).toHaveBeenCalledTimes(1);
    expect(mockOnSelect.mock.calls[0][0]).toHaveProperty('id', 'A01');
  });
});
