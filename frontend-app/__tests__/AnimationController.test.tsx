import { render, screen, fireEvent } from '@testing-library/react';
import { AnimationController } from '@/components/graph/AnimationController';
import type { AnimationStatus } from '@/lib/useGraphAnimation';

describe('AnimationController', () => {
  const defaultProps = {
    status: 'idle' as AnimationStatus,
    currentHop: 0,
    totalHops: 5,
    speed: 1,
    onPlay: jest.fn(),
    onPause: jest.fn(),
    onNextStep: jest.fn(),
    onReset: jest.fn(),
    onSpeedChange: jest.fn(),
  };

  beforeEach(() => {
    jest.clearAllMocks();
  });

  it('renders Play button when idle', () => {
    render(<AnimationController {...defaultProps} />);
    expect(screen.getByRole('button', { name: /play/i })).toBeInTheDocument();
  });

  it('renders Pause button when playing', () => {
    render(<AnimationController {...defaultProps} status="playing" />);
    expect(screen.getByRole('button', { name: /pause/i })).toBeInTheDocument();
  });

  it('renders Play button when paused', () => {
    render(<AnimationController {...defaultProps} status="paused" currentHop={2} />);
    expect(screen.getByRole('button', { name: /play/i })).toBeInTheDocument();
  });

  it('calls onPlay when Play button clicked', () => {
    render(<AnimationController {...defaultProps} />);
    fireEvent.click(screen.getByRole('button', { name: /play/i }));
    expect(defaultProps.onPlay).toHaveBeenCalledTimes(1);
  });

  it('calls onPause when Pause button clicked', () => {
    render(<AnimationController {...defaultProps} status="playing" />);
    fireEvent.click(screen.getByRole('button', { name: /pause/i }));
    expect(defaultProps.onPause).toHaveBeenCalledTimes(1);
  });

  it('renders Next button and calls onNextStep', () => {
    render(<AnimationController {...defaultProps} />);
    const nextBtn = screen.getByRole('button', { name: /next/i });
    fireEvent.click(nextBtn);
    expect(defaultProps.onNextStep).toHaveBeenCalledTimes(1);
  });

  it('renders Reset button and calls onReset', () => {
    render(<AnimationController {...defaultProps} status="complete" currentHop={5} />);
    const resetBtn = screen.getByRole('button', { name: /reset/i });
    fireEvent.click(resetBtn);
    expect(defaultProps.onReset).toHaveBeenCalledTimes(1);
  });

  it('displays hop progress', () => {
    render(<AnimationController {...defaultProps} currentHop={3} totalHops={5} />);
    expect(screen.getByText(/3\s*\/\s*5/)).toBeInTheDocument();
  });

  it('displays current speed', () => {
    render(<AnimationController {...defaultProps} speed={2} />);
    expect(screen.getByText(/2x/)).toBeInTheDocument();
  });

  it('cycles speed on speed button click', () => {
    render(<AnimationController {...defaultProps} speed={1} />);
    const speedBtn = screen.getByRole('button', { name: /speed|1x/i });
    fireEvent.click(speedBtn);
    expect(defaultProps.onSpeedChange).toHaveBeenCalled();
  });

  it('displays status indicator', () => {
    render(<AnimationController {...defaultProps} status="complete" />);
    expect(screen.getByText(/완료|complete/i)).toBeInTheDocument();
  });

  it('disables Next button when complete', () => {
    render(<AnimationController {...defaultProps} status="complete" currentHop={5} totalHops={5} />);
    const nextBtn = screen.getByRole('button', { name: /next/i });
    expect(nextBtn).toBeDisabled();
  });
});
