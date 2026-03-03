import { render, screen, fireEvent } from '@testing-library/react';
import { AppProvider, useAppContext } from '@/lib/context';

function TestConsumer() {
  const {
    selectedCustomer, scenarioId, mydataConsent, ragMode,
    setSelectedCustomer, setScenarioId, setRagMode,
    activeSubgraph, activeTraversalEvents, setActiveSubgraph, setActiveTraversalEvents,
  } = useAppContext();

  return (
    <div>
      <span data-testid="customer">{selectedCustomer?.name || 'none'}</span>
      <span data-testid="scenario">{scenarioId || 'none'}</span>
      <span data-testid="consent">{mydataConsent ? mydataConsent.customer_name : 'none'}</span>
      <span data-testid="rag-mode">{ragMode}</span>
      <span data-testid="subgraph">{activeSubgraph ? `${activeSubgraph.nodes.length}nodes` : 'none'}</span>
      <span data-testid="traversal">{activeTraversalEvents ? `${activeTraversalEvents.length}events` : 'none'}</span>
      <button onClick={() => setSelectedCustomer({ id: 'CUSTOMER_PARK', name: '박지영', products: [{ policy_name: 'H종신보험', product_type: 'whole_life' }] })}>Select Customer</button>
      <button onClick={() => setSelectedCustomer(null)}>Deselect Customer</button>
      <button onClick={() => setScenarioId('B')}>Set Scenario</button>
      <button onClick={() => setRagMode('naive')}>Set Naive</button>
      <button onClick={() => setActiveSubgraph({ nodes: [{ id: 'P1', type: 'Policy', label: 'P1', properties: {} }], edges: [] })}>Set Subgraph</button>
      <button onClick={() => setActiveTraversalEvents([{ type: 'node_activated', hop: 0, delay_ms: 0, data: { node_id: 'P1' } }])}>Set Traversal</button>
      <button onClick={() => { setActiveSubgraph(undefined); setActiveTraversalEvents(undefined); }}>Clear Graph</button>
    </div>
  );
}

describe('AppContext', () => {
  it('should provide default values', () => {
    render(
      <AppProvider>
        <TestConsumer />
      </AppProvider>
    );

    expect(screen.getByTestId('customer')).toHaveTextContent('none');
    expect(screen.getByTestId('scenario')).toHaveTextContent('none');
    expect(screen.getByTestId('consent')).toHaveTextContent('none');
    expect(screen.getByTestId('rag-mode')).toHaveTextContent('graphrag');
  });

  it('should allow selecting a customer and derive mydataConsent', () => {
    render(
      <AppProvider>
        <TestConsumer />
      </AppProvider>
    );

    fireEvent.click(screen.getByText('Select Customer'));
    expect(screen.getByTestId('customer')).toHaveTextContent('박지영');
    expect(screen.getByTestId('consent')).toHaveTextContent('박지영');
  });

  it('should clear mydataConsent when customer is deselected', () => {
    render(
      <AppProvider>
        <TestConsumer />
      </AppProvider>
    );

    fireEvent.click(screen.getByText('Select Customer'));
    expect(screen.getByTestId('consent')).toHaveTextContent('박지영');

    fireEvent.click(screen.getByText('Deselect Customer'));
    expect(screen.getByTestId('customer')).toHaveTextContent('none');
    expect(screen.getByTestId('consent')).toHaveTextContent('none');
  });

  it('should allow setting scenario', () => {
    render(
      <AppProvider>
        <TestConsumer />
      </AppProvider>
    );

    fireEvent.click(screen.getByText('Set Scenario'));
    expect(screen.getByTestId('scenario')).toHaveTextContent('B');
  });

  it('should reset scenario when customer changes', () => {
    render(
      <AppProvider>
        <TestConsumer />
      </AppProvider>
    );

    fireEvent.click(screen.getByText('Set Scenario'));
    expect(screen.getByTestId('scenario')).toHaveTextContent('B');

    fireEvent.click(screen.getByText('Select Customer'));
    expect(screen.getByTestId('scenario')).toHaveTextContent('none');
  });

  it('should allow changing ragMode', () => {
    render(
      <AppProvider>
        <TestConsumer />
      </AppProvider>
    );

    fireEvent.click(screen.getByText('Set Naive'));
    expect(screen.getByTestId('rag-mode')).toHaveTextContent('naive');
  });

  it('should have undefined activeSubgraph and activeTraversalEvents by default', () => {
    render(
      <AppProvider>
        <TestConsumer />
      </AppProvider>
    );

    expect(screen.getByTestId('subgraph')).toHaveTextContent('none');
    expect(screen.getByTestId('traversal')).toHaveTextContent('none');
  });

  it('should allow setting and clearing graph state', () => {
    render(
      <AppProvider>
        <TestConsumer />
      </AppProvider>
    );

    fireEvent.click(screen.getByText('Set Subgraph'));
    fireEvent.click(screen.getByText('Set Traversal'));
    expect(screen.getByTestId('subgraph')).toHaveTextContent('1nodes');
    expect(screen.getByTestId('traversal')).toHaveTextContent('1events');

    fireEvent.click(screen.getByText('Clear Graph'));
    expect(screen.getByTestId('subgraph')).toHaveTextContent('none');
    expect(screen.getByTestId('traversal')).toHaveTextContent('none');
  });
});
