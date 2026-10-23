# Field lookup classifier prompt

You will be given the title of a module that retrieval has already identified as the one the question is most likely about, and the question itself. Decide whether the question is asking for one or more of these five specific structured facts about that module:

- `ects`: how many CP / credit points the module is worth.
- `language`: what language(s) it is taught in.
- `cycle`: how regularly / in which semester(s) it is offered (including "irregularly").
- `level`: whether it is a Bachelor, Master, or both.
- `duration_semesters`: how many semesters it runs for.

This is **not** about the module's content, learning objectives, or prerequisites — those are free-text fields, answered a different way. Only the five listed above count.

A question can ask for more than one of these at once (e.g. "which semester and which language"). If the question isn't asking about this module's structured facts at all, say so.

Respond with:
- `is_structured_field_question`: true only if at least one of the five fields above is actually being asked for.
- `fields`: which of `ects`, `language`, `cycle`, `level`, `duration_semesters` are being asked for (empty list if none).
- `reason`: one short sentence.
