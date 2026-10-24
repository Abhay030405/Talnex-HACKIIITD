import { Step, Steps } from 'fumadocs-ui/components/steps';
import { Tab, Tabs } from 'fumadocs-ui/components/tabs';
import defaultMdxComponents from 'fumadocs-ui/mdx';
import type { MDXComponents } from 'mdx/types';

import { AgentLoop } from '@/components/diagrams/agent-loop';
import { AskFlow } from '@/components/diagrams/ask-flow';
import { CheckPipeline } from '@/components/diagrams/check-pipeline';
import { JobLifecycle } from '@/components/diagrams/job-lifecycle';
import { LeetcodeFlow } from '@/components/diagrams/leetcode-flow';
import { PipelineDag } from '@/components/diagrams/pipeline-dag';
import { RecruiterFlow } from '@/components/diagrams/recruiter-flow';
import { SystemOverview } from '@/components/diagrams/system-overview';
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
    SystemOverview,
    PipelineDag,
    JobLifecycle,
    AgentLoop,
    RecruiterFlow,
    AskFlow,
    LeetcodeFlow,
    TestToken,
    ...components,
  } satisfies MDXComponents;
}

export const useMDXComponents = getMDXComponents;

declare global {
  type MDXProvidedComponents = ReturnType<typeof getMDXComponents>;
}
