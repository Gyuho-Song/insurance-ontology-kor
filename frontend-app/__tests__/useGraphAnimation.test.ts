import { renderHook, act } from '@testing-library/react';
import { useGraphAnimation } from '@/lib/useGraphAnimation';
import type { TraversalEvent } from '@/lib/types';

// React 19 + modern fake timers conflict — use legacy
beforeEach(() => {
  jest.useFakeTimers({ legacyFakeTimers: true });
});

afterEach(() => {
  jest.useRealTimers();
});

const mockEvents: TraversalEvent[] = [
  {
    type: 'node_activated',
    hop: 0,
    delay_ms: 0,
    data: { node_id: 'P1', node_type: 'Policy', node_label: 'Policy 1' },
  },
  {
    type: 'edge_traversed',
    hop: 1,
    delay_ms: 300,
    data: { node_id: 'C1', node_type: 'Coverage', edge_type: 'HAS_COVERAGE', edge_style: 'default' },
  },
  {
    type: 'constraint_blocked',
    hop: 2,
    delay_ms: 600,
    data: { node_id: 'X1', node_type: 'Exception', edge_style: 'red_blocked', blocked_reason: 'Blocked' },
  },
  {
    type: 'traversal_complete',
    hop: 3,
    delay_ms: 900,
    data: {},
  },
];

describe('useGraphAnimation', () => {
  it('initializes in idle state with no events', () => {
    const { result } = renderHook(() => useGraphAnimation([]));
    expect(result.current.status).toBe('idle');
    expect(result.current.currentHop).toBe(0);
    expect(result.current.totalHops).toBe(0);
    expect(result.current.speed).toBe(1);
    expect(result.current.currentEvent).toBeNull();
    expect(result.current.appliedEvents).toEqual([]);
  });

  it('initializes in idle state with events', () => {
    const { result } = renderHook(() => useGraphAnimation(mockEvents));
    expect(result.current.status).toBe('idle');
    expect(result.current.totalHops).toBe(4);
  });

  it('transitions idle → playing on play(), applies first event immediately', () => {
    const { result } = renderHook(() => useGraphAnimation(mockEvents));

    act(() => {
      result.current.play();
    });

    expect(result.current.status).toBe('playing');
    expect(result.current.currentHop).toBe(1);
    expect(result.current.currentEvent).toEqual(mockEvents[0]);
    expect(result.current.appliedEvents).toHaveLength(1);
  });

  it('advances events on timer completion', () => {
    const { result } = renderHook(() => useGraphAnimation(mockEvents));

    act(() => {
      result.current.play();
    });

    act(() => {
      jest.advanceTimersByTime(300);
    });
    expect(result.current.currentHop).toBe(2);
    expect(result.current.currentEvent).toEqual(mockEvents[1]);
    expect(result.current.appliedEvents).toHaveLength(2);
  });

  it('reaches complete status after all events', () => {
    const { result } = renderHook(() => useGraphAnimation(mockEvents));

    act(() => {
      result.current.play();
    });

    act(() => {
      jest.advanceTimersByTime(900);
    });

    expect(result.current.status).toBe('complete');
    expect(result.current.currentHop).toBe(4);
    expect(result.current.appliedEvents).toHaveLength(4);
  });

  it('pauses playback and stops advancing', () => {
    const { result } = renderHook(() => useGraphAnimation(mockEvents));

    act(() => {
      result.current.play();
    });

    act(() => {
      result.current.pause();
    });
    expect(result.current.status).toBe('paused');

    act(() => {
      jest.advanceTimersByTime(1000);
    });
    expect(result.current.currentHop).toBe(1);
  });

  it('resumes from paused state', () => {
    const { result } = renderHook(() => useGraphAnimation(mockEvents));

    act(() => {
      result.current.play();
    });
    act(() => {
      result.current.pause();
    });

    act(() => {
      result.current.play();
    });
    expect(result.current.status).toBe('playing');

    act(() => {
      jest.advanceTimersByTime(300);
    });
    expect(result.current.currentHop).toBe(2);
  });

  it('supports nextStep() for manual stepping', () => {
    const { result } = renderHook(() => useGraphAnimation(mockEvents));

    act(() => {
      result.current.nextStep();
    });
    expect(result.current.status).toBe('paused');
    expect(result.current.currentHop).toBe(1);
    expect(result.current.currentEvent).toEqual(mockEvents[0]);

    act(() => {
      result.current.nextStep();
    });
    expect(result.current.currentHop).toBe(2);

    act(() => {
      result.current.nextStep();
    });
    expect(result.current.currentHop).toBe(3);

    act(() => {
      result.current.nextStep();
    });
    expect(result.current.status).toBe('complete');
    expect(result.current.currentHop).toBe(4);
  });

  it('resets to initial state', () => {
    const { result } = renderHook(() => useGraphAnimation(mockEvents));

    act(() => {
      result.current.play();
    });
    act(() => {
      jest.advanceTimersByTime(300);
    });

    act(() => {
      result.current.reset();
    });
    expect(result.current.status).toBe('idle');
    expect(result.current.currentHop).toBe(0);
    expect(result.current.currentEvent).toBeNull();
    expect(result.current.appliedEvents).toEqual([]);
  });

  it('changes speed and applies to playback timing', () => {
    const { result } = renderHook(() => useGraphAnimation(mockEvents));

    act(() => {
      result.current.setSpeed(2);
    });
    expect(result.current.speed).toBe(2);

    act(() => {
      result.current.play();
    });

    // At 2x speed, 300ms delay becomes 150ms
    act(() => {
      jest.advanceTimersByTime(150);
    });
    expect(result.current.currentHop).toBe(2);
  });

  it('does nothing if play() called with no events', () => {
    const { result } = renderHook(() => useGraphAnimation([]));
    act(() => {
      result.current.play();
    });
    expect(result.current.status).toBe('idle');
  });

  it('resets when events reference changes', () => {
    const { result, rerender } = renderHook(
      ({ events }) => useGraphAnimation(events),
      { initialProps: { events: mockEvents } }
    );

    act(() => {
      result.current.play();
    });
    expect(result.current.currentHop).toBe(1);

    const newEvents = [mockEvents[0]];
    rerender({ events: newEvents });

    expect(result.current.status).toBe('idle');
    expect(result.current.currentHop).toBe(0);
    expect(result.current.totalHops).toBe(1);
  });
});
