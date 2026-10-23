# Answer correctness judge prompt

You will be given a student's question, the retrieved passages the assistant had access to, and the assistant's answer. Decide whether the answer is correct.

An answer is correct if it is faithful to the passages AND actually addresses what the question asked:
- If the passages contain the answer, the assistant's answer must state the right fact, not a wrong or fabricated one.
- If the passages do **not** contain the answer, the correct behavior is for the assistant to say so (and suggest contacting the examination office or responsible chair) — count that as correct. Do not penalize a truthful "I don't know."
- If the passages conflict across documents, the correct behavior is to show both values and name which document each comes from, not silently pick one. Count that as correct; count silently picking one side as incorrect.
- An answer that states a fact not supported by the passages, even if it happens to be true in reality, is incorrect — the assistant isn't allowed general knowledge, only the given passages.

Respond with:
- `correct`: true or false, per the rubric above.
- `reason`: one short sentence explaining your judgement.

Be strict and specific — judge against what the passages actually say, not against what you independently know about German university regulations.
