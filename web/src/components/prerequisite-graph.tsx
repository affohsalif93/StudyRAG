"use client";

// The prerequisite graph as a clickable visualization, embedded in the
// quiz's recommendation view rather than a standalone catalog browser --
// the graph is still small (24 modules / 13 edges), scoped to the
// student's own recommendation.

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
  ReactFlowProvider,
  useReactFlow,
} from "@xyflow/react";
import dagre from "dagre";
import { useEffect, useMemo, useState } from "react";

import { getPrerequisiteGraph, type GraphEdge, type PrerequisiteGraph } from "@/lib/api";
import { cn } from "cn";

type Layer = "core" | "complementary" | "nice_to_have";
const LAYER_RING: Record<Layer, string> = {
  core: "ring-2 ring-foreground",
  complementary: "ring-2 ring-muted-foreground",
  nice_to_have: "ring-1 ring-border",
};

// Two edge kinds, two color families -- see api.ts's GraphEdge comment.
// "handbook" edges are stated in a module's own regulation text, so they're
// kept deliberately muted/light; "goal" edges are our own track curation
// connecting a module to a career goal the handbook never mentions, so
// they get one distinct, fully-saturated accent color instead.
type NecessityKey = NonNullable<GraphEdge["necessity"]>;
const NECESSITY_STYLE: Record<NecessityKey, { stroke: string; strokeWidth: number; dash?: string; label: string }> = {
  hard: { stroke: "var(--destructive)", strokeWidth: 2, label: "hard requirement" },
  recommended: { stroke: "#d4a72c", strokeWidth: 1.5, dash: "6 4", label: "recommended" },
  good_to_know: { stroke: "var(--muted-foreground)", strokeWidth: 1, dash: "2 3", label: "good to know" },
};
const HANDBOOK_OPACITY = 0.55;

const GOAL_COLOR = "#5ab0e0";
type LayerKey = NonNullable<GraphEdge["layer"]>;
const GOAL_LAYER_STYLE: Record<LayerKey, { strokeWidth: number; dash?: string; label: string }> = {
  core: { strokeWidth: 2.5, label: "core, toward your goal" },
  complementary: { strokeWidth: 1.75, dash: "6 3", label: "complementary, toward your goal" },
  nice_to_have: { strokeWidth: 1, dash: "2 3", label: "nice to have, toward your goal" },
};

function edgeStyle(e: GraphEdge): { stroke: string; strokeWidth: number; dash?: string; opacity: number } {
  if (e.kind === "goal") {
    const s = GOAL_LAYER_STYLE[e.layer ?? "nice_to_have"];
    return { stroke: GOAL_COLOR, strokeWidth: s.strokeWidth, dash: s.dash, opacity: 1 };
  }
  const s = NECESSITY_STYLE[e.necessity ?? "good_to_know"];
  return { stroke: s.stroke, strokeWidth: s.strokeWidth, dash: s.dash, opacity: HANDBOOK_OPACITY };
}

const BASE_WIDTH = 160;
const HEIGHT = 56;

function nodeWidth(degree: number): number {
  return BASE_WIDTH + 16 * Math.min(degree, 6);
}

function layoutGraph(graph: PrerequisiteGraph): { nodes: Node[]; edges: Edge[] } {
  const degree = new Map<string, number>();
  for (const n of graph.nodes) degree.set(n.module_id, 0);
  for (const e of graph.edges) {
    degree.set(e.source, (degree.get(e.source) ?? 0) + 1);
    degree.set(e.target, (degree.get(e.target) ?? 0) + 1);
  }

  const g = new dagre.graphlib.Graph();
  g.setGraph({ rankdir: "LR", nodesep: 24, ranksep: 90 });
  g.setDefaultEdgeLabel(() => ({}));

  for (const n of graph.nodes) {
    const width = n.kind === "goal" ? BASE_WIDTH + 40 : nodeWidth(degree.get(n.module_id) ?? 0);
    g.setNode(n.module_id, { width, height: HEIGHT });
  }
  for (const e of graph.edges) g.setEdge(e.source, e.target);
  dagre.layout(g);

  const nodes: Node[] = graph.nodes.map((n) => {
    const pos = g.node(n.module_id);
    const width = n.kind === "goal" ? BASE_WIDTH + 40 : nodeWidth(degree.get(n.module_id) ?? 0);
    return {
      id: n.module_id,
      type: n.kind,
      position: { x: pos.x - width / 2, y: pos.y - HEIGHT / 2 },
      data: { title: n.title, width, degree: degree.get(n.module_id) ?? 0 },
    };
  });

  const edges: Edge[] = graph.edges.map((e) => {
    const style = edgeStyle(e);
    return {
      id: `${e.kind}:${e.source}->${e.target}`,
      source: e.source,
      target: e.target,
      style: { stroke: style.stroke, strokeWidth: style.strokeWidth, strokeDasharray: style.dash, opacity: style.opacity },
      data: { kind: e.kind, necessity: e.necessity, layer: e.layer, reason: e.reason },
    };
  });

  return { nodes, edges };
}

function ModuleNode({ data, selected }: NodeProps) {
  const { title, highlight, width, degree, dim, matched } = data as {
    title: string;
    highlight?: Layer;
    width: number;
    degree: number;
    dim?: boolean;
    matched?: boolean;
  };
  return (
    <div
      className={cn(
        "rounded-xl border border-border bg-card px-3 py-2 text-xs shadow-sm transition-opacity",
        highlight && LAYER_RING[highlight],
        selected && "border-foreground",
        matched && "border-foreground ring-2 ring-foreground",
        dim && "opacity-25"
      )}
      style={{ width }}
      title={`${degree} prerequisite link${degree === 1 ? "" : "s"}`}
    >
      <Handle type="target" position={Position.Left} className="!bg-muted-foreground" />
      <span className="line-clamp-2 font-medium">{title}</span>
      <Handle type="source" position={Position.Right} className="!bg-muted-foreground" />
    </div>
  );
}

function GoalNode({ data, selected }: NodeProps) {
  const { title, width, dim } = data as { title: string; width: number; dim?: boolean };
  return (
    <div
      className={cn(
        "rounded-full border-2 px-4 py-3 text-center text-xs font-semibold shadow-sm transition-opacity",
        selected ? "border-foreground" : "border-[var(--goal-color)]",
        dim && "opacity-25"
      )}
      style={{ width, backgroundColor: "color-mix(in oklch, var(--goal-color) 18%, var(--card))", ["--goal-color" as string]: GOAL_COLOR }}
    >
      <Handle type="target" position={Position.Left} className="!bg-[var(--goal-color)]" />
      {title}
    </div>
  );
}

const nodeTypes = { module: ModuleNode, goal: GoalNode };

function GraphInner({
  highlightModuleIds,
  showSearch,
  trackId,
}: {
  highlightModuleIds?: Record<string, Layer>;
  showSearch?: boolean;
  trackId?: string;
}) {
  const [graph, setGraph] = useState<PrerequisiteGraph | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [selected, setSelected] = useState<string | null>(null);
  const [query, setQuery] = useState("");
  const { fitView } = useReactFlow();

  useEffect(() => {
    setGraph(null);
    getPrerequisiteGraph(trackId)
      .then(setGraph)
      .catch((e) => setError(e instanceof Error ? e.message : "Failed to load the prerequisite graph."));
  }, [trackId]);

  const trimmedQuery = query.trim().toLowerCase();

  const { nodes, edges } = useMemo(() => {
    if (!graph) return { nodes: [] as Node[], edges: [] as Edge[] };
    const { nodes: rawNodes, edges } = layoutGraph(graph);

    let matchedIds: Set<string> | null = null;
    let visibleIds: Set<string> | null = null;
    if (trimmedQuery.length >= 2) {
      matchedIds = new Set(graph.nodes.filter((n) => n.title.toLowerCase().includes(trimmedQuery)).map((n) => n.module_id));
      visibleIds = new Set(matchedIds);
      for (const e of graph.edges) {
        if (matchedIds.has(e.source)) visibleIds.add(e.target);
        if (matchedIds.has(e.target)) visibleIds.add(e.source);
      }
    }

    const nodes = rawNodes.map((n) => ({
      ...n,
      selected: n.id === selected,
      data: {
        ...n.data,
        highlight: highlightModuleIds?.[n.id],
        matched: matchedIds?.has(n.id) ?? false,
        dim: visibleIds ? !visibleIds.has(n.id) : false,
      },
    }));
    return { nodes, edges };
  }, [graph, selected, highlightModuleIds, trimmedQuery]);

  useEffect(() => {
    if (graph) fitView({ padding: 0.2 });
  }, [graph, fitView]);

  if (error) return <p className="text-sm text-destructive">{error}</p>;
  if (!graph) return <p className="text-sm text-muted-foreground">Loading graph…</p>;

  const selectedTitle = graph.nodes.find((n) => n.module_id === selected)?.title;
  const touching = selected
    ? graph.edges.filter((e) => e.source === selected || e.target === selected)
    : [];

  return (
    <div className="flex flex-col gap-4 lg:flex-row">
      <div className="h-[560px] flex-1 overflow-hidden rounded-xl border border-border bg-muted/20">
        <ReactFlow
          nodes={nodes}
          edges={edges}
          nodeTypes={nodeTypes}
          onNodeClick={(_, node) => setSelected((cur) => (cur === node.id ? null : node.id))}
          onPaneClick={() => setSelected(null)}
          proOptions={{ hideAttribution: true }}
          fitView
        >
          <Background />
          <Controls showInteractive={false} />
        </ReactFlow>
      </div>

      <aside className="flex w-full flex-col gap-3 lg:w-72 lg:shrink-0">
        {showSearch && (
          <input
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Search modules…"
            className="rounded-xl border border-border bg-card px-3 py-2 text-sm placeholder:text-muted-foreground focus:outline-none focus:ring-1 focus:ring-foreground"
          />
        )}
        <div className="flex flex-col gap-1.5 rounded-xl border border-border p-3 text-xs text-muted-foreground">
          <p className="text-foreground">Node size = how many links (of either kind) a module has.</p>
          <p className="mt-1 text-foreground">From the handbook:</p>
          {(Object.entries(NECESSITY_STYLE) as [NecessityKey, (typeof NECESSITY_STYLE)[NecessityKey]][]).map(([key, style]) => (
            <span key={key} className="flex items-center gap-1.5">
              <span className="inline-block h-0.5 w-5" style={{ backgroundColor: style.stroke, opacity: HANDBOOK_OPACITY }} />
              {style.label}
            </span>
          ))}
          {trackId && (
            <>
              <p className="mt-1 text-foreground">Toward your goal (not in the handbook):</p>
              <span className="flex items-center gap-1.5">
                <span className="inline-block h-0.5 w-5" style={{ backgroundColor: GOAL_COLOR }} />
                module → career goal
              </span>
            </>
          )}
        </div>

        {selected && (
          <div className="rounded-xl border border-border p-3 text-sm">
            <p className="font-medium">{selectedTitle}</p>
            {touching.length === 0 && <p className="mt-1 text-xs text-muted-foreground">No links.</p>}
            {touching.map((e) => {
              const other = graph.nodes.find((n) => n.module_id === (e.source === selected ? e.target : e.source));
              if (e.kind === "goal") {
                const moduleTitle = e.source === selected ? selectedTitle : other?.title;
                const goalTitle = e.source === selected ? other?.title : selectedTitle;
                return (
                  <p key={`${e.source}-${e.target}`} className="mt-1 text-xs text-muted-foreground">
                    <span className="text-foreground">{moduleTitle}</span> moves you toward{" "}
                    <span className="text-foreground">{goalTitle}</span> ({e.layer}) — {e.reason}
                  </p>
                );
              }
              const direction = e.source === selected ? "is a prerequisite for" : "depends on";
              return (
                <p key={`${e.source}-${e.target}`} className="mt-1 text-xs text-muted-foreground">
                  <span className="text-foreground">{selectedTitle}</span> {direction}{" "}
                  <span className="text-foreground">{other?.title}</span> ({e.necessity}) — {e.reason}
                </p>
              );
            })}
            <button onClick={() => setSelected(null)} className="mt-2 text-xs underline text-muted-foreground hover:text-foreground">
              Clear selection
            </button>
          </div>
        )}
      </aside>
    </div>
  );
}

export function PrerequisiteGraphView({
  highlightModuleIds,
  showSearch = true,
  trackId,
}: {
  highlightModuleIds?: Record<string, Layer>;
  showSearch?: boolean;
  trackId?: string;
}) {
  return (
    <ReactFlowProvider>
      <GraphInner highlightModuleIds={highlightModuleIds} showSearch={showSearch} trackId={trackId} />
    </ReactFlowProvider>
  );
}
