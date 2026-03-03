'use client';

import { useCallback } from 'react';
import { useAppContext } from '@/lib/context';
import { DualPanelLayout } from '@/components/layout/DualPanelLayout';
import { ChatPanel } from '@/components/chat/ChatPanel';
import { CustomerSwitcher } from '@/components/controls/CustomerSwitcher';
import { ScenarioPresets } from '@/components/controls/ScenarioPresets';
import { RagModeToggle } from '@/components/controls/RagModeToggle';
import { GraphPanel } from '@/components/graph/GraphPanel';
import { Badge } from '@/components/ui/badge';
import type { Scenario } from '@/lib/types';
import type { DemoCustomer } from '@/lib/customers';

export default function Home() {
  const {
    selectedCustomer,
    scenarioId,
    activeSubgraph,
    activeTraversalEvents,
    mydataConsent,
    ragMode,
    setSelectedCustomer,
    setScenarioId,
    setRagMode,
  } = useAppContext();

  const handleScenarioSelect = useCallback((scenario: Scenario) => {
    setScenarioId(scenario.id);
  }, [setScenarioId]);

  const handleScenarioConsumed = useCallback(() => {
    setScenarioId(undefined);
  }, [setScenarioId]);

  const handleCustomerChange = useCallback((customer: DemoCustomer | null) => {
    setSelectedCustomer(customer);
  }, [setSelectedCustomer]);

  return (
    <DualPanelLayout
      header={
        <div className="flex items-center justify-between gap-3">
          <h1 className="text-lg font-semibold whitespace-nowrap">Insurance Ontology GraphRAG</h1>
          <CustomerSwitcher
            selectedCustomerId={selectedCustomer?.id ?? null}
            onCustomerChange={handleCustomerChange}
          />
        </div>
      }
      leftPanel={
        <div className="flex h-full flex-col">
          <div className="border-b p-3 space-y-2">
            <div className="flex items-center justify-between">
              <span className="text-sm font-medium">시나리오 (31)</span>
              <RagModeToggle ragMode={ragMode} onRagModeChange={setRagMode} />
            </div>
            <ScenarioPresets onSelect={handleScenarioSelect} />
          </div>
          <div className="flex-1 min-h-0">
            <ChatPanel
              scenarioId={scenarioId}
              onScenarioConsumed={handleScenarioConsumed}
            />
          </div>
        </div>
      }
      rightPanel={
        <GraphPanel
          subgraph={activeSubgraph}
          traversalEvents={activeTraversalEvents}
        />
      }
      footer={
        <div className="flex items-center gap-4 text-xs">
          <Badge variant={ragMode === 'graphrag' ? 'default' : 'secondary'}>
            {ragMode === 'comparison' ? '비교' : ragMode === 'naive' ? 'Naive' : 'GraphRAG'}
          </Badge>
          {mydataConsent ? (
            <Badge variant="default" className="bg-emerald-600 text-white">
              MyData: {mydataConsent.customer_name} ({selectedCustomer?.products.length}건)
            </Badge>
          ) : (
            <span className="text-muted-foreground">마이데이터 미연동</span>
          )}
          <span className="ml-auto">v0.4.0</span>
        </div>
      }
    />
  );
}
