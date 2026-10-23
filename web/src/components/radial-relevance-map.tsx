"use client";

// Every module in the catalog on a radial map -- distance from the goal
// at the center literally is its relevance score (closer = more
// relevant), angle groups it with its subject area.
//
// d3-force here only resolves local overlap (forceRadial pins each node
// near its correct relevance radius, forceCollide nudges collisions
// apart) -- it can't rearrange the layout freely, since radius encodes
// real data. The ambient "moving bubbles" drift is kept small for the
// same reason: wander too far and the position starts lying about
// relevance.

import { forceCollide, forceRadial, forceSimulation, type SimulationNodeDatum } from "d3-force";
import { select } from "d3-selection";
import { zoom, zoomIdentity, type ZoomBehavior } from "d3-zoom";
import { useEffect, useMemo, useRef, useState } from "react";

import { getRelevance, type ModuleRelevance, type RealEdge, type SimilarityEdge } from "@/lib/api";
import { cn } from "cn";

const WIDTH = 820;
const HEIGHT = 820;
const R = Math.min(WIDTH, HEIGHT) / 2 - 60;
const INNER_R = 26; // dead zone right around the goal, so nothing visually collides with it
const OUTER_R = R * 0.74; // compressed inward (not all the way to R) -- keeps the whole map closer together, with the rim left for area labels
const MIN_DOT = 2.5;
const MAX_DOT = 8.5;
const DRIFT_AMPLITUDE = 3; // px -- small on purpose: radius is real data here, not just packing
const LABEL_MIN_DOT = 6.5;

function polarRadius(relevance: number): number {
  const clamped = Math.max(0, Math.min(1, relevance));
  return INNER_R + (OUTER_R - INNER_R) * (1 - Math.sqrt(clamped));
}
function dotRadius(relevance: number): number {
  const clamped = Math.max(0, Math.min(1, relevance));
  return MIN_DOT + (MAX_DOT - MIN_DOT) * Math.sqrt(clamped);
}

interface MapNode extends SimulationNodeDatum {
  id: string;
  title: string;
  area: string | null;
  ects: number | null;
  relevance: number;
  dot: number;
  targetR: number;
  isGoal?: boolean;
  baseX: number;
  baseY: number;
  phaseX: number;
  phaseY: number;
  speed: number;
  renderX?: number;
  renderY?: number;
}

type EdgeKind = "handbook" | "goal" | "similarity";
interface MapLink {
  id: string;
  source: string | MapNode;
  target: string | MapNode;
  kind: EdgeKind;
  reason?: string;
  necessity?: string;
  layer?: string;
  similarity?: number;
}

const REAL_EDGE_COLOR: Record<"handbook" | "goal", string> = {
  handbook: "var(--destructive)",
  goal: "#5ab0e0",
};
const SIMILARITY_COLOR = "var(--muted-foreground)";

// A stable, deterministic color per area name (not a fixed palette --
// the catalog has more subject areas than would fit a hand-picked list).
function areaColor(area: string | null): string {
  const key = area ?? "uncategorized";
  let hash = 0;
  for (let i = 0; i < key.length; i++) hash = (hash * 31 + key.charCodeAt(i)) >>> 0;
  return `hsl(${hash % 360} 55% 58%)`;
}

function idOf(ref: string | MapNode): string {
  return typeof ref === "string" ? ref : ref.id;
}

function buildLinks(realEdges: RealEdge[], similarityEdges: SimilarityEdge[], nodeIds: Set<string>): MapLink[] {
  const links: MapLink[] = [];
  for (const e of realEdges) {
    if (!nodeIds.has(e.source) || !nodeIds.has(e.target)) continue;
    links.push({ id: `real:${e.source}-${e.target}`, source: e.source, target: e.target, kind: e.kind, reason: e.reason, necessity: e.necessity, layer: e.layer });
  }
  for (const e of similarityEdges) {
    if (!nodeIds.has(e.source) || !nodeIds.has(e.target)) continue;
    links.push({ id: `sim:${e.source}-${e.target}`, source: e.source, target: e.target, kind: "similarity", similarity: e.similarity });
  }
  return links;
}

export function RadialRelevanceMap({ trackId }: { trackId?: string }) {
  const [modules, setModules] = useState<ModuleRelevance[] | null>(null);
  const [realEdges, setRealEdges] = useState<RealEdge[]>([]);
  const [similarityEdges, setSimilarityEdges] = useState<SimilarityEdge[]>([]);
  const [trackTitle, setTrackTitle] = useState<string>("");
  const [error, setError] = useState<string | null>(null);
  const [selected, setSelected] = useState<string | null>(null);
  const [query, setQuery] = useState("");
  const groupRefs = useRef<Map<string, SVGGElement>>(new Map());
  const lineRefs = useRef<Map<string, SVGLineElement>>(new Map());
  const svgRef = useRef<SVGSVGElement>(null);
  const zoomLayerRef = useRef<SVGGElement>(null);
  const zoomBehaviorRef = useRef<ZoomBehavior<SVGSVGElement, unknown> | null>(null);

  useEffect(() => {
    if (!svgRef.current || !zoomLayerRef.current) return;
    const layer = zoomLayerRef.current;
    const zb = zoom<SVGSVGElement, unknown>()
      .scaleExtent([0.5, 6])
      .filter((event: Event) => {
        // Default d3-zoom filter, plus: never start a pan/drag gesture
        // from a module node -- otherwise d3-zoom's drag tracking eats
        // the click before it reaches the node's own onClick.
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
    // svgRef/zoomLayerRef are only non-null once `modules` has loaded and
    // the real <svg> has rendered (the loading-state branch above renders
    // no <svg> at all) -- re-run once that happens, not just on first mount.
  }, [modules]);

  function zoomBy(factor: number) {
    if (!svgRef.current || !zoomBehaviorRef.current) return;
    select(svgRef.current).transition().duration(180).call(zoomBehaviorRef.current.scaleBy, factor);
  }
  function resetZoom() {
    if (!svgRef.current || !zoomBehaviorRef.current) return;
    select(svgRef.current).transition().duration(180).call(zoomBehaviorRef.current.transform, zoomIdentity);
  }

  useEffect(() => {
    if (!trackId) return;
    setModules(null);
    setError(null);
    setSelected(null);
    getRelevance(trackId)
      .then((g) => {
        setModules(g.modules);
        setRealEdges(g.real_edges);
        setSimilarityEdges(g.similarity_edges);
        setTrackTitle(g.track.title);
      })
      .catch((e) => setError(e instanceof Error ? e.message : "Failed to load relevance scores."));
  }, [trackId]);

  const goalId = `goal:${trackId}`;

  // Built once per dataset -- not derived purely functionally, since
  // d3-force mutates these objects in place (x/y) as a deliberate,
  // contained exception to the project's usual "no mutation" style.
  const nodes = useMemo<MapNode[]>(() => {
    if (!modules) return [];
    const areas = Array.from(new Set(modules.map((m) => m.area ?? "uncategorized")));
    const sectorWidth = (2 * Math.PI) / areas.length;
    const byArea = new Map<string, ModuleRelevance[]>();
    for (const m of modules) {
      const key = m.area ?? "uncategorized";
      if (!byArea.has(key)) byArea.set(key, []);
      byArea.get(key)!.push(m);
    }

    const result: MapNode[] = modules.map((m) => {
      const area = m.area ?? "uncategorized";
      const areaIdx = areas.indexOf(area);
      const within = byArea.get(area)!;
      const posInArea = within.indexOf(m);
      const angle = areaIdx * sectorWidth + ((posInArea + 0.5) / within.length) * sectorWidth * 0.92 + sectorWidth * 0.04 - Math.PI / 2;
      const targetR = polarRadius(m.relevance);
      const x = Math.cos(angle) * targetR;
      const y = Math.sin(angle) * targetR;
      return {
        id: m.module_id,
        title: m.title,
        area: m.area,
        ects: m.ects,
        relevance: m.relevance,
        dot: dotRadius(m.relevance),
        targetR,
        x,
        y,
        baseX: x,
        baseY: y,
        phaseX: Math.random() * Math.PI * 2,
        phaseY: Math.random() * Math.PI * 2,
        speed: 0.3 + Math.random() * 0.3,
      };
    });
    result.push({
      id: goalId,
      title: trackTitle,
      area: null,
      ects: null,
      relevance: 1,
      dot: 10,
      targetR: 0,
      x: 0,
      y: 0,
      fx: 0,
      fy: 0,
      baseX: 0,
      baseY: 0,
      phaseX: 0,
      phaseY: 0,
      speed: 0,
      isGoal: true,
    });
    return result;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [modules, goalId]);

  const nodesById = useMemo(() => new Map(nodes.map((n) => [n.id, n])), [nodes]);

  const links = useMemo<MapLink[]>(() => {
    if (nodes.length === 0) return [];
    return buildLinks(realEdges, similarityEdges, new Set(nodes.map((n) => n.id)));
  }, [nodes, realEdges, similarityEdges]);

  useEffect(() => {
    if (nodes.length === 0) return;

    const sim = forceSimulation(nodes)
      .force(
        "radial",
        forceRadial<MapNode>((d) => d.targetR, 0, 0).strength(0.9)
      )
      .force("collide", forceCollide<MapNode>((d) => d.dot + 1.5).strength(0.75))
      .stop();
    for (let i = 0; i < 300; i++) sim.tick();

    for (const n of nodes) {
      n.baseX = n.x ?? 0;
      n.baseY = n.y ?? 0;
      const el = groupRefs.current.get(n.id);
      if (el) el.setAttribute("transform", `translate(${n.baseX},${n.baseY})`);
    }

    let start: number | null = null;
    let raf = 0;
    const animate = (t: number) => {
      if (start === null) start = t;
      const elapsed = (t - start) / 1000;
      for (const n of nodes) {
        const cx = n.isGoal ? 0 : n.baseX + Math.sin(elapsed * n.speed + n.phaseX) * DRIFT_AMPLITUDE;
        const cy = n.isGoal ? 0 : n.baseY + Math.cos(elapsed * n.speed * 0.8 + n.phaseY) * DRIFT_AMPLITUDE;
        n.renderX = cx;
        n.renderY = cy;
        const el = groupRefs.current.get(n.id);
        if (el) el.setAttribute("transform", `translate(${cx},${cy})`);
      }
      for (const l of links) {
        const el = lineRefs.current.get(l.id);
        if (!el) continue;
        const s = nodesById.get(idOf(l.source));
        const t2 = nodesById.get(idOf(l.target));
        if (!s || !t2) continue;
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
  }, [nodes, links, nodesById]);

  const groupedByArea = useMemo(() => {
    if (!modules) return [];
    const byArea = new Map<string, ModuleRelevance[]>();
    for (const m of modules) {
      const key = m.area ?? "uncategorized";
      if (!byArea.has(key)) byArea.set(key, []);
      byArea.get(key)!.push(m);
    }
    for (const arr of byArea.values()) arr.sort((a, b) => b.relevance - a.relevance);
    return Array.from(byArea.entries()).sort((a, b) => a[0].localeCompare(b[0]));
  }, [modules]);

  if (error) return <p className="text-sm text-destructive">{error}</p>;
  if (!trackId) return <p className="text-sm text-muted-foreground">Pick a goal above to map every module by relevance.</p>;
  if (!modules) return <p className="text-sm text-muted-foreground">Scoring the catalog against this goal…</p>;

  const trimmedQuery = query.trim().toLowerCase();
  const matched = trimmedQuery.length >= 2 ? new Set(modules.filter((m) => m.title.toLowerCase().includes(trimmedQuery)).map((m) => m.module_id)) : null;
  const selectedModule = modules.find((m) => m.module_id === selected);
  const touchingSelected = selected ? links.filter((l) => idOf(l.source) === selected || idOf(l.target) === selected) : [];
  const selectedTitle = selected === goalId ? trackTitle : selectedModule?.title;

  return (
    <div className="flex flex-col gap-4 lg:flex-row">
      <div className="relative flex-1 overflow-hidden rounded-xl border border-border bg-muted/20">
        <svg ref={svgRef} viewBox={`0 0 ${WIDTH} ${HEIGHT}`} className="w-full touch-none" style={{ height: HEIGHT }}>
          <g ref={zoomLayerRef}>
          <g transform={`translate(${WIDTH / 2},${HEIGHT / 2})`}>
            <g>
              {links.map((l) => {
                const touches = selected !== null && (idOf(l.source) === selected || idOf(l.target) === selected);
                const isSimilarity = l.kind === "similarity";
                const s = nodesById.get(idOf(l.source));
                const t2 = nodesById.get(idOf(l.target));
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
                    stroke={isSimilarity ? SIMILARITY_COLOR : REAL_EDGE_COLOR[l.kind as "handbook" | "goal"]}
                    strokeWidth={touches ? 2.2 : isSimilarity ? 1 : 1.6}
                    strokeOpacity={touches ? 0.95 : isSimilarity ? 0.16 : 0.6}
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
                  {/* Generous invisible hit target -- the smallest dots are
                      only ~5px across and keep drifting, far too small to
                      reliably click on their visible radius alone. */}
                  <circle r={Math.max(n.dot, 7) + 6} fill="transparent" />
                  <circle
                    r={n.dot}
                    fill={n.isGoal ? REAL_EDGE_COLOR.goal : areaColor(n.area)}
                    fillOpacity={n.isGoal ? 1 : 0.75}
                    stroke={isSelected || isMatch || n.isGoal ? "var(--foreground)" : "none"}
                    strokeWidth={isSelected || isMatch || n.isGoal ? (n.isGoal ? 1.5 : 2) : 0}
                  >
                    <title>{n.isGoal ? n.title : `${n.title} — ${Math.round(n.relevance * 100)}%`}</title>
                  </circle>
                  {(n.isGoal || n.dot > LABEL_MIN_DOT) && (
                    <text
                      textAnchor="middle"
                      dy={n.isGoal ? -16 : "-0.9em"}
                      className={cn("pointer-events-none select-none fill-foreground", n.isGoal ? "text-[13px] font-semibold" : "text-[8px] font-medium")}
                    >
                      {n.isGoal ? n.title : n.title.length > 22 ? `${n.title.slice(0, 20)}…` : n.title}
                    </text>
                  )}
                </g>
              );
            })}
          </g>
          </g>
        </svg>
        <div className="absolute bottom-3 left-3 flex flex-col gap-1">
          <button
            onClick={() => zoomBy(1.3)}
            aria-label="Zoom in"
            className="flex h-7 w-7 items-center justify-center rounded-md border border-border bg-card/90 text-sm text-muted-foreground hover:bg-muted hover:text-foreground"
          >
            +
          </button>
          <button
            onClick={() => zoomBy(1 / 1.3)}
            aria-label="Zoom out"
            className="flex h-7 w-7 items-center justify-center rounded-md border border-border bg-card/90 text-sm text-muted-foreground hover:bg-muted hover:text-foreground"
          >
            −
          </button>
          <button
            onClick={resetZoom}
            aria-label="Reset zoom"
            className="flex h-7 w-7 items-center justify-center rounded-md border border-border bg-card/90 text-xs text-muted-foreground hover:bg-muted hover:text-foreground"
          >
            ⤾
          </button>
        </div>
      </div>

      <aside className="flex w-full flex-col gap-3 lg:w-80 lg:shrink-0">
        <input
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="Search modules…"
          className="rounded-xl border border-border bg-card px-3 py-2 text-sm placeholder:text-muted-foreground focus:outline-none focus:ring-1 focus:ring-foreground"
        />
        <div className="flex flex-col gap-1 rounded-xl border border-border p-3 text-xs text-muted-foreground">
          <p className="text-foreground">Distance from the goal = relevance (closer = more relevant). Color = subject area.</p>
          <span className="mt-1 flex items-center gap-1.5">
            <span className="inline-block h-0.5 w-5" style={{ backgroundColor: REAL_EDGE_COLOR.handbook, opacity: 0.8 }} />
            real handbook prerequisite
          </span>
          <span className="flex items-center gap-1.5">
            <span className="inline-block h-0.5 w-5" style={{ backgroundColor: REAL_EDGE_COLOR.goal, opacity: 0.8 }} />
            curated, toward your goal
          </span>
          <span className="flex items-center gap-1.5">
            <span className="inline-block h-0.5 w-5" style={{ backgroundColor: SIMILARITY_COLOR, opacity: 0.5 }} />
            similar content (not a real link)
          </span>
        </div>

        {selected ? (
          <div className="rounded-xl border border-border p-3 text-sm">
            <p className="font-medium">{selectedTitle}</p>
            {selectedModule && (
              <p className="mt-1 text-xs text-muted-foreground">
                {(selectedModule.area ?? "uncategorized").replace(/_/g, " ")} · {selectedModule.ects} CP · relevance{" "}
                {(selectedModule.relevance * 100).toFixed(0)}%
              </p>
            )}
            {touchingSelected.length > 0 && (
              <div className="mt-2 flex flex-col gap-1 border-t border-border pt-2">
                {touchingSelected.map((l) => {
                  const otherId = idOf(l.source) === selected ? idOf(l.target) : idOf(l.source);
                  const other = otherId === goalId ? trackTitle : modules.find((m) => m.module_id === otherId)?.title;
                  if (l.kind === "similarity") {
                    return (
                      <p key={l.id} className="text-xs text-muted-foreground">
                        similar to <span className="text-foreground">{other}</span> ({((l.similarity ?? 0) * 100).toFixed(0)}%)
                      </p>
                    );
                  }
                  return (
                    <p key={l.id} className="text-xs text-muted-foreground">
                      {l.kind === "goal" ? "goal link" : `prerequisite (${l.necessity})`} — <span className="text-foreground">{other}</span>
                      {l.reason ? `: ${l.reason}` : ""}
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
            {groupedByArea.map(([area, mods]) => (
              <div key={area}>
                <p className="mb-1 flex items-center gap-1.5 text-xs font-medium text-foreground">
                  <span className="inline-block h-2 w-2 rounded-full" style={{ backgroundColor: areaColor(area) }} />
                  {area.replace(/_/g, " ")}
                </p>
                <div className="flex flex-col">
                  {mods.map((m) => (
                    <button
                      key={m.module_id}
                      onClick={() => setSelected(m.module_id)}
                      className="flex items-baseline justify-between gap-2 py-0.5 text-left text-xs text-muted-foreground hover:text-foreground"
                    >
                      <span className="truncate">{m.title}</span>
                      <span className="shrink-0 font-mono">{Math.round(m.relevance * 100)}%</span>
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
