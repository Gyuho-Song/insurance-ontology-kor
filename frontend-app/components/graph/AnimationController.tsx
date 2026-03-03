'use client';

import { Play, Pause, SkipForward, RotateCcw } from 'lucide-react';
import { Button } from '@/components/ui/button';
import type { AnimationStatus } from '@/lib/useGraphAnimation';

const SPEED_CYCLE = [0.5, 1, 2] as const;

interface AnimationControllerProps {
  status: AnimationStatus;
  currentHop: number;
  totalHops: number;
  speed: number;
  onPlay: () => void;
  onPause: () => void;
  onNextStep: () => void;
  onReset: () => void;
  onSpeedChange: (speed: number) => void;
}

const STATUS_LABELS: Record<AnimationStatus, string> = {
  idle: '대기',
  playing: '재생 중',
  paused: '일시정지',
  complete: '완료',
};

export function AnimationController({
  status,
  currentHop,
  totalHops,
  speed,
  onPlay,
  onPause,
  onNextStep,
  onReset,
  onSpeedChange,
}: AnimationControllerProps) {
  const isComplete = status === 'complete';
  const isPlaying = status === 'playing';

  const handleSpeedCycle = () => {
    const currentIndex = SPEED_CYCLE.indexOf(speed as (typeof SPEED_CYCLE)[number]);
    const nextIndex = (currentIndex + 1) % SPEED_CYCLE.length;
    onSpeedChange(SPEED_CYCLE[nextIndex]);
  };

  return (
    <div className="flex items-center gap-2 rounded-lg border bg-muted/30 px-3 py-2">
      {/* Play / Pause */}
      {isPlaying ? (
        <Button
          variant="ghost"
          size="sm"
          onClick={onPause}
          aria-label="Pause"
        >
          <Pause className="h-4 w-4" />
        </Button>
      ) : (
        <Button
          variant="ghost"
          size="sm"
          onClick={onPlay}
          aria-label="Play"
          disabled={isComplete}
        >
          <Play className="h-4 w-4" />
        </Button>
      )}

      {/* Next Step */}
      <Button
        variant="ghost"
        size="sm"
        onClick={onNextStep}
        aria-label="Next"
        disabled={isComplete}
      >
        <SkipForward className="h-4 w-4" />
      </Button>

      {/* Reset */}
      <Button
        variant="ghost"
        size="sm"
        onClick={onReset}
        aria-label="Reset"
      >
        <RotateCcw className="h-4 w-4" />
      </Button>

      {/* Separator */}
      <div className="mx-1 h-4 w-px bg-border" />

      {/* Speed */}
      <Button
        variant="outline"
        size="sm"
        onClick={handleSpeedCycle}
        aria-label={`Speed ${speed}x`}
        className="min-w-[3rem] text-xs"
      >
        {speed}x
      </Button>

      {/* Progress */}
      <span className="text-xs text-muted-foreground">
        {currentHop} / {totalHops}
      </span>

      {/* Status */}
      <span className="ml-auto text-xs font-medium text-muted-foreground">
        {STATUS_LABELS[status]}
      </span>
    </div>
  );
}
