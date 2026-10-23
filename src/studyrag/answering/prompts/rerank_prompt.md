# Rerank prompt

You will be given a student's question and a set of numbered candidate passages retrieved by vector similarity search. Re-rank them by genuine relevance to the *specific* question, not shared vocabulary alone.

Pay special attention to a recurring failure case in this corpus: multiple documents (the Bachelor PO, the Master PO, the ÜPO) state near-identical-sounding rules about the same topic (e.g. early master modules, grade exclusion, thesis duration), each under its own § number. A passage that merely shares wording isn't automatically the right one — check which document and § the question is actually asking about, and prefer the passage that genuinely matches, not the one that happens to use similar phrases. The same applies to near-identical module titles that differ only slightly (e.g. a singular vs. plural name) — don't let superficial term overlap outrank genuine topical relevance.

Respond with:
- `top_indices`: the candidate numbers (1-based), best first, most relevant to least relevant.
