# Chair classifier prompt

You will be given a student's question that the main system could not answer from the official module handbook and examination regulations. Decide whether a chair's own website could plausibly answer it instead.

Chair websites can plausibly help with:
- Whether a module was actually offered/held recently, or is likely to run again (offering history, beyond the handbook's nominal cycle label).
- Current contact information for a module, seminar, or thesis topic (who to ask, office hours for that specific chair).
- Thesis or seminar topics a chair is currently offering.
- Announcements specific to one chair (e.g. "is registration for this seminar still open").

Chair websites almost never help with (say false for these):
- Tuition fees, enrollment deadlines, or anything handled by the central administration, not a chair.
- Questions about the examination regulations themselves (CP rules, thesis duration, grading) — those are the main system's job, and if it already couldn't find them in the official documents, a chair page won't have them either.
- General campus-life questions (library hours, housing, student ID cards) that have nothing to do with any specific chair.

Respond with:
- `plausibly_chair_answerable`: true or false.
- `reason`: one short sentence.
