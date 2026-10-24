'use client';
// How a recruiter check moves through the job queue, from the resume to the proof report.
// Every stage and every arrow below comes from the pipeline_stages rows in backend/migrations (000007 to 000030),
// the Go StartChecks / auto_confirm code (backend/internal/pipeline/autoconfirm.go) and the Python handlers that start
// the next pipeline (project_summary starts recruiter_report). If a migration changes the order, change this file too.
import {
  BaseEdge,
  type Edge,
  EdgeLabelRenderer,
  type EdgeProps,
  getSmoothStepPath,
  Handle,
  MarkerType,
  MiniMap,
  type Node,
  type NodeProps,
  Position,
  ReactFlow,
  type ReactFlowInstance,
} from '@xyflow/react';
import '@xyflow/react/dist/style.css';
import { useCallback, useEffect, useRef, useState } from 'react';

type Runner = 'go' | 'py' | 'api' | 'human' | 'out';
type Use = 'llm' | 'browser' | 'fetch' | 'search' | 'sandbox' | 'github' | 'api';

type StageData = { name: string; run: Runner; uses?: Use[]; note?: string; mono?: boolean };
type LoopData = { name: string; uses?: Use[]; lines: string[]; tone?: 'ladder' | 'verdict' };
type LaneData = { title: string; sub?: string; tone: 'group' | 'lane' | 'inset' };
type NoteData = { title: string; lines: string[]; tone: 'safety' | 'plain' };

type StageNode = Node<StageData, 'stage'>;
type LoopNode = Node<LoopData, 'loop'>;
type LaneNode = Node<LaneData, 'lane'>;
type NoteNode = Node<NoteData, 'note'>;
type FlowNode = StageNode | LoopNode | LaneNode | NoteNode;

const USE_LABEL: Record<Use, string> = {
  llm: 'LLM',
  browser: 'Browser',
  fetch: 'Fetch',
  search: 'Search',
  sandbox: 'sandboxd',
  github: 'GitHub API',
  api: 'public API',
};
const RUN_LABEL: Record<Runner, string> = { go: 'GO', py: 'PY', api: 'API', human: 'HUMAN', out: 'OUT' };

const SIDES = [
  ['t', Position.Top],
  ['r', Position.Right],
  ['b', Position.Bottom],
  ['l', Position.Left],
] as const;

function Handles() {
  return (
    <>
      {SIDES.map(([id, position]) => (
        <span key={id}>
          <Handle type="source" id={id} position={position} isConnectable={false} />
          <Handle type="target" id={`${id}-in`} position={position} isConnectable={false} />
        </span>
      ))}
    </>
  );
}

function Chips({ uses }: { uses?: Use[] }) {
  if (!uses?.length) return null;
  return (
    <>
      {uses.map((u) => (
        <span key={u} className={`ox-chip ox-chip--${u}`}>{USE_LABEL[u]}</span>
      ))}
    </>
  );
}

function Stage({ data }: NodeProps<StageNode>) {
  return (
    <div className={`ox-stage ox-stage--${data.run}`}>
      <Handles />
      <div className={data.mono === false ? 'ox-stage__title' : 'ox-stage__name'}>{data.name}</div>
      <div className="ox-stage__tags">
        <span className={`ox-run ox-run--${data.run}`}>{RUN_LABEL[data.run]}</span>
        <Chips uses={data.uses} />
      </div>
      {data.note ? <div className="ox-stage__note">{data.note}</div> : null}
    </div>
  );
}

function Loop({ data }: NodeProps<LoopNode>) {
  return (
    <div className={`ox-loop ox-loop--${data.tone ?? 'plain'}`}>
      <Handles />
      <div className="ox-loop__name">{data.name}</div>
      {data.uses?.length ? <div className="ox-stage__tags"><Chips uses={data.uses} /></div> : null}
      <ul className="ox-loop__lines">
        {data.lines.map((l) => <li key={l}>{l}</li>)}
      </ul>
    </div>
  );
}

function Lane({ data, width, height }: NodeProps<LaneNode>) {
  return (
    <div className={`ox-lane ox-lane--${data.tone}`} style={{ width, height }}>
      {/* the inset hangs under live_test, so its top handle sits under that box, not in the middle */}
      <Handle type="target" id="t-in" position={Position.Top} isConnectable={false}
              style={data.tone === 'inset' ? { left: 120 } : undefined} />
      <Handle type="target" id="l-in" position={Position.Left} isConnectable={false} />
      <Handle type="source" id="r" position={Position.Right} isConnectable={false} />
      <div className="ox-lane__head">
        <span className="ox-lane__title">{data.title}</span>
        {data.sub ? <span className="ox-lane__sub">{data.sub}</span> : null}
      </div>
    </div>
  );
}

function Note({ data }: NodeProps<NoteNode>) {
  return (
    <div className={`ox-note ox-note--${data.tone}`}>
      <div className="ox-note__title">{data.title}</div>
      <ul>
        {data.lines.map((l) => <li key={l}>{l}</li>)}
      </ul>
    </div>
  );
}

// An edge whose turns we place by hand (cx / cy), so lines run through the gaps between lanes instead of across boxes.
type RouteData = { cx?: number; cy?: number; at?: { x: number; y: number }; look?: 'main' | 'soft' | 'join' };
type RouteEdge = Edge<RouteData, 'route'>;

function Route({ id, sourceX, sourceY, targetX, targetY, sourcePosition, targetPosition, label, markerEnd, data }: EdgeProps<RouteEdge>) {
  const [path, lx, ly] = getSmoothStepPath({
    sourceX, sourceY, targetX, targetY, sourcePosition, targetPosition,
    borderRadius: 10, centerX: data?.cx, centerY: data?.cy,
  });
  const x = data?.at?.x ?? lx;
  const y = data?.at?.y ?? ly;
  return (
    <>
      <BaseEdge id={id} path={path} markerEnd={markerEnd} />
      {label ? (
        <EdgeLabelRenderer>
          <div className={`ox-edge-label ox-edge-label--${data?.look ?? 'plain'}`}
               style={{ transform: `translate(-50%, -50%) translate(${x}px, ${y}px)` }}>
            {label}
          </div>
        </EdgeLabelRenderer>
      ) : null}
    </>
  );
}

const nodeTypes = { stage: Stage, loop: Loop, lane: Lane, note: Note };
const edgeTypes = { route: Route };

// ---- layout (flow units). Stage boxes are 180 x 80; lanes are see-through frames drawn behind them.
const W = 180;
const COL = [545, 755, 965, 1175, 1385, 1595, 1805];

const stage = (id: string, x: number, y: number, name: string, run: Runner, uses?: Use[], note?: string,
               mono = true): StageNode => ({
  id, type: 'stage', position: { x, y }, data: { name, run, uses, note, mono }, width: W,
});
const lane = (id: string, x: number, y: number, width: number, height: number, title: string, sub: string | undefined,
              tone: LaneData['tone']): LaneNode => ({
  id, type: 'lane', position: { x, y }, width, height, data: { title, sub, tone },
  selectable: false, draggable: false, zIndex: -1, style: { pointerEvents: 'none' },
});
const loop = (id: string, x: number, name: string, lines: string[], uses?: Use[], tone?: LoopData['tone']): LoopNode => ({
  id, type: 'loop', position: { x, y: 240 }, width: 170, data: { name, lines, uses, tone },
});

const nodes: FlowNode[] = [
  // frames first, so they sit behind everything
  lane('g-cand', 0, 0, 260, 620, 'Candidate', 'one per resume', 'group'),
  lane('g-proj', 290, 0, 1730, 890, 'Per project × N', 'recruiter pipeline · every project runs in parallel', 'group'),
  lane('l-live', 525, 40, 1475, 390, 'Live-site track', undefined, 'lane'),
  lane('l-inset', 935, 185, 1045, 235, 'inside live_test', 'per claim · a few claims at a time', 'inset'),
  lane('l-repo', 525, 450, 1475, 170, 'Repository + sandbox VM track', undefined, 'lane'),
  lane('l-hist', 525, 640, 1475, 230, 'GitHub + code history track', undefined, 'lane'),
  lane('g-score', 2060, 220, 270, 650, 'Scoring', 'per project · tracks join', 'group'),
  lane('g-coding', 290, 915, 1080, 160, 'Coding profiles', 'per candidate · all 5 side by side', 'group'),
  lane('g-report', 1410, 915, 920, 160, 'Report', undefined, 'group'),

  // candidate
  stage('resume', 40, 40, 'Resume PDF', 'api', undefined, 'Go API queues the job', false),
  stage('resume_read', 40, 160, 'resume_read', 'py', ['llm'], 'projects, links, handles'),
  stage('auto_confirm', 40, 280, 'auto_confirm', 'go', undefined, 'role set: start at once'),
  stage('confirm', 40, 400, 'Recruiter confirms', 'human', undefined, 'checks what was found', false),
  stage('start', 40, 520, 'StartChecks', 'go', undefined, 'start_pipeline per project'),

  // per project: start
  stage('precheck', 315, 380, 'precheck', 'py', ['fetch'], 'do the links open?'),

  // live-site track
  stage('claims', COL[0], 80, 'claims', 'py', ['llm'], 'resume bullets + README'),
  stage('test_plan', COL[1], 80, 'test_plan', 'py', ['llm'], 'plans + score checklist'),
  stage('live_test', COL[2], 80, 'live_test', 'py', ['llm', 'browser'], 'uses the real site'),
  stage('proof_check', COL[3], 80, 'proof_check', 'py', undefined, 'safety net: no silent gaps'),

  // the testing loop, inside live_test
  loop('t-plan', 955, 'test planner', ['steps + expected result', 'guard: no pay, delete, message'], ['llm']),
  loop('t-run', 1162, 'runner', ['one action at a time', 'screenshot every step'], ['browser', 'llm']),
  loop('t-check', 1369, 'proof check', ['a separate model call', 'sees only the screenshots'], ['llm']),
  loop('t-ladder', 1576, 'never-blame ladder', ['1 page loaded?', '2 wait ~1 min', '3 2nd try, other way', '4 2nd independent check'],
       ['fetch'], 'ladder'),
  loop('t-verdict', 1783, 'verdict', ['works', 'partly works', 'broken (ladder only)', 'could not test'], undefined, 'verdict'),

  // repository + sandbox track
  stage('sandbox_run', COL[0], 495, 'sandbox_run', 'py', ['sandbox', 'llm'], 'clone, build, start'),
  stage('route_discovery', COL[1], 495, 'route_discovery', 'py', ['sandbox', 'llm'], 'routes ↔ claims'),
  stage('sandbox_plan', COL[2], 495, 'sandbox_plan', 'py', ['llm'], 'backend HTTP tests'),
  stage('sandbox_test', COL[3], 495, 'sandbox_test', 'py', ['sandbox', 'llm'], 'real requests + ladder'),
  stage('repo_tests', COL[4], 495, 'repo_tests', 'py', ['sandbox'], "the repo's own tests"),
  stage('code_review', COL[5], 495, 'code_review', 'py', ['sandbox', 'llm'], 'read from code, not run'),
  stage('sandbox_end', COL[6], 495, 'sandbox_end', 'py', ['sandbox'], 'destroy the VM'),

  // GitHub + code history track
  stage('github_check', COL[0], 680, 'github_check', 'go', ['github'], 'repo facts and dates'),
  stage('originality', COL[1], 775, 'originality', 'py', ['llm', 'search'], 'also waits for claims'),
  stage('code_locate', COL[2], 680, 'code_locate', 'py', ['llm', 'fetch'], 'claim → files + lines'),
  stage('github_history', COL[3], 680, 'github_history', 'go', ['github'], 'blame + push times'),
  stage('authorship_read', COL[4], 680, 'authorship_read', 'py', ['llm'], 'who wrote each feature'),

  // scoring, per project
  stage('track_reconcile', 2110, 260, 'track_reconcile', 'py', undefined, 'live and repo must agree'),
  stage('feature_score', 2110, 450, 'feature_score', 'py', ['llm'], 'score /10 per feature'),
  stage('project_summary', 2110, 680, 'project_summary', 'py', undefined, 'last one starts report'),

  // coding profiles, per candidate
  stage('codeforces', 320, 965, 'codeforces', 'go', ['api'], 'rating, contests'),
  stage('github_profile', 530, 965, 'github_profile', 'go', ['github'], 'the whole account'),
  stage('leetcode', 740, 965, 'leetcode', 'py', ['fetch'], 'profile facts'),
  stage('leetcode_replay', 950, 965, 'leetcode_replay', 'py', ['api'], 'paste check'),
  stage('codechef', 1160, 965, 'codechef', 'py', ['fetch'], 'profile facts'),

  // report, per candidate
  stage('candidate_report', 1450, 965, 'candidate_report', 'py', undefined, 'builds the report'),
  stage('resume_cleanup', 1780, 965, 'resume_cleanup', 'go', undefined, 'deletes the resume'),
  stage('report', 2110, 965, 'Proof report', 'out', undefined, 'score /10 · proof · flags', false),

  // side notes
  {
    id: 'n-safety', type: 'note', position: { x: 2060, y: 0 }, width: 270,
    data: {
      tone: 'safety', title: 'Safety rails',
      lines: ['never pays, deletes or messages', 'page text is data, not orders', 'a human confirms paid runs',
              'flags sit beside the score'],
    },
  },
  {
    id: 'n-ask', type: 'note', position: { x: 15, y: 650 }, width: 220,
    data: {
      tone: 'plain', title: 'On demand',
      lines: ['report_answer', 'custom_test', 'walkthrough_answer', 'one job each, nothing chained'],
    },
  },
];

const arrow = { type: MarkerType.ArrowClosed, width: 14, height: 14 } as const;
const link = (from: string, fromSide: string, to: string, toSide: string, label?: string, data: RouteData = {}): RouteEdge => ({
  id: `${from}:${fromSide}-${to}:${toSide}`, type: 'route',
  source: from, sourceHandle: fromSide, target: to, targetHandle: `${toSide}-in`,
  label, data, animated: data.look === 'main',
  className: data.look ? `ox-edge--${data.look}` : undefined,
  markerEnd: arrow,
});
const main = (d: RouteData = {}): RouteData => ({ ...d, look: 'main' });

const edges: RouteEdge[] = [
  // candidate
  link('resume', 'b', 'resume_read', 't', 'jobs table', { at: { x: 130, y: 140 } }),
  link('resume_read', 'b', 'auto_confirm', 't'),
  link('auto_confirm', 'b', 'confirm', 't', 'no role: wait', { look: 'soft', at: { x: 130, y: 380 } }),
  link('auto_confirm', 'l', 'start', 'l', 'role', { cx: 20, look: 'soft', at: { x: 20, y: 440 } }),
  link('confirm', 'b', 'start', 't', undefined, main()),
  link('start', 'r', 'precheck', 'l', '× N projects', main({ cx: 268, at: { x: 268, y: 470 } })),
  link('start', 'r', 'g-coding', 'l', 'coding', { cx: 250, at: { x: 250, y: 860 } }),

  // per project fan-out from precheck
  link('precheck', 'r', 'claims', 'l', 'parallel', main({ cx: 510, at: { x: 510, y: 250 } })),
  link('precheck', 'r', 'sandbox_run', 'l', undefined, { cx: 510 }),
  link('precheck', 'r', 'github_check', 'l', undefined, { cx: 510 }),

  // live-site track
  link('claims', 'r', 'test_plan', 'l', undefined, main()),
  link('test_plan', 'r', 'live_test', 'l', undefined, main()),
  link('live_test', 'r', 'proof_check', 'l', undefined, main()),
  link('live_test', 'b', 'l-inset', 't', undefined, { look: 'soft' }),
  link('claims', 'b', 'route_discovery', 't', 'needs claims', { cy: 440, at: { x: 735, y: 440 } }),

  // testing loop
  link('t-plan', 'r', 't-run', 'l'),
  link('t-run', 'r', 't-check', 'l'),
  link('t-check', 'r', 't-ladder', 'l'),
  link('t-ladder', 'r', 't-verdict', 'l'),
  link('t-check', 't', 't-verdict', 't', 'it worked', { cy: 225, at: { x: 1660, y: 225 } }),
  link('t-ladder', 'b', 't-run', 'b', '2nd try, a different way', { cy: 400, look: 'soft', at: { x: 1455, y: 400 } }),

  // repository + sandbox track
  link('sandbox_run', 'r', 'route_discovery', 'l'),
  link('route_discovery', 'r', 'sandbox_plan', 'l'),
  link('sandbox_plan', 'r', 'sandbox_test', 'l'),
  link('sandbox_test', 'r', 'repo_tests', 'l'),
  link('repo_tests', 'r', 'code_review', 'l'),
  link('code_review', 'r', 'sandbox_end', 'l'),
  link('route_discovery', 'b', 'code_locate', 't', 'route map', { cy: 630, at: { x: 945, y: 630 } }),

  // GitHub + code history track
  link('github_check', 'r', 'code_locate', 'l'),
  link('github_check', 'b', 'originality', 'l'),
  link('code_locate', 'r', 'github_history', 'l'),
  link('github_history', 'r', 'authorship_read', 'l'),

  // the tracks join
  link('proof_check', 'r', 'track_reconcile', 'l', 'joins', main({ cx: 2040, at: { x: 1700, y: 120 } })),
  link('sandbox_end', 'r', 'track_reconcile', 'l', 'joins', { cx: 2040, look: 'join', at: { x: 2040, y: 440 } }),
  link('track_reconcile', 'b', 'feature_score', 't', undefined, main()),
  link('feature_score', 'b', 'project_summary', 't', undefined, main()),
  link('authorship_read', 'r', 'project_summary', 'l', 'joins', { cx: 2040, look: 'join', at: { x: 1800, y: 720 } }),
  link('originality', 'r', 'project_summary', 'l', undefined, { cx: 2040, look: 'join' }),

  // report
  link('project_summary', 'b', 'candidate_report', 't', 'last project done · per candidate', main({ cy: 902, at: { x: 1860, y: 902 } })),
  link('g-coding', 'r', 'candidate_report', 'l', 'waits', { look: 'soft', at: { x: 1410, y: 985 } }),
  link('candidate_report', 'r', 'resume_cleanup', 'l', undefined, main()),
  link('resume_cleanup', 'r', 'report', 'l', undefined, main()),
];

const FIT = { padding: 0.03 };

function Legend() {
  return (
    <div className="ox-legend" aria-label="Legend">
      <span><b className="ox-run ox-run--go">GO</b> Go worker</span>
      <span><b className="ox-run ox-run--py">PY</b> Python worker</span>
      <span><b className="ox-chip ox-chip--llm">LLM</b> model call</span>
      <span><b className="ox-chip ox-chip--browser">Browser</b> TinyFish browser agent</span>
      <span><b className="ox-chip ox-chip--fetch">Fetch</b> <b className="ox-chip ox-chip--search">Search</b> free TinyFish calls</span>
      <span><b className="ox-chip ox-chip--sandbox">sandboxd</b> throwaway VM</span>
      <span><b className="ox-chip ox-chip--github">GitHub API</b></span>
      <span><i className="ox-key ox-key--main" /> main path</span>
      <span><i className="ox-key ox-key--soft" /> wait / optional</span>
    </div>
  );
}

export function OrchestrationFlow() {
  const figure = useRef<HTMLElement>(null);
  const flow = useRef<ReactFlowInstance<FlowNode, RouteEdge> | null>(null);
  const [full, setFull] = useState(false);

  useEffect(() => {
    const onChange = () => {
      setFull(document.fullscreenElement === figure.current);
      // the canvas changes size; fit again once the browser has laid it out
      window.setTimeout(() => flow.current?.fitView(FIT), 80);
    };
    document.addEventListener('fullscreenchange', onChange);
    return () => document.removeEventListener('fullscreenchange', onChange);
  }, []);

  const toggle = useCallback(() => {
    if (document.fullscreenElement) void document.exitFullscreen();
    else void figure.current?.requestFullscreen();
  }, []);

  return (
    <figure ref={figure} className="ox-figure not-prose" aria-label="How TalNex orchestrates a recruiter check">
      <div className="ox-figure__head">
        <Legend />
        <div className="ox-tools">
          <button type="button" className="ox-full" aria-label="Zoom in" onClick={() => flow.current?.zoomIn()}>+</button>
          <button type="button" className="ox-full" aria-label="Zoom out" onClick={() => flow.current?.zoomOut()}>−</button>
          <button type="button" className="ox-full" onClick={() => flow.current?.fitView(FIT)}>Fit</button>
          <button type="button" className="ox-full" onClick={toggle}>{full ? 'Exit full screen' : 'Full screen'}</button>
        </div>
      </div>
      <div className="ox-canvas">
        <ReactFlow<FlowNode, RouteEdge>
          // uncontrolled, so React Flow keeps the measured sizes the minimap needs
          defaultNodes={nodes}
          defaultEdges={edges}
          nodeTypes={nodeTypes}
          edgeTypes={edgeTypes}
          colorMode="dark"
          onInit={(instance) => { flow.current = instance; }}
          fitView
          fitViewOptions={FIT}
          minZoom={0.2}
          maxZoom={2.5}
          nodesDraggable={false}
          nodesConnectable={false}
          nodesFocusable={false}
          edgesFocusable={false}
          elementsSelectable={false}
          zoomOnScroll={false}
          zoomOnPinch
          panOnDrag
          preventScrolling={false}
        >
          <MiniMap pannable zoomable position="bottom-left" ariaLabel="Overview"
                   style={full ? { width: 200, height: 140 } : { width: 120, height: 70 }}
                   nodeClassName={(n) => (n.type === 'lane' ? 'ox-mini-lane' : 'ox-mini-node')} />
        </ReactFlow>
      </div>
      <figcaption className="ox-figure__caption">
        Every arrow is a row in the Postgres <code>jobs</code> table: Go and Python never call each other. A worker
        saves its result and adds the next stage in the same database step, and a stage with several arrows in starts
        when the last one finishes. Drag to pan; pinch or use + and − to zoom; Full screen for a projector.
      </figcaption>
    </figure>
  );
}
