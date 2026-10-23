# Claim split prompt

You will be given one sentence from an answer. The sentence may carry one or more citation markers like `[1]` or `[2]`, and may bundle together more than one distinct assertion — for example a positive fact plus a separate negative fact ("passage [1] gives the content, but no CP value"), or two facts each backed by a different cited passage ("A says X [1], while B says Y [2]").

Split the sentence into its distinct, atomic claims. Each claim should be a single self-contained assertion that could be checked against one or more passages on its own. For each claim, say which of the sentence's citation number(s) it actually relies on — usually the citation nearest the claim's own clause, not every citation in the sentence.

If the sentence makes only one claim, return it unsplit, as a single claim with all of the sentence's citation number(s).

For each claim, classify it as one of:
- `positive`: asserts a specific fact (a number, a rule, a name, an attribute).
- `negative`: asserts that some specific piece of information is absent from the passage(s).
- `advisory`: a procedural recommendation that isn't a factual claim about the passage at all (e.g. "contact the examination office to confirm"). This kind trivially needs no real support — it will always be treated as supported.

Respond with a list of claims, each with: `text` (the claim, in your own words if needed to stand alone), `citation_numbers` (list of ints), `kind` (one of the three above).
