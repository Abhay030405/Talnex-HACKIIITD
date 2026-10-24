import type { Metadata } from 'next';

import { Provider } from '@/components/provider';

import './global.css';

export const metadata: Metadata = {
  title: { default: 'TalNex MCP', template: '%s · TalNex MCP' },
  description: 'Let an AI assistant run TalNex checks, watch them live and read proof cards.',
};

export default function Layout({ children }: LayoutProps<'/'>) {
  return (
    <html lang="en" className="dark" suppressHydrationWarning>
      <body className="flex flex-col min-h-screen">
        <Provider>{children}</Provider>
      </body>
    </html>
  );
}
