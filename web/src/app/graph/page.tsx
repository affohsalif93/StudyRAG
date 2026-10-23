"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

import { ChairsGraphView } from "@/components/chairs-graph";
import { PrerequisiteGraphView } from "@/components/prerequisite-graph";
import { RadialRelevanceMap } from "@/components/radial-relevance-map";
import { getTracks, type TrackSummary } from "@/lib/api";
import { cn } from "cn";

type Mode = "dependencies" | "radial" | "chairs";

const TITLES: Record<Mode, string> = {
  dependencies: "Prerequisite graph",
  radial: "Relevance map",
  chairs: "Chairs",
};
const DESCRIPTIONS: Record<Mode, string> = {
  dependencies: "Real prerequisite links from the handbook, plus how each track's modules move you toward its goal.",
  radial: "Every module placed by relevance to your goal — the closer it sits to the center, the more it matters.",
  chairs: "The 43 Informatik chairs, clustered by RWTH's own research areas, with the modules matched to who coordinates them.",
};

export default function GraphPage() {
  const [tracks, setTracks] = useState<TrackSummary[]>([]);
  const [trackId, setTrackId] = useState<string | undefined>(undefined);
  const [mode, setMode] = useState<Mode>("dependencies");

  useEffect(() => {
    getTracks().then((ts) => {
      setTracks(ts);
      setTrackId((cur) => cur ?? ts[0]?.track_id);
    });
  }, []);

  return (
    <div className="mx-auto flex min-h-screen max-w-6xl flex-col gap-4 px-4 py-10">
      <div>
        <Link
          href={mode === "dependencies" ? "/" : "/quiz"}
          className="text-xs text-muted-foreground underline hover:text-foreground"
        >
          {mode === "dependencies" ? "← Back to chat" : "← Back to quiz"}
        </Link>
        <p className="mt-3 text-xs font-medium uppercase tracking-wider text-muted-foreground">Module catalog explorer</p>
        <h1 className="mt-1 text-2xl font-semibold">{TITLES[mode]}</h1>
        <p className="mt-1 max-w-2xl text-sm text-muted-foreground">{DESCRIPTIONS[mode]}</p>
      </div>

      <div className="flex gap-2 text-xs">
        {(["dependencies", "radial", "chairs"] as Mode[]).map((m) => (
          <button
            key={m}
            onClick={() => setMode(m)}
            className={cn(
              "rounded-full border px-3 py-1",
              mode === m ? "border-foreground" : "border-border text-muted-foreground hover:bg-muted"
            )}
          >
            {TITLES[m]}
          </button>
        ))}
      </div>

      {mode !== "chairs" && tracks.length > 0 && (
        <div className="flex flex-wrap items-center gap-2 text-xs">
          <span className="text-muted-foreground">{mode === "dependencies" ? "Overlay a goal:" : "Goal:"}</span>
          {mode === "dependencies" && (
            <button
              onClick={() => setTrackId(undefined)}
              className={cn("rounded-full border px-3 py-1", !trackId ? "border-foreground" : "border-border text-muted-foreground hover:bg-muted")}
            >
              None
            </button>
          )}
          {tracks.map((t) => (
            <button
              key={t.track_id}
              onClick={() => setTrackId(t.track_id)}
              className={cn(
                "rounded-full border px-3 py-1",
                trackId === t.track_id ? "border-foreground" : "border-border text-muted-foreground hover:bg-muted"
              )}
            >
              {t.title}
            </button>
          ))}
        </div>
      )}

      {mode === "dependencies" && <PrerequisiteGraphView trackId={trackId} />}
      {mode === "radial" && <RadialRelevanceMap trackId={trackId} />}
      {mode === "chairs" && <ChairsGraphView />}
    </div>
  );
}
