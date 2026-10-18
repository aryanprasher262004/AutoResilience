"use client";

import "@xyflow/react/dist/style.css";

import {
  Background,
  Controls,
  type Edge,
  Handle,
  type Node,
  type NodeProps,
  Position,
  ReactFlow,
  useReactFlow,
} from "@xyflow/react";
import { memo, useEffect, useMemo } from "react";

import type { TopologyEdge, TopologyNode } from "@/lib/api/types";
import { cn } from "@/lib/cn";
import { EDGE_META, KIND_META, NODE_HEALTH_META, NODE_HEIGHT, NODE_WIDTH, layout } from "@/lib/topology";

type ResourceData = { node: TopologyNode; dimmed: boolean; selected: boolean };
type GroupData = { label: string };

const TONE_DOT: Record<string, string> = {
  success: "bg-success",
  warning: "bg-warning",
  danger: "bg-danger",
  info: "bg-info",
  neutral: "bg-faint",
};

const ResourceNode = memo(function ResourceNode({ data }: NodeProps<Node<ResourceData>>) {
  const { node, dimmed, selected } = data;
  const health = NODE_HEALTH_META[node.health];
  return (
    <div
      className={cn(
        "flex h-full w-full flex-col justify-center rounded-md border bg-surface-2 px-2.5 text-left shadow-sm transition-opacity",
        selected ? "border-accent ring-2 ring-accent/40" : "border-line-strong",
        dimmed && "opacity-30",
      )}
      title={`${node.kind} ${node.namespace ? `${node.namespace}/` : ""}${node.name} · ${health.label}: ${node.health_reason}`}
    >
      <Handle type="target" position={Position.Left} isConnectable={false} className="!size-1.5 !border-0 !bg-line-strong" />
      <div className="flex items-center gap-1.5 text-2xs text-faint">
        <span aria-hidden className={cn("size-1.5 shrink-0 rounded-full", TONE_DOT[health.tone])} />
        <span>{KIND_META[node.kind].label}</span>
        {node.experiment_target?.supported ? <span className="ml-auto text-accent">target</span> : null}
      </div>
      <div className="truncate font-mono text-xs text-fg">{node.name}</div>
      <Handle type="source" position={Position.Right} isConnectable={false} className="!size-1.5 !border-0 !bg-line-strong" />
    </div>
  );
});

function GroupNode({ data }: NodeProps<Node<GroupData>>) {
  return (
    <div className="h-full w-full rounded-lg border border-dashed border-line-strong bg-surface/40">
      <p className="px-3 pt-2 font-mono text-2xs tracking-wide text-faint uppercase">{data.label}</p>
    </div>
  );
}

const nodeTypes = { resource: ResourceNode, namespace: GroupNode };

const EDGE_STYLE: Record<TopologyEdge["type"], { stroke: string; dash?: string }> = {
  owns: { stroke: "var(--color-line-strong)" },
  selects: { stroke: "var(--color-accent)", dash: "6 4" },
  endpoint: { stroke: "var(--color-success)", dash: "2 4" },
  slice_for: { stroke: "var(--color-line-strong)", dash: "2 4" },
  scheduled_on: { stroke: "var(--color-faint)", dash: "8 6" },
};

/** Re-fits the viewport when the visible set of nodes changes (filters, new snapshot). */
function FitOnChange({ signature }: { signature: string }) {
  const { fitView } = useReactFlow();
  useEffect(() => {
    const frame = requestAnimationFrame(() => void fitView({ padding: 0.12, duration: 200 }));
    return () => cancelAnimationFrame(frame);
  }, [signature, fitView]);
  return null;
}

/**
 * The interactive 2D graph: pan (drag the canvas), zoom (wheel, pinch, controls),
 * select (click or keyboard focus + Enter). Layout is computed, not draggable, so the
 * same snapshot always looks the same.
 */
export function TopologyGraph({
  nodes,
  edges,
  selected,
  matches,
  onSelect,
}: {
  nodes: TopologyNode[];
  edges: TopologyEdge[];
  selected: string | null;
  /** Node ids matching the search; others are dimmed. Null: no search. */
  matches: Set<string> | null;
  onSelect: (id: string | null) => void;
}) {
  const groups = useMemo(() => layout(nodes, edges), [nodes, edges]);
  const byId = useMemo(() => new Map(nodes.map((n) => [n.id, n])), [nodes]);

  const flowNodes = useMemo<Node[]>(() => {
    const result: Node[] = [];
    for (const g of groups) {
      result.push({
        id: g.id,
        type: "namespace",
        position: { x: g.x, y: g.y },
        data: { label: g.label },
        style: { width: g.width, height: g.height },
        selectable: false,
        focusable: false,
        draggable: false,
      });
      for (const m of g.members) {
        const node = byId.get(m.id)!;
        result.push({
          id: m.id,
          type: "resource",
          parentId: g.id,
          position: { x: m.x, y: m.y },
          data: { node, dimmed: matches !== null && !matches.has(m.id), selected: m.id === selected },
          style: { width: NODE_WIDTH, height: NODE_HEIGHT },
          draggable: false,
          ariaLabel: `${node.kind} ${node.name}${node.namespace ? ` in ${node.namespace}` : ""}, ${NODE_HEALTH_META[node.health].label}`,
        });
      }
    }
    return result;
  }, [groups, byId, matches, selected]);

  const flowEdges = useMemo<Edge[]>(
    () =>
      edges.map((e) => {
        const style = EDGE_STYLE[e.type];
        const active = selected !== null && (e.source === selected || e.target === selected);
        const notReady = e.type === "endpoint" && e.attributes.ready === false;
        return {
          id: e.id,
          source: e.source,
          target: e.target,
          label: active ? EDGE_META[e.type].label : undefined,
          animated: active,
          focusable: false,
          style: {
            stroke: notReady ? "var(--color-warning)" : active ? "var(--color-accent)" : style.stroke,
            strokeDasharray: style.dash,
            strokeWidth: active ? 2 : 1.25,
            opacity: selected !== null && !active ? 0.35 : 1,
          },
          labelStyle: { fill: "var(--color-fg)", fontSize: 10 },
          labelBgStyle: { fill: "var(--color-surface)" },
        };
      }),
    [edges, selected],
  );

  const signature = useMemo(() => nodes.map((n) => n.id).join("|"), [nodes]);

  return (
    <ReactFlow
      nodes={flowNodes}
      edges={flowEdges}
      nodeTypes={nodeTypes}
      colorMode="dark"
      fitView
      minZoom={0.15}
      maxZoom={2}
      nodesDraggable={false}
      nodesConnectable={false}
      edgesFocusable={false}
      onNodeClick={(_, node) => node.type === "resource" && onSelect(node.id)}
      onNodesChange={(changes) => {
        // Keyboard selection (focus + Enter) arrives as a select change.
        for (const change of changes) {
          if (change.type === "select" && change.selected && byId.has(change.id)) onSelect(change.id);
        }
      }}
      onPaneClick={() => onSelect(null)}
      proOptions={{ hideAttribution: false }}
      className="bg-canvas"
    >
      <Background gap={24} size={1} color="var(--color-line)" />
      <Controls showInteractive={false} position="bottom-left" />
      <FitOnChange signature={signature} />
    </ReactFlow>
  );
}
