import { useState, useCallback, useRef, useEffect } from 'react';
import type { TraversalEvent } from './types';

export type AnimationStatus = 'idle' | 'playing' | 'paused' | 'complete';

export interface UseGraphAnimationReturn {
  status: AnimationStatus;
  currentHop: number;
  totalHops: number;
  speed: number;
  currentEvent: TraversalEvent | null;
  appliedEvents: TraversalEvent[];
  play: () => void;
  pause: () => void;
  nextStep: () => void;
  reset: () => void;
  setSpeed: (speed: number) => void;
}

const EMPTY_EVENTS: TraversalEvent[] = [];

export function useGraphAnimation(events: TraversalEvent[]): UseGraphAnimationReturn {
  const [status, setStatus] = useState<AnimationStatus>('idle');
  const [appliedEvents, setAppliedEvents] = useState<TraversalEvent[]>(EMPTY_EVENTS);
  const [speed, setSpeedState] = useState(1);

  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const speedRef = useRef(speed);
  const appliedCountRef = useRef(0);
  const eventsRef = useRef(events);

  speedRef.current = speed;
  eventsRef.current = events;

  // Reset animation when events change — using useEffect instead of setState during render
  useEffect(() => {
    if (timerRef.current !== null) {
      clearTimeout(timerRef.current);
      timerRef.current = null;
    }
    appliedCountRef.current = 0;
    setStatus('idle');
    setAppliedEvents(EMPTY_EVENTS);
  }, [events]);

  const clearTimer = useCallback(() => {
    if (timerRef.current !== null) {
      clearTimeout(timerRef.current);
      timerRef.current = null;
    }
  }, []);

  const scheduleNextFrom = useCallback((currentIndex: number) => {
    const ev = eventsRef.current;
    const nextIndex = currentIndex + 1;

    if (nextIndex >= ev.length) {
      setStatus('complete');
      return;
    }

    const currentDelay = ev[currentIndex].delay_ms;
    const nextDelay = ev[nextIndex].delay_ms;
    const delayDiff = (nextDelay - currentDelay) / speedRef.current;

    timerRef.current = setTimeout(() => {
      timerRef.current = null;

      const currentEvents = eventsRef.current;
      const newApplied = currentEvents.slice(0, nextIndex + 1);
      appliedCountRef.current = newApplied.length;
      setAppliedEvents(newApplied);

      if (nextIndex + 1 >= currentEvents.length) {
        setStatus('complete');
      } else {
        scheduleNextFrom(nextIndex);
      }
    }, delayDiff);
  }, []);

  const play = useCallback(() => {
    const ev = eventsRef.current;
    if (ev.length === 0) return;

    const currentCount = appliedCountRef.current;
    if (currentCount >= ev.length) return;

    setStatus('playing');

    if (currentCount === 0) {
      const firstApplied = ev.slice(0, 1);
      appliedCountRef.current = 1;
      setAppliedEvents(firstApplied);
      scheduleNextFrom(0);
    } else {
      scheduleNextFrom(currentCount - 1);
    }
  }, [scheduleNextFrom]);

  const pause = useCallback(() => {
    clearTimer();
    setStatus('paused');
  }, [clearTimer]);

  const nextStep = useCallback(() => {
    const ev = eventsRef.current;
    if (ev.length === 0) return;

    clearTimer();
    const currentCount = appliedCountRef.current;

    if (currentCount >= ev.length) {
      setStatus('complete');
      return;
    }

    const newApplied = ev.slice(0, currentCount + 1);
    appliedCountRef.current = newApplied.length;
    setAppliedEvents(newApplied);

    if (currentCount + 1 >= ev.length) {
      setStatus('complete');
    } else {
      setStatus('paused');
    }
  }, [clearTimer]);

  const reset = useCallback(() => {
    clearTimer();
    setStatus('idle');
    setAppliedEvents(EMPTY_EVENTS);
    appliedCountRef.current = 0;
  }, [clearTimer]);

  const setSpeed = useCallback((newSpeed: number) => {
    setSpeedState(newSpeed);
    speedRef.current = newSpeed;
  }, []);

  const currentHop = appliedEvents.length;
  const currentEvent = appliedEvents.length > 0 ? appliedEvents[appliedEvents.length - 1] : null;

  return {
    status,
    currentHop,
    totalHops: events.length,
    speed,
    currentEvent,
    appliedEvents,
    play,
    pause,
    nextStep,
    reset,
    setSpeed,
  };
}
