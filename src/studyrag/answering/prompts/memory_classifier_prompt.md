# Memory classifier prompt

You will be given a student's question and what's already remembered about them. Decide whether the question itself reveals a new or updated durable fact about the student — something true of them generally, not just relevant to this one question — worth remembering for future conversations.

Durable facts worth remembering: career goal, self-rated weak subjects, modules already completed or passed, constraints (CP remaining, semesters left, preferred language). A one-off factual lookup ("how many CP is X worth?") reveals nothing about the student and should not be remembered.

Require genuine first-person self-disclosure — the student must be stating something about *themselves* ("I already passed...", "I'm aiming for...", "I'm weak in..."). A question phrased in the third person or about a general category of student ("What must a Master Informatik student do before...", "Which module is excluded for a Bachelor student...") is asking about a *rule*, not disclosing anything about the asker — do not infer that the asker belongs to that category just because the question mentions it. When in doubt, don't remember.

If the question updates or contradicts something already remembered, reuse that same key rather than inventing a new one — the write is a clean overwrite, not a second, conflicting entry.

A single question can reveal more than one distinct fact (e.g. a completed module *and* a career goal in the same sentence) — give each its own entry with its own key. Never bundle unrelated facts into one key just because they appeared together; a later question updating only one of them needs to find it on its own.

Respond with:
- `should_remember`: true only if the question itself states at least one durable fact about the student.
- `facts`: one entry per distinct fact, each with a short reusable snake_case `key` (e.g. `career_goal`, `weak_subjects`, `modules_completed`) and its `value`. Empty list if `should_remember` is false.
- `reason`: one short sentence.
