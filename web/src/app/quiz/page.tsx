"use client";

import { useEffect, useState } from "react";

import { PrerequisiteGraphView } from "@/components/prerequisite-graph";
import { Button } from "@/components/ui/button";
import {
  getQuizSchema,
  getRecommendation,
  searchModules,
  type ModuleSearchResult,
  type QuizSchema,
  type QuizStage,
  type RecommendationResult,
} from "@/lib/api";
import { cn } from "cn";

type JobTitleAnswer = {
  track_id: string;
  job_title: string;
  skills: { skill: string; weight: number | null; evidence?: string }[];
};

type Answers = {
  interest?: string[];
  sub_area?: string[];
  work_style?: Record<string, string | number>;
  job_title?: JobTitleAnswer[];
  sector?: string;
  certainty?: string;
  skills?: Record<string, { level: number; weak: boolean }>;
  passed?: ModuleSearchResult[];
  constraints?: Record<string, unknown>;
};

function activeBranchKey(stage: QuizStage, answers: Answers): string | null {
  if (!stage.depends_on) return null;
  // depends_on always names a string[]-valued stage (interest) in this
  // app's schema -- TS can't narrow that across the Answers union on its
  // own, hence the cast.
  const dependValue = answers[stage.depends_on as keyof Answers] as string[] | undefined;
  if (!Array.isArray(dependValue)) return null;
  const branches = stage.branches ?? {};
  return dependValue.find((v) => v in branches) ?? null;
}

// Same idea as activeBranchKey, but returns every matching branch, not
// just the first -- the job_title stage needs this so a student who
// picked several Stage-1 interests can see and pick titles from all of
// them, feeding engine.recommend()'s multi-track merge.
function activeBranchKeys(stage: QuizStage, answers: Answers): string[] {
  if (!stage.depends_on) return [];
  const dependValue = answers[stage.depends_on as keyof Answers] as string[] | undefined;
  if (!Array.isArray(dependValue)) return [];
  const branches = stage.branches ?? {};
  return dependValue.filter((v) => v in branches);
}

function OptionToggle({ label, checked, onToggle }: { label: string; checked: boolean; onToggle: () => void }) {
  return (
    <button
      onClick={onToggle}
      className={cn(
        "rounded-xl border px-4 py-2.5 text-left text-sm transition-colors",
        checked ? "border-foreground bg-secondary" : "border-border hover:bg-muted"
      )}
    >
      {label}
    </button>
  );
}

function StageRenderer({
  stage,
  answers,
  setAnswers,
}: {
  stage: QuizStage;
  answers: Answers;
  setAnswers: React.Dispatch<React.SetStateAction<Answers>>;
}) {
  if (stage.type === "multi_select") {
    const branchKey = activeBranchKey(stage, answers);
    const options = stage.branches ? (branchKey ? stage.branches[branchKey]?.options : undefined) : stage.options;
    if (stage.branches && !branchKey) {
      return <p className="text-base text-muted-foreground">{stage.fallback_message}</p>;
    }
    const field = stage.id as "interest" | "sub_area";
    const selected = answers[field] ?? [];
    return (
      <div className="flex flex-col gap-2">
        {options?.map((opt) => (
          <OptionToggle
            key={opt.value}
            label={opt.label}
            checked={selected.includes(opt.value)}
            onToggle={() => {
              const isSelected = selected.includes(opt.value);
              const next = isSelected
                ? selected.filter((v) => v !== opt.value)
                : [...selected, opt.value].slice(-(stage.max_select ?? 99));
              setAnswers((a) => ({ ...a, [field]: next }));
            }}
          />
        ))}
      </div>
    );
  }

  if (stage.type === "work_style") {
    const workStyle = answers.work_style ?? {};
    return (
      <div className="flex flex-col gap-6">
        {stage.questions?.map((q) => (
          <div key={q.id} className="flex flex-col gap-2">
            <p className="text-sm font-medium">{q.prompt}</p>
            {q.scale ? (
              <div className="flex items-center gap-2">
                {Array.from({ length: q.scale[1] - q.scale[0] + 1 }, (_, i) => q.scale![0] + i).map((n) => (
                  <button
                    key={n}
                    onClick={() => setAnswers((a) => ({ ...a, work_style: { ...workStyle, [q.id]: n } }))}
                    className={cn(
                      "h-9 w-9 rounded-full border text-sm",
                      workStyle[q.id] === n ? "border-foreground bg-secondary" : "border-border hover:bg-muted"
                    )}
                  >
                    {n}
                  </button>
                ))}
                {q.scale_labels && (
                  <span className="ml-2 text-xs text-muted-foreground">
                    {q.scale_labels[0]} … {q.scale_labels[1]}
                  </span>
                )}
              </div>
            ) : (
              <div className="flex flex-wrap gap-2">
                {q.options?.map((opt) => (
                  <OptionToggle
                    key={opt}
                    label={opt.replaceAll("_", " ")}
                    checked={workStyle[q.id] === opt}
                    onToggle={() => setAnswers((a) => ({ ...a, work_style: { ...workStyle, [q.id]: opt } }))}
                  />
                ))}
              </div>
            )}
          </div>
        ))}
      </div>
    );
  }

  if (stage.type === "job_title") {
    const branchKeys = activeBranchKeys(stage, answers);
    if (branchKeys.length === 0) return <p className="text-base text-muted-foreground">{stage.fallback_message}</p>;
    const titles = branchKeys.flatMap((key) => stage.branches?.[key]?.titles ?? []);
    const selected = answers.job_title ?? [];
    return (
      <div className="flex flex-col gap-4">
        {titles.length > 1 && (
          <p className="text-xs text-muted-foreground">
            Pick one or more goals — picking more than one merges both tracks into a single recommendation (the higher layer wins for any module they share).
          </p>
        )}
        <div className="flex flex-col gap-3">
          {titles.map((t) => {
            const isSelected = selected.some((s) => s.track_id === t.track_id);
            return (
              <button
                key={t.track_id}
                onClick={() =>
                  setAnswers((a) => {
                    const current = a.job_title ?? [];
                    const next = isSelected
                      ? current.filter((s) => s.track_id !== t.track_id)
                      : [...current, { track_id: t.track_id, job_title: t.job_title, skills: (t as unknown as JobTitleAnswer).skills ?? [] }];
                    return { ...a, job_title: next };
                  })
                }
                className={cn(
                  "rounded-2xl border p-4 text-left transition-colors",
                  isSelected ? "border-foreground bg-secondary" : "border-border hover:bg-muted"
                )}
              >
                <div className="font-medium">{t.job_title}</div>
                <div className="text-sm text-muted-foreground">{t.day_in_the_life}</div>
              </button>
            );
          })}
        </div>
        {selected.length > 0 &&
          stage.follow_up?.map((q) => (
            <div key={q.id} className="flex flex-col gap-2">
              <p className="text-sm font-medium">{q.prompt}</p>
              <div className="flex flex-wrap gap-2">
                {q.options.map((opt) => (
                  <OptionToggle
                    key={opt}
                    label={opt}
                    checked={answers[q.id as "sector" | "certainty"] === opt}
                    onToggle={() => setAnswers((a) => ({ ...a, [q.id]: opt }))}
                  />
                ))}
              </div>
            </div>
          ))}
      </div>
    );
  }

  if (stage.type === "skills") {
    // Union across every selected target's skills, deduped by skill name
    // (same skill name appearing in two chosen tracks is shown once).
    const skillsList = Array.from(
      new Map((answers.job_title ?? []).flatMap((t) => t.skills).map((s) => [s.skill, s])).values()
    );
    if (skillsList.length === 0) {
      return <p className="text-base text-muted-foreground">No skills to rate yet — pick a goal in the previous step first.</p>;
    }
    const ratings = answers.skills ?? {};
    return (
      <div className="flex flex-col gap-4">
        {skillsList.map((s) => (
          <div key={s.skill} className="flex flex-col gap-2">
            <p className="text-sm font-medium">{s.skill.replaceAll("_", " ")}</p>
            {s.evidence && <p className="text-xs text-muted-foreground">{s.evidence}</p>}
            <div className="flex flex-wrap gap-2">
              {(stage.levels ?? []).map((level, i) => (
                <OptionToggle
                  key={level}
                  label={level.replaceAll("_", " ")}
                  checked={ratings[s.skill]?.level === i}
                  onToggle={() =>
                    setAnswers((a) => ({
                      ...a,
                      skills: { ...ratings, [s.skill]: { level: i, weak: ratings[s.skill]?.weak ?? false } },
                    }))
                  }
                />
              ))}
              <OptionToggle
                label="this is a weak area for me"
                checked={ratings[s.skill]?.weak ?? false}
                onToggle={() =>
                  setAnswers((a) => ({
                    ...a,
                    skills: { ...ratings, [s.skill]: { level: ratings[s.skill]?.level ?? 0, weak: !(ratings[s.skill]?.weak ?? false) } },
                  }))
                }
              />
            </div>
          </div>
        ))}
      </div>
    );
  }

  if (stage.type === "progress") {
    return <ModuleProgressPicker answers={answers} setAnswers={setAnswers} />;
  }

  if (stage.type === "constraints") {
    const constraints = answers.constraints ?? {};
    return (
      <div className="flex flex-col gap-4">
        {stage.fields?.map((f) => (
          <div key={f.id} className="flex flex-col gap-2">
            <p className="text-sm font-medium">{f.prompt}</p>
            {f.input === "number" ? (
              <input
                type="number"
                value={(constraints[f.id] as number) ?? ""}
                onChange={(e) => setAnswers((a) => ({ ...a, constraints: { ...constraints, [f.id]: Number(e.target.value) } }))}
                className="w-32 rounded-lg border border-input bg-transparent px-2.5 py-2 text-sm outline-none focus-visible:border-ring"
              />
            ) : (
              <div className="flex flex-wrap gap-2">
                {f.options?.map((opt) => {
                  const current = constraints[f.id];
                  const isMulti = f.input === "multi_select";
                  const checked = isMulti ? Array.isArray(current) && current.includes(opt) : current === opt;
                  return (
                    <OptionToggle
                      key={opt}
                      label={opt}
                      checked={checked}
                      onToggle={() => {
                        if (isMulti) {
                          const arr = Array.isArray(current) ? (current as string[]) : [];
                          const next = arr.includes(opt) ? arr.filter((v) => v !== opt) : [...arr, opt];
                          setAnswers((a) => ({ ...a, constraints: { ...constraints, [f.id]: next } }));
                        } else {
                          setAnswers((a) => ({ ...a, constraints: { ...constraints, [f.id]: opt } }));
                        }
                      }}
                    />
                  );
                })}
              </div>
            )}
          </div>
        ))}
      </div>
    );
  }

  if (stage.type === "summary") {
    return (
      <div className="flex flex-col gap-2 text-sm text-muted-foreground">
        <p>
          <span className="text-foreground">Goal:</span>{" "}
          {answers.job_title?.length ? answers.job_title.map((t) => t.job_title).join(" + ") : "not set"}
          {answers.sector ? ` — ${answers.sector}, ${answers.certainty}` : ""}
        </p>
        <p>
          <span className="text-foreground">Already passed:</span>{" "}
          {answers.passed?.length ? answers.passed.map((m) => m.title).join(", ") : "none"}
        </p>
        <p>
          <span className="text-foreground">Constraints:</span> {JSON.stringify(answers.constraints ?? {})}
        </p>
      </div>
    );
  }

  return null;
}

function ModuleProgressPicker({
  answers,
  setAnswers,
}: {
  answers: Answers;
  setAnswers: React.Dispatch<React.SetStateAction<Answers>>;
}) {
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<ModuleSearchResult[]>([]);
  const passed = answers.passed ?? [];

  useEffect(() => {
    const handle = setTimeout(() => {
      searchModules(query).then(setResults).catch(() => setResults([]));
    }, 250);
    return () => clearTimeout(handle);
  }, [query]);

  return (
    <div className="flex flex-col gap-3">
      <input
        value={query}
        onChange={(e) => setQuery(e.target.value)}
        placeholder="Search a module you've already passed…"
        className="w-full rounded-lg border border-input bg-transparent px-2.5 py-2 text-sm outline-none focus-visible:border-ring"
      />
      {results.length > 0 && (
        <div className="flex flex-col gap-1 rounded-lg border border-border p-1">
          {results.map((m) => (
            <button
              key={m.module_id}
              onClick={() => {
                if (!passed.some((p) => p.module_id === m.module_id)) {
                  setAnswers((a) => ({ ...a, passed: [...passed, m] }));
                }
                setQuery("");
                setResults([]);
              }}
              className="rounded-md px-2 py-1.5 text-left text-sm hover:bg-muted"
            >
              {m.title}
            </button>
          ))}
        </div>
      )}
      {passed.length > 0 && (
        <div className="flex flex-wrap gap-2">
          {passed.map((m) => (
            <span key={m.module_id} className="flex items-center gap-1.5 rounded-full bg-secondary px-3 py-1 text-xs">
              {m.title}
              <button onClick={() => setAnswers((a) => ({ ...a, passed: passed.filter((p) => p.module_id !== m.module_id) }))} aria-label="Remove">
                ×
              </button>
            </span>
          ))}
        </div>
      )}
    </div>
  );
}

function RecommendationView({ result, onRestart }: { result: RecommendationResult; onRestart: () => void }) {
  const [showGraph, setShowGraph] = useState(false);
  const layers: { key: "core" | "complementary" | "nice_to_have"; label: string }[] = [
    { key: "core", label: "Core — take these first" },
    { key: "complementary", label: "Complementary" },
    { key: "nice_to_have", label: "Nice to have" },
  ];
  const highlightModuleIds = Object.fromEntries(
    layers.flatMap(({ key }) => result[key].map((m) => [m.module_id, key] as const))
  );
  return (
    <div className="mx-auto flex min-h-screen max-w-2xl flex-col gap-6 px-4 py-10">
      <div>
        <h1 className="text-2xl font-semibold">
          Your plan: {result.targets?.length ? result.targets.map((t) => t.job_title).join(" + ") : result.target.job_title}
        </h1>
        <p className="mt-1 text-sm text-muted-foreground">{result.note}</p>
      </div>
      {layers.map(({ key, label }) => (
        <div key={key} className="flex flex-col gap-3">
          <h2 className="text-sm font-medium text-muted-foreground">{label}</h2>
          {result[key].length === 0 && <p className="text-sm text-muted-foreground">None.</p>}
          {result[key].map((m) => (
            <div key={m.module_id} className="rounded-2xl border border-border p-4">
              <div className="flex items-center justify-between">
                <span className="flex items-center gap-2 font-medium">
                  {m.module}
                  {m.research_industry_weight === "up" && (
                    <span className="rounded-full bg-primary/10 px-2 py-0.5 text-[10px] font-normal text-primary">
                      matches your lean
                    </span>
                  )}
                </span>
                <span className="text-xs text-muted-foreground">
                  {m.ects} CP · {m.area} · {m.cycle ?? "?"} · {m.language ?? "?"}
                  {m.handbook_page_start != null && (
                    <>
                      {" "}
                      ·{" "}
                      {m.handbook_page_start === m.handbook_page_end
                        ? `p. ${m.handbook_page_start}`
                        : `pp. ${m.handbook_page_start}-${m.handbook_page_end}`}
                    </>
                  )}
                </span>
              </div>
              <p className="mt-1 text-sm text-muted-foreground">{m.reason}</p>
              {m.probably_not_offered_next_semester && (
                <p className="mt-2 text-xs text-amber-600 dark:text-amber-400">
                  Probably not offered next semester, based on its usual cycle ({m.cycle}).
                </p>
              )}
              {m.foundation_first_warnings.length > 0 && (
                <div className="mt-2 rounded-lg bg-destructive/10 px-3 py-2 text-xs text-destructive">
                  Foundation first: this builds directly on{" "}
                  {m.foundation_first_warnings.map((w) => w.title).join(", ")}, which you haven&apos;t marked as passed yet.
                </div>
              )}
            </div>
          ))}
        </div>
      ))}
      {result.weak_skill_notes != null && result.weak_skill_notes.length > 0 && (
        <div className="flex flex-col gap-3">
          <h2 className="text-sm font-medium text-muted-foreground">Your flagged weak areas</h2>
          {result.weak_skill_notes.map((n) => (
            <div key={n.skill} className="rounded-2xl border border-border p-4">
              <span className="font-medium">{n.skill.replaceAll("_", " ")}</span>
              {n.evidence && <p className="mt-1 text-sm text-muted-foreground">{n.evidence}</p>}
            </div>
          ))}
        </div>
      )}
      {result.practical_skills.length > 0 && (
        <div className="flex flex-col gap-3">
          <h2 className="text-sm font-medium text-muted-foreground">
            Practical skills to build on your own — no module teaches these
          </h2>
          {result.practical_skills.map((s) => (
            <div key={s.skill} className="rounded-2xl border border-border p-4">
              <span className="font-medium">{s.skill.replaceAll("_", " ")}</span>
              <p className="mt-1 text-sm text-muted-foreground">{s.why}</p>
              <p className="mt-2 text-xs text-muted-foreground">
                {s.evidence}{" "}
                <a href={s.learn_more_url} target="_blank" rel="noreferrer" className="underline hover:text-foreground">
                  Learn more
                </a>
              </p>
            </div>
          ))}
        </div>
      )}
      {result.excluded.length > 0 && (
        <div className="text-xs text-muted-foreground">
          Excluded: {result.excluded.map((e) => `${e.module} (${e.reason})`).join("; ")}
        </div>
      )}
      {result.rule_check && (
        <div className="rounded-2xl border border-border p-4">
          <h2 className="text-sm font-medium text-muted-foreground">Rule check</h2>
          <p className="mt-2 text-sm">
            {result.rule_check.area_requirement.satisfied
              ? "This plan meets the area requirement."
              : "This plan alone doesn't yet meet the area requirement — it's only one track, not your full elective plan."}
          </p>
          <p className="mt-1 text-xs text-muted-foreground">{result.rule_check.area_requirement.rule}</p>
          <div className="mt-2 flex flex-wrap gap-2 text-xs">
            {Object.entries(result.rule_check.area_requirement.cp_by_area).map(([area, cp]) => (
              <span
                key={area}
                className={`rounded-full border px-2 py-1 ${
                  result.rule_check!.area_requirement.areas_meeting_minimum.includes(area)
                    ? "border-primary/40 text-primary"
                    : "border-border text-muted-foreground"
                }`}
              >
                {area.replaceAll("_", " ")}: {cp} CP
              </span>
            ))}
          </div>
          <p className="mt-2 text-xs text-muted-foreground">
            {result.rule_check.area_requirement.citation} · {result.rule_check.area_requirement.basis}
          </p>
        </div>
      )}
      {result.cp_budget != null && (
        <p className="text-xs text-muted-foreground">
          {result.cp_budget.total_recommended_cp} CP recommended · you said {result.cp_budget.cp_missing_total} CP remaining —{" "}
          {result.cp_budget.note}
        </p>
      )}
      <div className="flex flex-col gap-3">
        <Button variant="outline" onClick={() => setShowGraph((v) => !v)} className="self-start">
          {showGraph ? "Hide" : "Show"} prerequisite graph
        </Button>
        {showGraph && <PrerequisiteGraphView highlightModuleIds={highlightModuleIds} trackId={result.target.track_id} />}
      </div>
      <Button variant="outline" onClick={onRestart} className="self-start">
        Start over
      </Button>
    </div>
  );
}

export default function QuizPage() {
  const [schema, setSchema] = useState<QuizSchema | null>(null);
  const [stageIndex, setStageIndex] = useState(0);
  const [answers, setAnswers] = useState<Answers>({});
  const [result, setResult] = useState<RecommendationResult | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    getQuizSchema()
      .then(setSchema)
      .catch((e) => setError(e instanceof Error ? e.message : "Failed to load the quiz."));
  }, []);

  if (error && !schema) {
    return <div className="p-8 text-base text-destructive">{error}</div>;
  }
  if (!schema) {
    return <div className="p-8 text-base text-muted-foreground">Loading quiz…</div>;
  }
  if (result) {
    return (
      <RecommendationView
        result={result}
        onRestart={() => {
          setResult(null);
          setStageIndex(0);
          setAnswers({});
        }}
      />
    );
  }

  const stage = schema.stages[stageIndex];
  const isLast = stageIndex === schema.stages.length - 1;

  const buildProfile = () => ({
    // One shared sector/certainty answer applies to every selected
    // target -- "where are you headed" is a property of the student,
    // not asked per track, even when more than one track is picked.
    targets: (answers.job_title ?? []).map((t) => ({
      job_title: t.job_title,
      track_id: t.track_id,
      sector: answers.sector ?? "industry",
      certainty: answers.certainty ?? "exploring",
    })),
    interests: answers.interest ?? [],
    sub_areas: answers.sub_area ?? [],
    work_style: answers.work_style
      ? { theory_vs_practice: Number(answers.work_style.theory_vs_practice ?? 3), exam_formats_avoid: [] }
      : null,
    skills: Object.fromEntries(Object.entries(answers.skills ?? {}).map(([k, v]) => [k, { level: v.level, weak: v.weak }])),
    progress: { passed: (answers.passed ?? []).map((m) => ({ module_id: m.module_id, grade: null })), current: [], failed_or_not_taken: [] },
    constraints: answers.constraints ?? null,
  });

  const handleFinish = async () => {
    setLoading(true);
    setError(null);
    try {
      setResult(await getRecommendation(buildProfile()));
    } catch (e) {
      setError(e instanceof Error ? e.message : "Something went wrong.");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="mx-auto flex min-h-screen max-w-2xl flex-col gap-6 px-4 py-10">
      <div className="text-sm text-muted-foreground">
        Step {stageIndex + 1} of {schema.stages.length}
      </div>
      <h1 className="text-2xl font-semibold">{stage.title}</h1>
      <StageRenderer stage={stage} answers={answers} setAnswers={setAnswers} />
      {error && <p className="text-base text-destructive">{error}</p>}
      <div className="flex items-center justify-between pt-4">
        <Button variant="ghost" onClick={() => setStageIndex((i) => Math.max(i - 1, 0))} disabled={stageIndex === 0}>
          Back
        </Button>
        {isLast ? (
          <Button onClick={handleFinish} disabled={loading}>
            {loading ? "Thinking…" : "See my recommendation"}
          </Button>
        ) : (
          <Button onClick={() => setStageIndex((i) => Math.min(i + 1, schema.stages.length - 1))}>Next</Button>
        )}
      </div>
    </div>
  );
}
