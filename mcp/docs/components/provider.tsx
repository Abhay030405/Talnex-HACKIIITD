'use client';
import { RootProvider } from 'fumadocs-ui/provider/next';
import type { ReactNode } from 'react';

import SearchDialog from '@/components/search';

/** TalNex is dark only: black with crimson. */
export function Provider({ children }: { children: ReactNode }) {
  return (
    <RootProvider search={{ SearchDialog }} theme={{ forcedTheme: 'dark', defaultTheme: 'dark', hotKey: false }}>
      {children}
    </RootProvider>
  );
}
