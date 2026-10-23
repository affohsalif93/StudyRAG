"use client";

// The chairs graph -- a deliberately separate view from the relevance
// map and dependency DAG: chairs answer "who teaches this, who do I
// talk to", not "how relevant is this to my goal", so there's no single
// goal to anchor a radial layout to. Uses a clustered force layout with
// area hulls instead.
//
// Clusters by informatik_number (RWTH's own thematic grouping) rather
// than subject area. Chairs are the primary subject (sized by how many
// matched modules they have); modules are small satellites pulled
// toward their chair by forceLink.

import { forceCollide, forceLink, forceManyBody, forceSimulation, forceX, forceY, type SimulationNodeDatum } from "d3-force";
import { select } from "d3-selection";
import { zoom, zoomIdentity, type ZoomBehavior } from "d3-zoom";
import { useEffect, useMemo, useRef, useState } from "react";

import { getChairsGraph, type ChairModuleEdge, type ChairNode, type ChairParentEdge, type ChairsGraph } from "@/lib/api";
import { cn } from "cn";

const WIDTH = 980;
const HEIGHT = 680;
const MIN_CHAIR_R = 9;
const MAX_CHAIR_R = 28;
const MODULE_R = 3;
const DRIFT_AMPLITUDE = 4;

const PARENT_EDGE_COLOR = "#b08ee0";
const MODULE_EDGE_COLOR = "var(--muted-foreground)";

function isDefunct(groupType: string): boolean {
  return groupType.startsWith("ehemals");
}

// A stable, deterministic color per informatik_number cluster.
function clusterColor(key: string): string {
  let hash = 0;
  for (let i = 0; i < key.length; i++) hash = (hash * 31 + key.charCodeAt(i)) >>> 0;
  return `hsl(${hash % 360} 55% 58%)`;
}

function idOf(ref: string | GraphNode): string {
  return typeof ref === "string" ? ref : ref.id;
}

interface GraphNode extends SimulationNodeDatum {
  id: string;
  kind: "chair" | "module";
  label: string;
  cluster: string;
  radius: number;
  defunct: boolean;
  isParent: boolean;
  baseX: number;
  baseY: number;
  phaseX: number;
  phaseY: number;
  speed: number;
  renderX?: number;
  renderY?: number;
  chair?: ChairNode;
}

type EdgeKind = "module" | "parent";
interface GraphLink {
  id: string;
  source: string | GraphNode;
  target: string | GraphNode;
  kind: EdgeKind;
  matchedPeople?: string[];
}

export function ChairsGraphView() {
  const [data, setData] = useState<ChairsGraph | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [selected, setSelected] = useState<string | null>(null);
  const [query, setQuery] = useState("");
  const groupRefs = useRef<Map<string, SVGGElement>>(new Map());
  const lineRefs = useRef<Map<string, SVGLineElement>>(new Map());
  const svgRef = useRef<SVGSVGElement>(null);
  const zoomLayerRef = useRef<SVGGElement>(null);
  const zoomBehaviorRef = useRef<ZoomBehavior<SVGSVGElement, unknown> | null>(null);

  useEffect(() => {
    getChairsGraph()
      .then(setData)
      .catch((e) => setError(e instanceof Error ? e.message : "Failed to load the chairs graph."));
  }, []);

  useEffect(() => {
    if (!svgRef.current || !zoomLayerRef.current) return;
    const layer = zoomLayerRef.current;
    const zb = zoom<SVGSVGElement, unknown>()
      .scaleExtent([0.5, 6])
      .filter((event: Event) => {
        const e = event as MouseEvent;
        const target = event.target as Element;
        return (!e.ctrlKey || e.type === "wheel") && !e.button && !target.closest(".node");
      })
      .on("zoom", (event) => layer.setAttribute("transform", event.transform.toString()));
    const selection = select(svgRef.current);
    selection.call(zb);
    zoomBehaviorRef.current = zb;
    return () => {
      selection.on(".zoom", null);
    };
    // svgRef/zoomLayerRef are only non-null once `data` has loaded and the
    // real <svg> has rendered (the loading-state branch above renders no
    // <svg> at all) -- re-run once that happens, not just on first mount.
  }, [data]);

  function zoomBy(factor: number) {
    if (!svgRef.current || !zoomBehaviorRef.current) return;
    select(svgRef.current).transition().duration(180).call(zoomBehaviorRef.current.scaleBy, factor);
  }
  function resetZoom() {
    if (!svgRef.current || !zoomBehaviorRef.current) return;
    select(svgRef.current).transition().duration(180).call(zoomBehaviorRef.current.transform, zoomIdentity);
  }

  const moduleCountByChair = useMemo(() => {
    if (!data) return new Map<string, number>();
    const counts = new Map<string, number>();
    for (const e of data.module_edges) counts.set(e.target, (counts.get(e.target) ?? 0) + 1);
    return counts;
  }, [data]);

  const clusters = useMemo(() => {
    if (!data) return [];
    return Array.from(new Set(data.chairs.map((c) => c.informatik_number))).sort((a, b) => a.localeCompare(b, undefined, { numeric: true }));
  }, [data]);

  const nodes = useMemo<GraphNode[]>(() => {
    if (!data) return [];
    const parentIds = new Set(data.parent_edges.map((e) => e.target));
    const centers = new Map<string, [number, number]>();
    clusters.forEach((cl, i) => {
      const angle = (i / clusters.length) * 2 * Math.PI - Math.PI / 2;
      centers.set(cl, [WIDTH / 2 + Math.cos(angle) * 340, HEIGHT / 2 + Math.sin(angle) * 250]);
    });

    const chairNodes: GraphNode[] = data.chairs.map((c) => {
      const [cx, cy] = centers.get(c.informatik_number) ?? [WIDTH / 2, HEIGHT / 2];
      const x = cx + (Math.random() - 0.5) * 40;
      const y = cy + (Math.random() - 0.5) * 40;
      const count = moduleCountByChair.get(c.id) ?? 0;
      return {
        id: c.id,
        kind: "chair",
        label: c.name,
        cluster: c.informatik_number,
        radius: MIN_CHAIR_R + Math.sqrt(count) * 6,
        defunct: isDefunct(c.group_type),
        isParent: parentIds.has(c.id),
        x,
        y,
        baseX: x,
        baseY: y,
        phaseX: Math.random() * Math.PI * 2,
        phaseY: Math.random() * Math.PI * 2,
        speed: 0.25 + Math.random() * 0.25,
        chair: c,
      };
    });

    const chairById = new Map(data.chairs.map((c) => [c.id, c]));
    const moduleNodes: GraphNode[] = data.modules.map((m) => {
      const edge = data.module_edges.find((e) => e.source === m.module_id);
      const chair = edge ? chairById.get(edge.target) : undefined;
      const cluster = chair?.informatik_number ?? clusters[0] ?? "1";
      const [cx, cy] = centers.get(cluster) ?? [WIDTH / 2, HEIGHT / 2];
      const x = cx + (Math.random() - 0.5) * 60;
      const y = cy + (Math.random() - 0.5) * 60;
      return {
        id: m.module_id,
        kind: "module",
        label: m.title,
        cluster,
        radius: MODULE_R,
        defunct: false,
        isParent: false,
        x,
        y,
        baseX: x,
        baseY: y,
        phaseX: Math.random() * Math.PI * 2,
        phaseY: Math.random() * Math.PI * 2,
        speed: 0.3 + Math.random() * 0.3,
      };
    });

    return [...chairNodes, ...moduleNodes];
  }, [data, clusters, moduleCountByChair]);

  const links = useMemo<GraphLink[]>(() => {
    if (!data) return [];
    const ids = new Set(nodes.map((n) => n.id));
    const moduleLinks: GraphLink[] = data.module_edges
      .filter((e) => ids.has(e.source) && ids.has(e.target))
      .map((e) => ({ id: `mod:${e.source}-${e.target}`, source: e.source, target: e.target, kind: "module" as const, matchedPeople: e.matched_people }));
    const parentLinks: GraphLink[] = data.parent_edges
      .filter((e) => ids.has(e.source) && ids.has(e.target))
      .map((e) => ({ id: `parent:${e.source}-${e.target}`, source: e.source, target: e.target, kind: "parent" as const }));
    return [...moduleLinks, ...parentLinks];
  }, [data, nodes]);

  useEffect(() => {
    if (nodes.length === 0) return;

    const sim = forceSimulation(nodes)
      .force("x", forceX<GraphNode>((d) => WIDTH / 2 + Math.cos(((clusters.indexOf(d.cluster) ?? 0) / clusters.length) * 2 * Math.PI - Math.PI / 2) * 340).strength(0.05))
      .force("y", forceY<GraphNode>((d) => HEIGHT / 2 + Math.sin(((clusters.indexOf(d.cluster) ?? 0) / clusters.length) * 2 * Math.PI - Math.PI / 2) * 250).strength(0.05))
      .force("charge", forceManyBody().strength(-20))
      .force(
        "link",
        forceLink<GraphNode, GraphLink>(links)
          .id((d) => d.id)
          .distance((l) => (l.kind === "parent" ? 55 : 30))
          .strength((l) => (l.kind === "parent" ? 0.6 : 0.5))
      )
      .force("collide", forceCollide<GraphNode>((d) => d.radius + 2).strength(0.8))
      .stop();
    for (let i = 0; i < 350; i++) sim.tick();

    for (const n of nodes) {
      n.baseX = n.x ?? WIDTH / 2;
      n.baseY = n.y ?? HEIGHT / 2;
      const el = groupRefs.current.get(n.id);
      if (el) el.setAttribute("transform", `translate(${n.baseX},${n.baseY})`);
    }

    let start: number | null = null;
    let raf = 0;
    const animate = (t: number) => {
      if (start === null) start = t;
      const elapsed = (t - start) / 1000;
      for (const n of nodes) {
        const cx = n.baseX + Math.sin(elapsed * n.speed + n.phaseX) * DRIFT_AMPLITUDE;
        const cy = n.baseY + Math.cos(elapsed * n.speed * 0.8 + n.phaseY) * DRIFT_AMPLITUDE;
        n.renderX = cx;
        n.renderY = cy;
        const el = groupRefs.current.get(n.id);
        if (el) el.setAttribute("transform", `translate(${cx},${cy})`);
      }
      for (const l of links) {
        const el = lineRefs.current.get(l.id);
        if (!el) continue;
        const s = l.source as GraphNode;
        const t2 = l.target as GraphNode;
        el.setAttribute("x1", String(s.renderX ?? s.x ?? 0));
        el.setAttribute("y1", String(s.renderY ?? s.y ?? 0));
        el.setAttribute("x2", String(t2.renderX ?? t2.x ?? 0));
        el.setAttribute("y2", String(t2.renderY ?? t2.y ?? 0));
      }
      raf = requestAnimationFrame(animate);
    };
    raf = requestAnimationFrame(animate);

    return () => {
      cancelAnimationFrame(raf);
      sim.stop();
    };
  }, [nodes, links, clusters]);

  const groupedChairs = useMemo(() => {
    if (!data) return [];
    const byCluster = new Map<string, ChairNode[]>();
    for (const c of data.chairs) {
      if (!byCluster.has(c.informatik_number)) byCluster.set(c.informatik_number, []);
      byCluster.get(c.informatik_number)!.push(c);
    }
    for (const arr of byCluster.values()) arr.sort((a, b) => (moduleCountByChair.get(b.id) ?? 0) - (moduleCountByChair.get(a.id) ?? 0));
    return Array.from(byCluster.entries()).sort((a, b) => a[0].localeCompare(b[0], undefined, { numeric: true }));
  }, [data, moduleCountByChair]);

  if (error) return <p className="text-sm text-destructive">{error}</p>;
  if (!data) return <p className="text-sm text-muted-foreground">Loading the chairs graph…</p>;

  const trimmedQuery = query.trim().toLowerCase();
  const matched = trimmedQuery.length >= 2 ? new Set(nodes.filter((n) => n.label.toLowerCase().includes(trimmedQuery)).map((n) => n.id)) : null;

  const selectedNode = nodes.find((n) => n.id === selected);
  // "parent" edges are already shown via the dedicated parentChair/
  // childChairs summary lines above -- listing them again here would
  // just repeat the same fact.
  const touchingSelected = selected ? links.filter((l) => l.kind === "module" && (idOf(l.source) === selected || idOf(l.target) === selected)) : [];
  const selectedChair = selectedNode?.kind === "chair" ? selectedNode.chair : undefined;
  const childChairs = selectedChair ? data.chairs.filter((c) => c.parent_chair_id === selectedChair.id) : [];
  const parentChair = selectedChair?.parent_chair_id ? data.chairs.find((c) => c.id === selectedChair.parent_chair_id) : undefined;

  return (
    <div className="flex flex-col gap-4 lg:flex-row">
      <div className="relative flex-1 overflow-hidden rounded-xl border border-border bg-muted/20">
        <svg ref={svgRef} viewBox={`0 0 ${WIDTH} ${HEIGHT}`} className="w-full touch-none" style={{ height: HEIGHT }}>
          <g ref={zoomLayerRef}>
            <g>
              {links.map((l) => {
                const touches = selected !== null && (idOf(l.source) === selected || idOf(l.target) === selected);
                const s = nodes.find((n) => n.id === idOf(l.source));
                const t2 = nodes.find((n) => n.id === idOf(l.target));
                return (
                  <line
                    key={l.id}
                    ref={(el) => {
                      if (el) lineRefs.current.set(l.id, el);
                      else lineRefs.current.delete(l.id);
                    }}
                    x1={s?.x ?? 0}
                    y1={s?.y ?? 0}
                    x2={t2?.x ?? 0}
                    y2={t2?.y ?? 0}
                    stroke={l.kind === "parent" ? PARENT_EDGE_COLOR : MODULE_EDGE_COLOR}
                    strokeWidth={l.kind === "parent" ? (touches ? 3 : 2) : touches ? 1.8 : 0.8}
                    strokeOpacity={l.kind === "parent" ? 0.9 : touches ? 0.85 : 0.3}
                  />
                );
              })}
            </g>
            {nodes.map((n) => {
              const isMatch = matched?.has(n.id) ?? false;
              const dim = matched ? !isMatch : false;
              const isSelected = n.id === selected;
              return (
                <g
                  key={n.id}
                  ref={(el) => {
                    if (el) groupRefs.current.set(n.id, el);
                    else groupRefs.current.delete(n.id);
                  }}
                  onClick={() => setSelected((cur) => (cur === n.id ? null : n.id))}
                  className={cn("node cursor-pointer transition-opacity", dim && "opacity-20")}
                >
                  <circle r={Math.max(n.radius, 7) + 6} fill="transparent" />
                  <circle
                    r={n.radius}
                    fill={clusterColor(n.cluster)}
                    fillOpacity={n.kind === "chair" ? (n.defunct ? 0.35 : 0.85) : 0.6}
                    stroke={isSelected || isMatch ? "var(--foreground)" : n.isParent ? PARENT_EDGE_COLOR : "none"}
                    strokeWidth={isSelected || isMatch ? 2 : n.isParent ? 1.5 : 0}
                    strokeDasharray={n.defunct ? "2,2" : undefined}
                  >
                    <title>{n.kind === "chair" ? `${n.label} (${n.chair?.group_type})` : n.label}</title>
                  </circle>
                  {n.kind === "chair" && (
                    <text
                      textAnchor="middle"
                      dy={-n.radius - 5}
                      className="pointer-events-none select-none fill-foreground text-[8px] font-medium"
                    >
                      {n.label.length > 26 ? `${n.label.slice(0, 24)}…` : n.label}
                    </text>
                  )}
                </g>
              );
            })}
          </g>
        </svg>
        <div className="absolute bottom-3 left-3 flex flex-col gap-1">
          <button onClick={() => zoomBy(1.3)} aria-label="Zoom in" className="flex h-7 w-7 items-center justify-center rounded-md border border-border bg-card/90 text-sm text-muted-foreground hover:bg-muted hover:text-foreground">+</button>
          <button onClick={() => zoomBy(1 / 1.3)} aria-label="Zoom out" className="flex h-7 w-7 items-center justify-center rounded-md border border-border bg-card/90 text-sm text-muted-foreground hover:bg-muted hover:text-foreground">−</button>
          <button onClick={resetZoom} aria-label="Reset zoom" className="flex h-7 w-7 items-center justify-center rounded-md border border-border bg-card/90 text-xs text-muted-foreground hover:bg-muted hover:text-foreground">⤾</button>
        </div>
      </div>

      <aside className="flex w-full flex-col gap-3 lg:w-80 lg:shrink-0">
        <input
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="Search chairs or modules…"
          className="rounded-xl border border-border bg-card px-3 py-2 text-sm placeholder:text-muted-foreground focus:outline-none focus:ring-1 focus:ring-foreground"
        />
        <div className="flex flex-col gap-1 rounded-xl border border-border p-3 text-xs text-muted-foreground">
          <p className="text-foreground">Clustered by RWTH's own research area (informatik_number). Bigger = more matched modules.</p>
          <span className="flex items-center gap-1.5">
            <span className="inline-block h-2 w-2 rounded-full border border-dashed" style={{ borderColor: "var(--muted-foreground)" }} />
            defunct chair (ehemals)
          </span>
          <span className="flex items-center gap-1.5">
            <span className="inline-block h-0.5 w-5" style={{ backgroundColor: PARENT_EDGE_COLOR, opacity: 0.9 }} />
            sub-chair → parent chair
          </span>
          <span className="flex items-center gap-1.5">
            <span className="inline-block h-0.5 w-5" style={{ backgroundColor: MODULE_EDGE_COLOR, opacity: 0.4 }} />
            module → coordinating chair
          </span>
        </div>

        {selectedNode ? (
          <div className="rounded-xl border border-border p-3 text-sm">
            <p className="font-medium">{selectedNode.label}</p>
            {selectedNode.kind === "chair" && selectedChair && (
              <>
                <p className="mt-1 text-xs text-muted-foreground">
                  {selectedChair.group_type} · Informatik {selectedChair.informatik_number}
                  {selectedNode.defunct && " · defunct"}
                </p>
                {parentChair && (
                  <p className="mt-1 text-xs text-muted-foreground">
                    embedded into <span className="text-foreground">{parentChair.name}</span>
                  </p>
                )}
                {childChairs.length > 0 && (
                  <p className="mt-1 text-xs text-muted-foreground">
                    parent of {childChairs.map((c) => c.name).join(", ")}
                  </p>
                )}
              </>
            )}
            {selectedNode.kind === "module" && (
              <p className="mt-1 text-xs text-muted-foreground">
                {data.modules.find((m) => m.module_id === selectedNode.id)?.area ?? "uncategorized"} ·{" "}
                {data.modules.find((m) => m.module_id === selectedNode.id)?.ects} CP
              </p>
            )}
            {touchingSelected.length > 0 && (
              <div className="mt-2 flex flex-col gap-1 border-t border-border pt-2">
                {touchingSelected.map((l) => {
                  const otherId = idOf(l.source) === selected ? idOf(l.target) : idOf(l.source);
                  const other = nodes.find((n) => n.id === otherId);
                  const direction = idOf(l.source) === selected ? "coordinated by" : "coordinates";
                  return (
                    <p key={l.id} className="text-xs text-muted-foreground">
                      {direction} <span className="text-foreground">{other?.label}</span>
                      {l.matchedPeople && l.matchedPeople.length > 0 ? ` (${l.matchedPeople.join(", ")})` : ""}
                    </p>
                  );
                })}
              </div>
            )}
            <button onClick={() => setSelected(null)} className="mt-2 text-xs underline text-muted-foreground hover:text-foreground">
              Clear selection
            </button>
          </div>
        ) : (
          <div className="themed-scrollbar flex flex-col gap-3 overflow-y-auto rounded-xl border border-border p-3" style={{ maxHeight: HEIGHT - 110 }}>
            {groupedChairs.map(([cluster, chairs]) => (
              <div key={cluster}>
                <p className="mb-1 flex items-center gap-1.5 text-xs font-medium text-foreground">
                  <span className="inline-block h-2 w-2 rounded-full" style={{ backgroundColor: clusterColor(cluster) }} />
                  Informatik {cluster}
                </p>
                <div className="flex flex-col">
                  {chairs.map((c) => (
                    <button
                      key={c.id}
                      onClick={() => setSelected(c.id)}
                      className={cn("flex items-baseline justify-between gap-2 py-0.5 text-left text-xs hover:text-foreground", isDefunct(c.group_type) ? "text-muted-foreground/60 italic" : "text-muted-foreground")}
                    >
                      <span className="truncate">{c.name}</span>
                      <span className="shrink-0 font-mono">{moduleCountByChair.get(c.id) ?? 0}</span>
                    </button>
                  ))}
                </div>
              </div>
            ))}
          </div>
        )}
      </aside>
    </div>
  );
}
