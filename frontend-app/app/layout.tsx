import type { Metadata } from 'next';
import { AppProvider } from '@/lib/context';
import { AuthProvider } from '@/lib/auth-context';
import { ErrorBoundary } from '@/components/ErrorBoundary';
import './globals.css';

export const metadata: Metadata = {
  title: 'Insurance Ontology GraphRAG Demo',
  description: 'Insurance Ontology GraphRAG Demo Application',
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="ko">
      <body>
        <ErrorBoundary>
          <AuthProvider>
            <AppProvider>{children}</AppProvider>
          </AuthProvider>
        </ErrorBoundary>
      </body>
    </html>
  );
}
