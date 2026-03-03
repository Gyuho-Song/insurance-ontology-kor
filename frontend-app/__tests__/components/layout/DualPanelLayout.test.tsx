import { render, screen } from '@testing-library/react';
import { DualPanelLayout } from '@/components/layout/DualPanelLayout';

describe('DualPanelLayout', () => {
  it('should render left panel content', () => {
    render(
      <DualPanelLayout
        leftPanel={<div>Chat Content</div>}
        rightPanel={<div>Graph Content</div>}
        header={<div>Header</div>}
        footer={<div>Footer</div>}
      />
    );

    expect(screen.getByText('Chat Content')).toBeInTheDocument();
  });

  it('should render right panel content', () => {
    render(
      <DualPanelLayout
        leftPanel={<div>Chat Content</div>}
        rightPanel={<div>Graph Content</div>}
        header={<div>Header</div>}
        footer={<div>Footer</div>}
      />
    );

    expect(screen.getByText('Graph Content')).toBeInTheDocument();
  });

  it('should render header and footer', () => {
    render(
      <DualPanelLayout
        leftPanel={<div>Chat</div>}
        rightPanel={<div>Graph</div>}
        header={<div>Test Header</div>}
        footer={<div>Test Footer</div>}
      />
    );

    expect(screen.getByText('Test Header')).toBeInTheDocument();
    expect(screen.getByText('Test Footer')).toBeInTheDocument();
  });

  it('should have proper layout structure with main container', () => {
    const { container } = render(
      <DualPanelLayout
        leftPanel={<div>Chat</div>}
        rightPanel={<div>Graph</div>}
        header={<div>Header</div>}
        footer={<div>Footer</div>}
      />
    );

    // Should have a main container
    const main = container.querySelector('main');
    expect(main).toBeInTheDocument();
  });
});
