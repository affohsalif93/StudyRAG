# Version/source-conflict judge prompt

You will be given a final answer and a set of numbered source passages, some from different documents. Some passages may coincidentally share a number (e.g. "30 CP") while addressing completely unrelated rules — that is not a conflict.

Decide:
- `is_true_conflict`: true only if two or more passages state a *different* value for the *same specific rule* (not just similar numbers on different topics).
- `handled_correctly`: true if the answer, when a true conflict exists, explicitly shows both values and says which document/source each comes from, rather than picking one silently or treating them as equivalent. If there is no true conflict, this should be true as long as the answer didn't invent one.
- `reason`: one short sentence explaining your judgement.
