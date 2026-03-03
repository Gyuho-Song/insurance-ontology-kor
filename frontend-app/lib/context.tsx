'use client';

import { createContext, useContext, useState, useCallback, useMemo, type ReactNode } from 'react';
import type { SubgraphNode, SubgraphEdge, TraversalEvent, RagMode, StageEvent } from './types';
import type { DemoCustomer } from './customers';

export interface MyDataConsentState {
  customer_id: string;
  customer_name: string;
  consented: boolean;
}

export type RightPanelTab = 'graph' | 'pipeline';

interface AppContextValue {
  selectedCustomer: DemoCustomer | null;
  scenarioId: string | undefined;
  activeSubgraph: { nodes: SubgraphNode[]; edges: SubgraphEdge[] } | undefined;
  activeTraversalEvents: TraversalEvent[] | undefined;
  mydataConsent: MyDataConsentState | null;
  ragMode: RagMode;
  pipelineStages: StageEvent[];
  rightPanelTab: RightPanelTab;
  setSelectedCustomer: (customer: DemoCustomer | null) => void;
  setScenarioId: (id: string | undefined) => void;
  setActiveSubgraph: (subgraph: { nodes: SubgraphNode[]; edges: SubgraphEdge[] } | undefined) => void;
  setActiveTraversalEvents: (events: TraversalEvent[] | undefined) => void;
  setRagMode: (mode: RagMode) => void;
  setPipelineStages: (stages: StageEvent[]) => void;
  setRightPanelTab: (tab: RightPanelTab) => void;
}

const AppContext = createContext<AppContextValue | undefined>(undefined);

export function AppProvider({ children }: { children: ReactNode }) {
  const [selectedCustomer, setSelectedCustomerState] = useState<DemoCustomer | null>(null);
  const [scenarioId, setScenarioId] = useState<string | undefined>(undefined);
  const [activeSubgraph, setActiveSubgraph] = useState<{ nodes: SubgraphNode[]; edges: SubgraphEdge[] } | undefined>(undefined);
  const [activeTraversalEvents, setActiveTraversalEvents] = useState<TraversalEvent[] | undefined>(undefined);
  const [ragMode, setRagMode] = useState<RagMode>('graphrag');
  const [pipelineStages, setPipelineStages] = useState<StageEvent[]>([]);
  const [rightPanelTab, setRightPanelTab] = useState<RightPanelTab>('graph');

  // Derive mydata consent from selected customer
  const mydataConsent: MyDataConsentState | null = selectedCustomer
    ? { customer_id: selectedCustomer.id, customer_name: selectedCustomer.name, consented: true }
    : null;

  const setSelectedCustomer = useCallback((customer: DemoCustomer | null) => {
    setSelectedCustomerState(customer);
    setScenarioId(undefined); // Reset scenario on customer change
  }, []);

  const value = useMemo<AppContextValue>(() => ({
    selectedCustomer,
    scenarioId,
    activeSubgraph,
    activeTraversalEvents,
    mydataConsent,
    ragMode,
    pipelineStages,
    rightPanelTab,
    setSelectedCustomer,
    setScenarioId,
    setActiveSubgraph,
    setActiveTraversalEvents,
    setRagMode,
    setPipelineStages,
    setRightPanelTab,
  }), [selectedCustomer, scenarioId, activeSubgraph, activeTraversalEvents, mydataConsent, ragMode, pipelineStages, rightPanelTab, setSelectedCustomer]);

  return (
    <AppContext.Provider value={value}>
      {children}
    </AppContext.Provider>
  );
}

export function useAppContext(): AppContextValue {
  const context = useContext(AppContext);
  if (!context) {
    throw new Error('useAppContext must be used within AppProvider');
  }
  return context;
}
