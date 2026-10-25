import { Step, Steps } from 'fumadocs-ui/components/steps';
import { Tab, Tabs } from 'fumadocs-ui/components/tabs';
import defaultMdxComponents from 'fumadocs-ui/mdx';
import type { MDXComponents } from 'mdx/types';

import { AgentLoop } from '@/components/docs/diagrams/agent-loop';
import { AskFlow } from '@/components/docs/diagrams/ask-flow';
import { CheckPipeline } from '@/components/docs/diagrams/check-pipeline';
import { JobLifecycle } from '@/components/docs/diagrams/job-lifecycle';
import { LeetcodeFlow } from '@/components/docs/diagrams/leetcode-flow';
import { PipelineDag } from '@/components/docs/diagrams/pipeline-dag';
import { RecruiterFlow } from '@/components/docs/diagrams/recruiter-flow';
import { SystemOverview } from '@/components/docs/diagrams/system-overview';
import { NeverBlameLadder } from '@/components/docs/diagrams/never-blame';
import { OrchestrationFlow } from '@/components/docs/diagrams/orchestration-flow';
import { RequestFlow } from '@/components/docs/diagrams/request-flow';
import { SessionToken, TestToken } from '@/components/docs/test-token';

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
    OrchestrationFlow,
    TestToken,
    SessionToken,
    ...components,
  } satisfies MDXComponents;
}

export const useMDXComponents = getMDXComponents;

declare global {
  type MDXProvidedComponents = ReturnType<typeof getMDXComponents>;
}
