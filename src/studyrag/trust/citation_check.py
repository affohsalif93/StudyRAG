"""Citation check -- first a rule-based check (do the numbers a cited
sentence claims actually appear in the passage it cites), then an
LLM-judge check for genuine semantic support. Pipeline-agnostic: takes
the final answer text and the same `sources` list both pipelines
already return (1-based citation numbers map to sources[n-1]).
"""

from __future__ import annotations

import re

from openai import OpenAI
from pydantic import BaseModel, Field

from studyrag.answering.chat import DISCLAIMER
from studyrag.answering.prompts import load_prompt
from studyrag.config import CHAT_MODEL
from studyrag.observability import get_openai_client

# (?!\[) stops a split between "sentence. " and a trailing "[2]" — without
# it, a citation that trails after the period (the normal pattern: "...the
# colloquium. [2]") gets severed from its own sentence and swept into
# whatever follows, including the appended disclaimer. Found by running
# this against a real answer and seeing the citation land in a "sentence"
# that was actually just disclaimer text.
_SENTENCE_RE = re.compile(r"(?<=[.!?])\s+(?!\[)")
_CITATION_RE = re.compile(r"\[(\d+)\]")
_NUMBER_RE = re.compile(r"\b\d+(?:[.,]\d+)?\b")


class CitationJudgement(BaseModel):
    supported: bool = Field(description="True only if the passage genuinely supports the specific claim.")
    reason: str = Field(description="One short sentence explaining the judgement.")


class SubClaim(BaseModel):
    text: str = Field(description="The atomic claim, standing on its own.")
    citation_numbers: list[int] = Field(description="Which of the sentence's citation number(s) this claim relies on.")
    kind: str = Field(description="One of: positive, negative, advisory.")


class ClaimSplitResult(BaseModel):
    claims: list[SubClaim]


def extract_cited_sentences(answer: str) -> list[str]:
    """Returns each distinct sentence in the answer that carries at least
    one citation marker, in order, deduplicated. A sentence is handed to
    split_claims() next rather than checked as a single unit — one
    sentence can bundle multiple distinct claims (see claim_split_prompt.md).
    """
    sentences = _SENTENCE_RE.split(answer)
    seen: set[str] = set()
    cited_sentences = []
    for sentence in sentences:
        sentence = sentence.strip()
        if sentence in seen or not _CITATION_RE.search(sentence):
            continue
        seen.add(sentence)
        cited_sentences.append(sentence)
    return cited_sentences


def split_claims(
    sentence: str,
    client: OpenAI | None = None,
    model: str = CHAT_MODEL,
) -> list[SubClaim]:
    """Breaks one cited sentence into its atomic claims -- judging a
    whole sentence as one unit fails when it mixes a positive and a
    negative claim, or cites two passages for two different halves.
    """
    client = client or get_openai_client()
    response = client.chat.completions.parse(
        model=model,
        messages=[
            {"role": "system", "content": load_prompt("claim_split_prompt")},
            {"role": "user", "content": sentence},
        ],
        response_format=ClaimSplitResult,
    )
    return response.choices[0].message.parsed.claims


def check_rule_based(sentence: str, passage_text: str) -> dict:
    """Do the numbers the sentence claims actually appear in the passage?

    Deliberately narrow: numbers are the most objective, easiest-to-verify
    signal, and catch citing the wrong passage that coincidentally
    contains a matching number. "Key terms" beyond numbers is left to the
    LLM judge below rather than a second brittle regex heuristic.
    """
    # Strip citation markers first — "[2]" contains the digit "2", which
    # is metadata about *which* source, not a claimed fact, and would
    # otherwise get checked as if it were a number the sentence asserts.
    sentence_without_citations = _CITATION_RE.sub("", sentence)
    claimed = set(_NUMBER_RE.findall(sentence_without_citations))
    present = set(_NUMBER_RE.findall(passage_text))
    missing = claimed - present
    return {
        "numbers_claimed": sorted(claimed),
        "numbers_missing_from_passage": sorted(missing),
        "passed": not missing,
    }


def check_llm_judge(
    claim: str,
    passage_text: str,
    kind: str = "positive",
    client: OpenAI | None = None,
    model: str = CHAT_MODEL,
) -> CitationJudgement:
    if kind == "advisory":
        # A procedural recommendation ("contact the examination office")
        # isn't a factual claim about the passage — nothing to check.
        return CitationJudgement(supported=True, reason="Advisory claim, not a factual assertion about the passage.")
    client = client or get_openai_client()
    response = client.chat.completions.parse(
        model=model,
        messages=[
            {"role": "system", "content": load_prompt("citation_judge_prompt")},
            {"role": "user", "content": f"Claim ({kind}): {claim}\n\nPassage: {passage_text}"},
        ],
        response_format=CitationJudgement,
    )
    return response.choices[0].message.parsed


def check_all_citations(
    answer: str,
    sources: list[dict],
    client: OpenAI | None = None,
    model: str = CHAT_MODEL,
) -> list[dict]:
    """Runs both checks for every atomic claim in every cited sentence.
    The disclaimer is stripped first — it's appended after the model's
    real answer and was never meant to be checked for citations. Each
    cited sentence is split into its atomic claims (split_claims) before
    judging, since a whole-sentence judgement fails on sentences that
    bundle a positive and a negative claim together, or cite two
    passages for two different halves of the same sentence.
    """
    client = client or get_openai_client()
    answer = answer.split(DISCLAIMER)[0]
    cited_sentences = extract_cited_sentences(answer)

    results = []
    for sentence in cited_sentences:
        for claim in split_claims(sentence, client=client, model=model):
            if not claim.citation_numbers:
                results.append(
                    {"sentence": sentence, "claim": claim.text, "kind": claim.kind, "error": "no citation number attached"}
                )
                continue
            for n in claim.citation_numbers:
                if n < 1 or n > len(sources):
                    results.append(
                        {"citation": n, "sentence": sentence, "claim": claim.text, "error": "citation number has no matching source"}
                    )
                    continue
                passage_text = sources[n - 1]["text"]
                rule_result = check_rule_based(claim.text, passage_text)
                judge_result = check_llm_judge(claim.text, passage_text, kind=claim.kind, client=client, model=model)
                results.append(
                    {
                        "citation": n,
                        "sentence": sentence,
                        "claim": claim.text,
                        "kind": claim.kind,
                        "rule_based": rule_result,
                        "llm_judge": {"supported": judge_result.supported, "reason": judge_result.reason},
                    }
                )
    return results
