# Eval questions — first draft batch (6 of 30-50)

Written before any retrieval/parsing code, per Step 2. Each verified against the actual downloaded PDF text (`data/raw/`) with `pdftotext`, not guessed. Page numbers are PDF page numbers (not printed footer numbers, which reset per document) — recheck once the real PDF parser (Step 4) is in place, since page-counting by form-feed character here is a manual stand-in.

| # | Type | Question | Expected answer | Source | Page |
|---|---|---|---|---|---|
| 1 | Direct lookup | How many CP is the "Masterarbeit" module worth in the Master Informatik program? | 30 CP | Master Informatik PO 2023 (Gesamtfassung 18.09.2025, Nr. 2025/340), § 13 Abs. 6 | 9 |
| 2 | Direct lookup | In how many of the five Wahlpflicht areas must a Master Informatik student earn at least 12 CP, and which area is mandatory among them? | At least 3 of the 5 areas; "Theoretische Informatik" must be one of them | Master Informatik PO 2023, § 4 Abs. 2 | 5 |
| 3 | Two-passage combination | What is the maximum CP a Bachelor Informatik student may take as early ("vorgezogene") Master modules, and how far into the Bachelor's must they be before starting? | Max 30 CP total; earliest after generally acquiring 120 CP of the Bachelor's (not from the start) | Bachelor Informatik PO 2022 § 9 (eligibility: which modules) **combined with** ÜPO § 9 Abs. 1 (the 30 CP cap and 120 CP threshold — not stated in the Bachelor PO itself) | Bachelor PO p. 6; ÜPO p. 16 |
| 4 | Citation-accuracy trap / abstain-if-wrong-source | Does the Bachelor Informatik PO itself state a numeric cap on early master-module CP? | No — the Bachelor PO § 9 only lists which modules are eligible; the only "30 CP" figure in that document (§ 10 Abs. 5) is the unrelated grade-exclusion cap. The actual early-master cap is in ÜPO § 9, not the Bachelor PO. A wrong answer here is citing § 10 Abs. 5 as if it were the early-master rule. | Bachelor Informatik PO 2022 § 9 and § 10 Abs. 5 (for contrast) | 6-7 |
| 5 | Version/scope conflict | Which document governs the actual CP cap for early master modules — the program-specific PO or the ÜPO? | The ÜPO (§ 9 Abs. 1) — the program-specific Bachelor PO is silent on the numeric cap and only covers eligibility | Bachelor Informatik PO 2022 § 9 vs. ÜPO § 9 | Bachelor PO p. 6; ÜPO p. 16 |
| 6 | Unanswerable | What are the office hours of the Fachstudienberatung Informatik? | Not found in these documents — hand over to the Fachstudienberatung/examination office contact | — (none of the four collected documents cover this) | — |

## Notes for the next batch
- Question 4 and 5 both exploit the same real mistake documented in `studyrag-lessons-from-planning-session.md` P3 — worth keeping at least one "wrong document, right-looking number" trap per batch, since that's a documented real failure mode, not a hypothetical one.
- **Correction logged:** P3 in the lessons doc says the 30-CP early-master cap "appeared in neither source" (PO or study-centre page) and was treated as unverified. It's actually in ÜPO § 9 Abs. 1 — P3 should be amended to note the ÜPO specifically needs checking before calling a rule unverified, not just the program PO and the study-centre page. Not yet edited in that file — flagging here first.
- Still need: a two-passage question that pulls from the module handbook itself (none drafted yet, since the handbook's 569 pages need the real parser to navigate reliably rather than manual `pdftotext` spelunking).
- Target is 30-50 total; this is 6.
