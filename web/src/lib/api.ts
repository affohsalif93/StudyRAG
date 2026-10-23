// Talks to the StudyRAG FastAPI backend (src/studyrag/api/app.py).
// NEXT_PUBLIC_* so it's readable in the browser, not just at build time.
const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export type ChatTurn = { role: "user" | "assistant"; content: string };

export type Source = Record<string, unknown>;

export type AskResponse = {
  question: string;
  answer: string;
  sources: Source[];
  abstained: boolean;
};

async function parseErrorDetail(res: Response): Promise<string> {
  const body = await res.json().catch(() => null);
  if (body?.detail) {
    return typeof body.detail === "string" ? body.detail : JSON.stringify(body.detail);
  }
  return `Request failed (${res.status})`;
}

export async function askQuestion(question: string, history: ChatTurn[]): Promise<AskResponse> {
  const res = await fetch(`${API_URL}/ask`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ question, history }),
  });
  if (!res.ok) throw new Error(await parseErrorDetail(res));
  return res.json();
}

export async function sendFeedback(params: {
  question: string;
  answer: string;
  sources: Source[];
  rating: "up" | "down";
  comment?: string;
}): Promise<{ id: number }> {
  const res = await fetch(`${API_URL}/feedback`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(params),
  });
  if (!res.ok) throw new Error(await parseErrorDetail(res));
  return res.json();
}

// Quiz schema + recommendation types — see src/studyrag/recommender/.
export type QuizOption = { value: string; label: string };
export type QuizStage = {
  id: string;
  title: string;
  type: string;
  skip_allowed?: boolean;
  max_select?: number;
  options?: QuizOption[];
  depends_on?: string;
  branches?: Record<string, { options?: QuizOption[]; titles?: JobTitleOption[] }>;
  fallback_message?: string;
  questions?: { id: string; prompt: string; scale?: [number, number]; scale_labels?: string[]; options?: string[] }[];
  follow_up?: { id: string; prompt: string; options: string[] }[];
  source?: string;
  levels?: string[];
  fields?: { id: string; prompt: string; input: string; options?: string[] }[];
};
export type JobTitleOption = { track_id: string; job_title: string; day_in_the_life: string };
export type QuizSchema = { stages: QuizStage[] };

export async function getQuizSchema(): Promise<QuizSchema> {
  const res = await fetch(`${API_URL}/quiz/schema`);
  if (!res.ok) throw new Error(await parseErrorDetail(res));
  return res.json();
}

export type RecommendedModule = {
  module: string;
  module_id: string;
  ects: number;
  area: string;
  layer: string;
  reason: string;
  cycle: string | null;
  language: string | null;
  exam_formats: string[];
  handbook_page_start: number | null;
  handbook_page_end: number | null;
  foundation_first_warnings: { module_id: string; title: string; reason: string }[];
  research_industry_weight: "up" | "down" | null;
  probably_not_offered_next_semester: boolean | null;
};
export type PracticalSkill = { skill: string; why: string; evidence: string; learn_more_url: string };
export type WeakSkillNote = { skill: string; track_id: string; weight: number | null; evidence?: string };
export type CpBudget = { total_recommended_cp: number; cp_missing_total: number; note: string };

export type AreaRequirementCheck = {
  rule: string;
  citation: string;
  cp_by_area: Record<string, number>;
  areas_meeting_minimum: string[];
  satisfied: boolean;
  basis: string;
};

export type RecommendationResult = {
  target: { job_title: string; track_id: string; track_title: string };
  targets?: { job_title: string; track_id: string; track_title: string }[];
  core: RecommendedModule[];
  complementary: RecommendedModule[];
  nice_to_have: RecommendedModule[];
  excluded: { module: string; reason: string }[];
  practical_skills: PracticalSkill[];
  weak_skill_notes?: WeakSkillNote[];
  cp_budget?: CpBudget | null;
  rule_check?: { area_requirement: AreaRequirementCheck; early_master_cap: { applies: boolean; note: string } };
  note: string;
  error?: string;
};

export type ModuleSearchResult = { module_id: string; title: string };

export async function searchModules(q: string): Promise<ModuleSearchResult[]> {
  if (q.trim().length < 2) return [];
  const res = await fetch(`${API_URL}/modules/search?q=${encodeURIComponent(q)}`);
  if (!res.ok) throw new Error(await parseErrorDetail(res));
  return res.json();
}

// Prerequisite graph types — see
// src/studyrag/recommender/prerequisites.py:get_prerequisite_graph and
// tracks.py:build_goal_graph. Two edge kinds: "handbook" (explicitly named
// in a module's own prerequisites text) and "goal" (this module moves you
// toward a track's career goal, from our own track curation).
export type GraphNode = { module_id: string; title: string; kind: "module" | "goal" };
export type GraphEdge = {
  source: string;
  target: string;
  kind: "handbook" | "goal";
  necessity?: "hard" | "recommended" | "good_to_know";
  layer?: "core" | "complementary" | "nice_to_have";
  reason: string;
};
export type PrerequisiteGraph = { nodes: GraphNode[]; edges: GraphEdge[] };

export async function getPrerequisiteGraph(trackId?: string): Promise<PrerequisiteGraph> {
  const url = trackId ? `${API_URL}/graph/prerequisites?track_id=${encodeURIComponent(trackId)}` : `${API_URL}/graph/prerequisites`;
  const res = await fetch(url);
  if (!res.ok) throw new Error(await parseErrorDetail(res));
  return res.json();
}

export type TrackSummary = { track_id: string; title: string };

export async function getTracks(): Promise<TrackSummary[]> {
  const res = await fetch(`${API_URL}/tracks`);
  if (!res.ok) throw new Error(await parseErrorDetail(res));
  return res.json();
}

// Every module in the catalog, scored by embedding similarity to a
// track's goal — see src/studyrag/recommender/relevance.py. `relevance`
// is already normalized to 0..1 and gamma-curved.
export type ModuleRelevance = {
  module_id: string;
  title: string;
  area: string | null;
  ects: number;
  relevance: number;
  raw_similarity: number;
};
// Reuses the exact edge shape from the Dependencies view (kind, necessity,
// layer, reason) plus a separate content-similarity edge set -- see
// src/studyrag/recommender/relevance.py:similarity_edges.
export type RealEdge = GraphEdge;
export type SimilarityEdge = { source: string; target: string; similarity: number };
export type RelevanceGraph = {
  track: TrackSummary;
  modules: ModuleRelevance[];
  real_edges: RealEdge[];
  similarity_edges: SimilarityEdge[];
};

export async function getRelevance(trackId: string): Promise<RelevanceGraph> {
  const res = await fetch(`${API_URL}/graph/relevance?track_id=${encodeURIComponent(trackId)}`);
  if (!res.ok) throw new Error(await parseErrorDetail(res));
  return res.json();
}

export async function getRecommendation(profile: Record<string, unknown>): Promise<RecommendationResult> {
  const res = await fetch(`${API_URL}/recommend`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(profile),
  });
  if (!res.ok) throw new Error(await parseErrorDetail(res));
  return res.json();
}

// The chairs graph — see src/studyrag/recommender/chairs_graph.py. A
// separate graph from the relevance map and dependency DAG: chairs
// answer "who teaches this, who do I talk to", not "how relevant is
// this to my goal".
export type ChairNode = {
  id: string;
  name: string;
  group_type: string; // "Lehrstuhl" | "LuFG" | "JP" | "ehemals Lehrstuhl" | "ehemals LuFG"
  informatik_number: string; // mostly "1".."16", one "Zweitsitz"
  parent_chair_id: string | null;
};
export type ChairModuleNode = { module_id: string; title: string; area: string | null; ects: number };
export type ChairModuleEdge = { source: string; target: string; matched_people: string[] };
export type ChairParentEdge = { source: string; target: string };
export type ChairsGraph = {
  chairs: ChairNode[];
  modules: ChairModuleNode[];
  module_edges: ChairModuleEdge[];
  parent_edges: ChairParentEdge[];
};

export async function getChairsGraph(): Promise<ChairsGraph> {
  const res = await fetch(`${API_URL}/graph/chairs`);
  if (!res.ok) throw new Error(await parseErrorDetail(res));
  return res.json();
}

// Renders a short, readable label for one source — the shape varies by
// kind (module / rule / module_field_lookup / chair_lookup), matching
// src/studyrag/answering/chat.py's actual source dicts.
export function sourceLabel(source: Source): string {
  if (source.kind === "chair_lookup") return "Chair website (see links in the answer)";

  const parts: string[] = [];
  if (typeof source.title === "string") parts.push(source.title);
  else if (typeof source.source_id === "string") parts.push(source.source_id);

  if (source.paragraph) {
    parts.push(`§ ${source.paragraph}${source.absatz ? ` Abs. ${source.absatz}` : ""}`);
  }
  if (source.page_start) parts.push(`p. ${source.page_start}`);

  return parts.join(" — ") || "Source";
}
