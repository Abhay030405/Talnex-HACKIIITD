import { Step, Steps } from 'fumadocs-ui/components/steps';
import { Tab, Tabs } from 'fumadocs-ui/components/tabs';
import defaultMdxComponents from 'fumadocs-ui/mdx';
import type { MDXComponents } from 'mdx/types';

import { CheckPipeline } from '@/components/diagrams/check-pipeline';
import { NeverBlameLadder } from '@/components/diagrams/never-blame';
import { RequestFlow } from '@/components/diagrams/request-flow';
import { TestToken } from '@/components/test-token';

export function getMDXComponents(components?: MDXComponents) {
  return {
    ...defaultMdxComponents,
    Tab,
    Tabs,
    Step,
    Steps,
    RequestFlow,
    CheckPipeline,
    NeverBlameLadder,
    TestToken,
    ...components,
  } satisfies MDXComponents;
}

export const useMDXComponents = getMDXComponents;

declare global {
  type MDXProvidedComponents = ReturnType<typeof getMDXComponents>;
}
