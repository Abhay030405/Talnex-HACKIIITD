import type { BaseLayoutProps } from 'fumadocs-ui/layouts/shared';

import { appName, gitConfig } from './shared';

export function baseOptions(): BaseLayoutProps {
  return {
    nav: {
      title: (
        <span className="tx-brand">
          <span className="tx-brand__mark" aria-hidden />
          {appName}
        </span>
      ),
    },
    githubUrl: `https://github.com/${gitConfig.user}/${gitConfig.repo}`,
    themeSwitch: { enabled: false },
  };
}
