import type { ReactNode } from 'react';

interface DualPanelLayoutProps {
  leftPanel: ReactNode;
  rightPanel: ReactNode;
  header: ReactNode;
  footer: ReactNode;
}

export function DualPanelLayout({
  leftPanel,
  rightPanel,
  header,
  footer,
}: DualPanelLayoutProps) {
  return (
    <div className="flex h-screen flex-col">
      {/* Header */}
      <header className="border-b px-4 py-3">
        {header}
      </header>

      {/* Main Content — Side by Side */}
      <main className="flex flex-1 overflow-hidden">
        {/* Left Panel — Chat (45%) */}
        <div className="w-[45%] border-r flex flex-col min-h-0 max-lg:w-full">
          {leftPanel}
        </div>

        {/* Right Panel — Graph (55%) */}
        <div className="w-[55%] flex flex-col max-lg:hidden">
          {rightPanel}
        </div>
      </main>

      {/* Footer */}
      <footer className="border-t px-4 py-2 text-xs text-muted-foreground">
        {footer}
      </footer>
    </div>
  );
}
