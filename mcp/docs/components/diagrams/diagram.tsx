'use client';
// A read-only React Flow canvas for the docs: fitted to view, nothing to drag, connect or select, and the page still
// scrolls over it. Nodes are TalNex boxes with a handle on every side, so edges can leave and enter where they read best.
import {
  type Edge,
  Handle,
  MarkerType,
  type Node,
  type NodeProps,
  Position,
  ReactFlow,
} from '@xyflow/react';
import '@xyflow/react/dist/style.css';

export type Tone = 'plain' | 'accent' | 'danger' | 'question' | 'safe';
export type BoxData = { label: string; sub?: string; tone?: Tone };
export type BoxNode = Node<BoxData, 'box'>;

const SIDES = [
  ['t', Position.Top],
  ['r', Position.Right],
  ['b', Position.Bottom],
  ['l', Position.Left],
] as const;

function Box({ data }: NodeProps<BoxNode>) {
  return (
    <div className={`tx-node tx-node--${data.tone ?? 'plain'}`}>
      {SIDES.map(([id, position]) => (
        <span key={id}>
          <Handle type="source" id={id} position={position} isConnectable={false} />
          <Handle type="target" id={`${id}-in`} position={position} isConnectable={false} />
        </span>
      ))}
      <div className="tx-node__label">{data.label}</div>
      {data.sub ? <div className="tx-node__sub">{data.sub}</div> : null}
    </div>
  );
}

const nodeTypes = { box: Box };

/** A box at (x, y). */
export const box = (id: string, x: number, y: number, label: string, sub?: string, tone?: Tone): BoxNode => ({
  id, type: 'box', position: { x, y }, data: { label, sub, tone },
});

/** An edge from one side of a node to a side of another: "r" leaves from the right, "l" enters on the left. */
export const link = (from: string, fromSide: string, to: string, toSide: string, label?: string,
                     look?: 'yes' | 'soft', animated = false): Edge => ({
  id: `${from}:${fromSide}-${to}:${toSide}`,
  source: from, sourceHandle: fromSide, target: to, targetHandle: `${toSide}-in`,
  label, animated, className: look ? `tx-edge--${look}` : undefined,
  type: 'smoothstep', markerEnd: { type: MarkerType.ArrowClosed, width: 16, height: 16 },
  labelBgPadding: [6, 3], labelBgBorderRadius: 4,
});

export function Diagram({ nodes, edges, title, caption, size = 'medium' }: {
  nodes: BoxNode[];
  edges: Edge[];
  title: string;
  caption: string;
  size?: 'small' | 'medium' | 'large';
}) {
  return (
    <figure className="tx-diagram not-prose" data-size={size} aria-label={title}>
      <div className="tx-diagram__canvas">
        <ReactFlow
          nodes={nodes}
          edges={edges}
          nodeTypes={nodeTypes}
          colorMode="dark"
          fitView
          fitViewOptions={{ padding: 0.08 }}
          nodesDraggable={false}
          nodesConnectable={false}
          nodesFocusable={false}
          edgesFocusable={false}
          elementsSelectable={false}
          panOnDrag={false}
          panOnScroll={false}
          zoomOnScroll={false}
          zoomOnPinch={false}
          zoomOnDoubleClick={false}
          preventScrolling={false}
        />
      </div>
      <figcaption className="tx-diagram__caption">{caption}</figcaption>
    </figure>
  );
}
