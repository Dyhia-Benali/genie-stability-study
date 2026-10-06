# Genie Stability Score

Business useres never phrase a question the same way twice:
"revenue last month", "CA M-1", "how did sales land in septembre". If Genie answers one phrasing tight and another wrong, 
users cannot tell witch answer to trust. The lab's benchmark checks one phrasing per question; I wented to know whether
the answer stays the same when the question changes, and what it takes to make it stable.

## In short

- 8 business questions, 10 phrasings each (English and French), asked through the Genie API to four configurations of the same space: 480 answers graded against reference SQL.
- Configuration took accuracy from 68% to 96%. Writing down the missing business definitions took it to 99%: no wrong number left, one generated query failed to run.
- One of my fixes made a hidden bug more frequent: Genie understood "last month" but returned this month's revenue. A full re-run caught it, and the root cause was the date table's grain.

## Relation to the lab

The lab already teaches the core loop: a 10-question benchmark scored against ground-truth SQL
(`02_Benchmarks.md`), then generate, read the SQL, tune the smallest surface, re-run (`03_Test_Workflows.md`).
This exercise reuses that loop and adds what the lab's guides do not cover:

- **10 phrasings per question** instead of one, including French business shorthand.
- **The same sentence asked 3 times**, to separate randomness from phrasing effects.
- **An unconfigured baseline (space A)**, to see what configuration actually changes.
- **Automation through the Genie Conversation API**: 120 questions per space, graded by code and reproducible.
- **Held-out phrasings and a full re-run after every fix**, which is how the regression in space C was caught.

## Setup

- **Data:** the Bramblepeak retail star schema from Jakub Lasak's lab
  ([databricks-code-practice](https://github.com/jrlasak/databricks-code-practice), "Build a Genie Space"), on Databricks Free Edition.
- **Four Genie spaces, same 7 tables:**
  - **A**: tables only, no Genie configuration (Unity Catalog table comments only).
  - **B**: configured as in the lab: general instructions, 4 joins, 5 measures + 1 filter, 8 example queries, 3 UC functions. English synonyms only. See `space_B_definitions.md`.
  - **C**: B + business definitions written after diagnosing A and B ("CA" / "M-1", calendar quarters, product = SKU, discounted revenue share). See `space_C_definitions.md`.
  - **D**: C with the month rule rewritten after C regressed. See `space_D_definitions.md`.
- **Questions:** 8 business question families x 10 phrasings (5 EN, 5 FR) in `genie_stability_questions.json`, each with a reference SQL query.
  The first EN and FR phrasing of each family is asked 3 times to separate randomness from phrasing effects.
  8 extra phrasings (F5 and F8), written after the diagnosis and never used to build C or D, check whether the fixes generalise.

## Results

| | A · tables only | B · configured | C · + definitions | D · + fixed month rule |
|---|---|---|---|---|
| Correct answers (80 phrasings) | 54 (67.5%) | 77 (96.2%) | 78 (97.5%) | 79 (98.8%) |
| Families right in all 10 phrasings | 2/8 | 6/8 | 7/8 | 7/8 |
| New phrasings (8, held out) | 5/8 | 5/8 | 6/8 | 8/8 |
| Same sentence asked 3 times, different answer | 2/16 | 0/16 | 0/16 | 0/16 |

D's only miss is a query that failed to execute: Genie's logic was right (it took distinct months, as the new rule says), but it wrote a row-value comparison that Databricks SQL rejected. The user would see an error, not a wrong number.

**One root cause behind most remaining errors: "the previous period" computed on a table with one row per day.**
`dim_date` has one row per day. To find "last month" or "last quarter", Genie sometimes sorted it and took the second row
(`ORDER BY ... LIMIT 1 OFFSET 1`), which is another day of the *current* period. The query runs, and silently returns this
month's or this quarter's figure.

- Space B already did it once for "last month" (on a held-out phrasing) and twice for "last quarter" (52.6% = the current quarter).
- Space C did it on 3 "last month" phrasings, including "CA M-1?", which B had answered by asking for clarification.
  The definitions I added fixed "last quarter" but made this pattern more frequent for "last month".
- Space D states the table grain and the exact pattern in the instructions: all 18 "last month" answers and all held-out
  phrasings correct, and the same distinct-period logic now also used for quarters.

Genie rarely fails random: it fails where a business definition, or a property of data was never written down. Writing them down is a business job more than a technical one. And every change must be re-tested on all questions: my first round of defintions fixed one question and made another one worse.

## Examples

Asked "CA M-1?" (French shorthand for last month's revenue), the unconfigured space answered with a Cascade lantern and two customers named Lucas and Carlos. The configured space asked what I meant. Once I defined the term, it understood the question but returned this month's figure. Once the rule also described the date table, it returned the right number. Details in examples/ca_m-1.md.

## Limits

- Synthetic data, a single run per space.
- All phrasings, definitions and held-out questions written by me with an AI assistant, not collected from real business users.
- 8 held-out phrasings is encouraging, not statistical proof.

## How to reproduce

1. Run the lab's `00_Run_All` notebook to create the data.
2. Create the Genie spaces and note their IDs (A, B as in the lab, C and D from the definition files).
3. `01_genie_smoke_test.py`: sends one question through the Genie Conversation API to check access.
4. `02_genie_runner.py`: asks every phrasing to each space, one new conversation per question, and stores raw answers in a Delta table. Resumes automatically if interrupted.
5. `03_genie_grading.py`: compares each answer with the reference query and computes accuracy and consistency per space, family and language, plus the held-out results.

Replace `<SPACE_ID_A>` ... `<SPACE_ID_D>` with your own space IDs.

## Credits

- Data and Genie configuration of space B: Jakub Lasak's lab ([link above](https://github.com/jrlasak/databricks-code-practice)).
- Related research: Gan et al., *Towards Robustness of Text-to-SQL Models against Synonym Substitution* (Spider-Syn), ACL 2021.
- The test approach comes from how I run regression testing across environments at Renault (dev, test, pre-prod, prod): compare each configuration with the previous one and re-run everything after every change. 
- I used an AI assistant (Claude) under my direction, mainly to write the technical code and the repetitive parts (notebooks, phrasing variants, reference SQL), and to refine protocol details such as repeated questions and held-out phrasings. I set up the four Genie spaces, ran every step, validated the reference queries, checked each surprising answer in SQL, and decided what to test next. 
