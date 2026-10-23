# Citation judge prompt

You will be given a single, already-atomic claim (one claim extracted from a sentence in an answer — see claim_split_prompt.md, which produced it) and the exact passage it cites as support. Decide whether the passage actually supports the claim. The claim has already been classified into one of three kinds; judge it accordingly.

1. **Positive claim** (asserts a specific fact, e.g. a number, a rule, a name): supported only if the passage genuinely contains or directly implies that specific fact. False if the passage is about a related but different topic, only partially supports the claim, or doesn't address it at all. Be strict — merely sharing the same general topic without stating the specific fact does not count.

2. **Negative/declining claim** (says the passage does *not* state some piece of information, e.g. "the passage does not specify the CP value"): supported if the passage, read on its own topic, genuinely does not contain that information — i.e. the negative claim is an accurate description of what's absent from the passage. Only mark this unsupported if the passage actually *does* contain the claimed-absent fact (making the decline wrong), or if the passage is so unrelated to the question's topic that citing it for this decline is misleading rather than informative.

3. **Advisory claim** (a procedural recommendation, not a factual claim about the passage at all — e.g. "contact the examination office to confirm"): always supported. It isn't asserting anything the passage needs to verify.

Respond with:
- `supported`: true or false per the rubric above, matching the claim's kind.
- `reason`: one short sentence explaining your judgement, naming which kind of claim you judged it as.
