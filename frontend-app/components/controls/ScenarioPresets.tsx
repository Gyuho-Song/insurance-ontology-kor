'use client';

import { useState } from 'react';
import { getScenariosByCategory, CATEGORY_LABELS, CATEGORY_ORDER } from '@/lib/scenarios';
import type { Scenario, ScenarioCategory } from '@/lib/types';
import { cn } from '@/lib/utils';

const CATEGORY_COLORS: Partial<Record<ScenarioCategory, string>> = {
  mydata: 'bg-emerald-100 text-emerald-800 border-emerald-300',
  security: 'bg-red-100 text-red-800 border-red-300',
  comparison: 'bg-blue-100 text-blue-800 border-blue-300',
};

const CATEGORY_ACTIVE_COLORS: Partial<Record<ScenarioCategory, string>> = {
  mydata: 'bg-emerald-600 text-white border-emerald-600',
  security: 'bg-red-600 text-white border-red-600',
  comparison: 'bg-blue-600 text-white border-blue-600',
};

interface ScenarioPresetsProps {
  onSelect: (scenario: Scenario) => void;
}

export function ScenarioPresets({ onSelect }: ScenarioPresetsProps) {
  const [activeCategory, setActiveCategory] = useState<ScenarioCategory | null>(null);
  const categoryMap = getScenariosByCategory();

  const handleCategoryClick = (cat: ScenarioCategory) => {
    setActiveCategory((prev) => (prev === cat ? null : cat));
  };

  const activeScenarios = activeCategory ? categoryMap.get(activeCategory) ?? [] : [];

  return (
    <div className="space-y-2">
      {/* Level 1: Category chips */}
      <div className="flex flex-wrap gap-1.5">
        {CATEGORY_ORDER.map((cat) => {
          const items = categoryMap.get(cat);
          if (!items) return null;
          const isActive = activeCategory === cat;
          const baseColor = CATEGORY_COLORS[cat] ?? 'bg-gray-100 text-gray-700 border-gray-300';
          const activeColor = CATEGORY_ACTIVE_COLORS[cat] ?? 'bg-gray-800 text-white border-gray-800';

          return (
            <button
              key={cat}
              className={cn(
                'rounded-full border px-2.5 py-0.5 text-xs font-medium transition-colors',
                isActive ? activeColor : baseColor,
                'hover:opacity-80'
              )}
              onClick={() => handleCategoryClick(cat)}
            >
              {CATEGORY_LABELS[cat]} {items.length}
            </button>
          );
        })}
      </div>

      {/* Level 2: Scenario chips for selected category */}
      {activeCategory && activeScenarios.length > 0 && (
        <div className="border-t pt-2">
          <div className="mb-1.5 text-xs font-medium text-muted-foreground">
            {CATEGORY_LABELS[activeCategory]} ({activeScenarios.length})
          </div>
          <div className="flex flex-wrap gap-1.5">
            {activeScenarios.map((scenario) => (
              <button
                key={scenario.id}
                className="flex items-center gap-1 rounded-lg border border-input bg-background px-2.5 py-1 text-xs hover:bg-accent transition-colors"
                onClick={() => onSelect(scenario)}
              >
                <span className="font-mono text-[10px] text-muted-foreground">{scenario.id}</span>
                <span>{scenario.title}</span>
              </button>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
