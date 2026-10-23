# AI Experiment — Grounded vs. Ungrounded

**Question:** If a sales executive asks an AI assistant about the pipeline, does the answer depend on the
business logic behind the data?

**Method:** Ask a free AI assistant the same five questions twice, then compare both answers with the
Power BI dashboard (the reconciled "ground truth").

## Setup
- Tool used: ______________________ (e.g. Claude, ChatGPT, Gemini — free tier) · Date: __________
- Start a **new chat** for each round so the AI can't carry context between them.
- Round A file: `data/output/ai/raw_union_uncleaned.csv` (the 24 CRM extracts stacked, not cleaned).
- Round B files: `data/output/ai/pipeline_deals_for_ai.csv` + `docs/business_definitions.md`.
- Data is synthetic, so it is safe to upload.

## The five questions (copy-paste exactly)
```
Q1. How many unique sales opportunities are in this data?
Q2. What is the total value of open pipeline in EUR?
Q3. What is the weighted pipeline in EUR?
Q4. What was our win rate for deals closed in the last 12 months (as of 15 Sep 2026)?
Q5. Which department has the most open pipeline value stuck beyond its stage threshold?
```

## Round A — Ungrounded prompt
```
You are a sales operations analyst. Attached is our CRM opportunity export.
Answer these five questions with a single number or name each, and show how you calculated it.
[paste Q1–Q5]
```

## Round B — Grounded prompt
```
You are a sales operations analyst. Attached are (1) our cleaned, reconciled pipeline table and
(2) our official business definitions. Use ONLY these definitions — do not invent your own rules.
If a question can't be answered with the definitions, say so.
Answer these five questions with a single number or name each, and cite the definition you used.
[paste Q1–Q5]
```

## Round C — Narrative with human verification
```
Using the same files and definitions, write a 5-bullet Monday pipeline summary for our Chief Revenue
Officer: what's healthy, what's at risk, and one recommended action. Include numbers.
```
Then verify every number/claim in Power BI and fill in the validation log.

## Results

| Q | Dashboard ground truth | Round A answer | Round A error | Round B answer | Round B error | What went wrong in Round A |
|---|---|---|---|---|---|---|
| Q1 | 4,800 | | | | | *e.g. counted rows, not unique IDs; didn't remove duplicates or test records* |
| Q2 | € | | | | | *e.g. added GBP/SEK amounts as if EUR; included outliers* |
| Q3 | € | | | | | *e.g. used rep-typed probabilities; mixed 0.75 and 75* |
| Q4 | % | | | | | *e.g. stage spellings not grouped; open deals in denominator* |
| Q5 | | | | | | *e.g. no stage entry dates in the export* |

**Score:** Round A ___ / 5 within 2% · Round B ___ / 5 within 2%

## Round C validation log
| # | Claim made by the AI | Dashboard value | Correct? | Note |
|---|---|---|---|---|
| 1 | | | | |
| 2 | | | | |
| 3 | | | | |
| 4 | | | | |
| 5 | | | | |

## Conclusion (write 3–4 sentences in your own words)
> *Example direction: the model wasn't the problem — the missing business context was. Once the AI was given
> governed definitions and reconciled data, it answered correctly and explained itself. The analyst's value
> moved from "producing the number" to "defining, proving and governing the number".*
