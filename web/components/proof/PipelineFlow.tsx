"use client";

import {
  Handle,
  MarkerType,
  type Edge,
  type Node,
  type NodeProps,
  Position,
  ReactFlow,
  ReactFlowProvider,
  useReactFlow,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import { useEffect, useRef, useState } from "react";

import { layoutPipeline, type FlowStage } from "@/lib/pipeline-flow";
import type { JobRow } from "@/lib/types";

type StageData = { stage: FlowStage; selected: boolean };
type StageNode = Node<StageData, "stage">;

const STATUS_TEXT: Record<FlowStage["status"], string> = {
  done: "Done",
  running: "Running",
  retrying: "Retrying",
  failed: "Failed",
  queued: "Queued",
  skipped: "Skipped",
  waiting: "Not started",
};

function StageBox({ data }: NodeProps<StageNode>) {
  const { stage, selected } = data;
  return (
    <div className={`job-node job-node--${stage.status}${selected ? " job-node--selected" : ""}`}>
      <Handle type="target" position={Position.Left} isConnectable={false} />
      <Handle type="source" position={Position.Right} isConnectable={false} />
      <div className="job-node__name">{stage.name.replace(/_/g, " ")}</div>
      <div className="job-node__status">{STATUS_TEXT[stage.status]}</div>
    </div>
  );
}

const nodeTypes = { stage: StageBox };

/**
 * One pipeline run as a graph: a box per stage, left to right in the order stages wait for each other, coloured by
 * status. Click a box to see its result and to run it again, run from it, or retry it. Nothing can be edited.
 */
export function PipelineFlow({
  rows,
  allRows,
  pending,
  canRun,
  run,
  retry,
}: {
  rows: JobRow[];
  allRows: JobRow[];
  pending: boolean;
  canRun: boolean;
  run: (stages: string[]) => void;
  retry: (id: string) => void;
}) {
  const [open, setOpen] = useState<string | null>(null);
  const { stages, edges: links } = layoutPipeline(rows, allRows);
  const chosen = stages.find((s) => s.name === open) ?? null;

  const nodes: StageNode[] = stages.map((s) => ({
    id: s.name,
    type: "stage",
    position: { x: s.depth * 200, y: s.row * 88 },
    data: { stage: s, selected: s.name === open },
  }));
  const edges: Edge[] = links.map(([from, to]) => ({
    id: `${from}-${to}`,
    source: from,
    target: to,
    type: "smoothstep",
    animated: stages.find((s) => s.name === to)?.status === "running",
    markerEnd: { type: MarkerType.ArrowClosed, width: 14, height: 14 },
  }));

  return (
    <div className="job-flow">
      <FitCanvas nodeCount={nodes.length}>
        <ReactFlow
          nodes={nodes}
          edges={edges}
          nodeTypes={nodeTypes}
          fitView
          fitViewOptions={{ padding: 0.12 }}
          nodesDraggable={false}
          nodesConnectable={false}
          elementsSelectable={false}
          onNodeClick={(_, node) => setOpen(node.id === open ? null : node.id)}
          proOptions={{ hideAttribution: true }}
          minZoom={0.3}
        />
      </FitCanvas>
      {chosen && (
        <aside className="job-flow__drawer" aria-label={`Stage ${chosen.name}`}>
          <div className="row">
            <strong>{chosen.name.replace(/_/g, " ")}</strong>
            <span className="meta">{STATUS_TEXT[chosen.status]}</span>
            <button type="button" className="button button--ghost button--sm" onClick={() => setOpen(null)}>
              Close
            </button>
          </div>
          {chosen.job ? (
            <dl className="definition">
              <dt>Tries</dt>
              <dd>
                {chosen.job.tries}/{chosen.job.max_tries}
              </dd>
              <dt>Time</dt>
              <dd>{chosen.job.status === "done" || chosen.job.status === "failed" ? `${Math.round(chosen.job.seconds)}s` : "running"}</dd>
              <dt>{chosen.job.error ? "Error" : "Result"}</dt>
              <dd>{chosen.job.error || chosen.summary || "Nothing to show"}</dd>
            </dl>
          ) : (
            <p className="note">This stage has not started in this run.</p>
          )}
          <div className="row">
            {chosen.job?.status === "failed" && (
              <button type="button" className="button button--sm" disabled={pending} onClick={() => retry(chosen.job!.id)}>
                Retry
              </button>
            )}
            {canRun && (
              // ponytail: one button; run-stages always chains the stages after it, so "run again" and "run from
              // here" are the same request. Split them when a stage can be re-run on its own.
              <button type="button" className="button button--sm" disabled={pending} onClick={() => run([chosen.name])}>
                Run again from here
              </button>
            )}
          </div>
          <p className="note">
            Running a stage again reuses the stages before it and runs every stage after it, so the scores update.
          </p>
        </aside>
      )}
    </div>
  );
}

/**
 * The canvas, fitted to its box whenever the box changes size. Every tab is rendered up front and hidden, so the first
 * fit happens at zero width and leaves the graph stuck at the left; refitting when the tab opens (the box grows) fixes it.
 */
function FitCanvas({ nodeCount, children }: { nodeCount: number; children: React.ReactNode }) {
  return (
    <ReactFlowProvider>
      <Fitter nodeCount={nodeCount}>{children}</Fitter>
    </ReactFlowProvider>
  );
}

function Fitter({ nodeCount, children }: { nodeCount: number; children: React.ReactNode }) {
  const box = useRef<HTMLDivElement>(null);
  const { fitView } = useReactFlow();
  useEffect(() => {
    const el = box.current;
    if (!el) return;
    const fit = () => {
      if (el.clientWidth > 0 && el.clientHeight > 0) requestAnimationFrame(() => fitView({ padding: 0.12 }));
    };
    const watch = new ResizeObserver(fit);
    watch.observe(el);
    fit();
    return () => watch.disconnect();
  }, [fitView, nodeCount]);
  return (
    <div className="job-flow__canvas" ref={box}>
      {children}
    </div>
  );
}
