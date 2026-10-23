# Prerequisite extraction prompt

You will be given one Master Informatik (MSInf) elective module's title, and the raw prose from its "prerequisites" and "recommended requirements" fields in the module handbook. These fields are free text, not a structured list, and most of what they mention is either a Bachelor's-level foundational course (outside this Master's program's electives) or a generic skill/topic rather than a specific named module.

Your job is to separate the two:

- `msinf_prerequisites`: OTHER **Master Informatik elective modules** that are explicitly named or unambiguously identifiable as prior knowledge for this module, each with a `title` and a `necessity` grade. Only include an entry here if it plausibly names a specific Master's-level MSInf elective — never a Bachelor's-level course (even if named, e.g. "Modul Programmierung", "Datenstrukturen und Algorithmen" are Bachelor's modules, not MSInf electives), and never a generic skill or topic phrase with no specific module behind it (e.g. "basic knowledge of algorithms" names a skill, not a module). When in doubt, leave it out — a missed edge is better than a wrong one.
- `external_prerequisite_note`: a short, human-readable summary of everything else mentioned (Bachelor's courses, generic skills/topics) — for a student to read, never used to build a graph edge.
- `reason`: one short sentence explaining your overall classification.

Titles don't need to match character-for-character — paraphrases like "the lecture Machine Learning" for a module titled "Machine Learning" should still be extracted. But do not invent a module that isn't plausibly real; a later step resolves your titles against the actual catalog and discards anything that doesn't match closely.

## Grading necessity

**Do not just copy the handbook's own wording.** German/EU module handbooks phrase almost every prerequisite as "recommended," even genuinely essential ones — a real, strictly binding admission requirement is rare and would usually appear as a separate formal exam-admission rule, not as prerequisite prose. Judge actual pedagogical necessity from the subject matter itself:

- `hard`: a student who skipped the named module would struggle badly or the module's content directly and heavily builds on it. A strong, reliable signal: naming patterns like "Advanced X" / "X II" / "X 2" naming a module literally called "X" (or "X I" / "X 1") — this is almost always a hard dependency, regardless of how softly it's phrased.
- `recommended`: a real head start, genuinely useful, but a student without it could reasonably catch up during the module.
- `good_to_know`: minor, contextual overlap — nice context, not a real dependency.
