# Databricks notebook source
# MAGIC %md
# MAGIC # Genie Stability Score - grading and summary
# MAGIC Compares each raw Genie answer with the reference SQL query, then computes accuracy
# MAGIC and consistency per space, per question family and per language.
# MAGIC
# MAGIC This notebook asks Genie **nothing**: it can be re-run as often as needed.
# MAGIC
# MAGIC **Outcomes:** `correct`, `partial` (right figures, wrong level of detail), `incorrect`,
# MAGIC `trap_hit` (Genie took the anticipated wrong interpretation), `needs_review` (human check needed),
# MAGIC `no_answer` (no SQL: clarification request, error or timeout).

# COMMAND ----------

RESULTS_TABLE = "bramblepeak_retail.genie_study.raw_runs"
GRADED_TABLE = "bramblepeak_retail.genie_study.graded"
RUN_LABEL = "run1"
QUESTIONS_FILE = "genie_stability_questions.json"   # in the same folder as this notebook

# COMMAND ----------

import json, os
from decimal import Decimal
import pandas as pd

path = QUESTIONS_FILE if os.path.isabs(QUESTIONS_FILE) else os.path.join(os.getcwd(), QUESTIONS_FILE)
with open(path, encoding="utf-8") as fh:
    QS = json.load(fh)
TOL_AMOUNT = QS["meta"]["tolerance"]["amount_relative"]
TOL_PCT = QS["meta"]["tolerance"]["percent_absolute"]


def to_py(v):
    if isinstance(v, bool):
        return v
    return float(v) if isinstance(v, (Decimal, int, float)) else v


def run_sql(sql):
    if not sql:
        return None
    return [{k: to_py(v) for k, v in r.asDict().items()} for r in spark.sql(sql).collect()]


FAM = {}
for f in QS["families"]:
    FAM[f["id"]] = {"compare": f["compare"],
                    "expected": run_sql(f["reference_sql"]),
                    "trap": run_sql(f.get("trap_sql")),
                    "partial": run_sql(f.get("partial_sql"))}
    print(f["id"], "| expected:", FAM[f["id"]]["expected"], "| trap:", FAM[f["id"]]["trap"])

# COMMAND ----------

def num(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def norm(x):
    return str(x).strip().lower() if x is not None else None


def is_pct(col):
    return "pct" in col or "percent" in col


def close(v, e, pct=False):
    if v is None or e is None:
        return False
    if pct:  # accepts 53.6 and 0.536 alike
        return abs(v - e) <= TOL_PCT or abs(v * 100 - e) <= TOL_PCT
    return abs(v - e) <= max(TOL_AMOUNT * abs(e), 0.01)


def numbers(rows):
    return [n for r in rows for n in (num(c) for c in r) if n is not None]


def any_close(rows, e, pct=False):
    return any(close(v, e, pct) for v in numbers(rows))


def grade(fam_id, status, sql, rows):
    outcome, detail = _grade(fam_id, status, sql, rows)
    if status != "COMPLETED" and outcome != "no_answer":
        detail = f"[status {status}, graded on content] " + detail
    return outcome, detail


def _grade(fam_id, status, sql, rows):
    spec = FAM[fam_id]["compare"]
    exp, trap, t = FAM[fam_id]["expected"], FAM[fam_id]["trap"], spec["type"]
    partial = FAM[fam_id].get("partial")

    if not sql or rows is None:
        return "no_answer", "no SQL result (clarification, error or timeout)"
    if t == "label_set" and not exp:
        return ("correct", "no value expected, empty result") if not rows else ("needs_review", "empty result expected")
    if not rows:
        return "incorrect", "empty result"

    if t == "scalar":
        col = spec["column"]
        e, pct = exp[0][col], spec.get("kind") == "pct" or is_pct(col)
        if len(rows) > 1:
            return "needs_review", f"{len(rows)} rows instead of a single value"
        if any_close(rows, e, pct):
            return "correct", f"expected value {e} found"
        if trap and any_close(rows, trap[0][col], pct):
            return "trap_hit", f"trap value {trap[0][col]} found"
        return "incorrect", f"expected {e}, got {numbers(rows)[:5]}"

    if t == "values_present":
        for group in spec["match_any_of"]:
            if all(any_close(rows, exp[0][c], is_pct(c)) for c in group):
                return "correct", f"values {group} found"
        pc = spec.get("partial_column")
        if partial and pc and all(any_close(rows, r[pc]) for r in partial):
            return "partial", "right detailed figures, but no answer at the requested level"
        if len(rows) > 1:
            return "needs_review", f"{len(rows)} rows, expected totals missing"
        return "incorrect", "expected values missing"

    if t == "label_set":
        col = spec["column"]
        expected = {norm(r[col]) for r in exp}
        best = set()
        for j in range(len(rows[0])):
            vals = {norm(r[j]) for r in rows if r[j] is not None}
            if len(vals & expected) > len(best & expected):
                best = vals
        if not (best & expected):
            return "incorrect", "no expected label found"
        if best == expected:
            return "correct", "identical set"
        if expected < best:
            marks = [m.lower() for m in spec.get("superset_ok_if_marked", [])]
            extra = best - expected
            extra_rows = [r for r in rows if {norm(c) for c in r} & extra]
            if marks and extra_rows and all(any(norm(c) in marks for c in r) for r in extra_rows):
                return "correct", "complete list, extra labels are explicitly marked as on track"
            return "incorrect", f"extra labels: {sorted(extra)}"
        return "incorrect", f"missing: {sorted(expected - best)}; extra: {sorted(best - expected)}"

    if t == "label_value_map":
        lab, valc, misses = spec["label"], spec["value"], []
        for r_exp in exp:
            target, e = norm(r_exp[lab]), r_exp[valc]
            match_rows = [r for r in rows if target in {norm(c) for c in r}]
            if not match_rows:
                misses.append(f"{r_exp[lab]} missing")
            elif not any_close(match_rows, e, is_pct(valc)):
                misses.append(f"{r_exp[lab]}: expected {e}")
        return ("correct", "all pairs found") if not misses else ("incorrect", "; ".join(misses))

    if t == "top_label_and_value":
        lab, valc, first = spec["label"], spec["value"], rows[0]
        labels = {norm(c) for c in first}
        if norm(exp[0][lab]) in labels and any_close([first], exp[0][valc]):
            return "correct", "right label and right amount"
        if trap and norm(trap[0][lab]) in labels and any_close([first], trap[0][valc]):
            return "trap_hit", "amount of the trap interpretation"
        if norm(exp[0][lab]) in labels:
            return "needs_review", "right label, amount not recognised"
        return "incorrect", f"first row: {first}"

    return "needs_review", f"unknown comparison type: {t}"

# COMMAND ----------

raw = spark.sql(f"""
  SELECT * FROM (
    SELECT *, ROW_NUMBER() OVER (PARTITION BY space_label, variant_id, repeat_idx ORDER BY asked_at DESC) AS rn
    FROM {RESULTS_TABLE} WHERE run_label = '{RUN_LABEL}'
  ) WHERE rn = 1
""").toPandas()

records = []
for _, r in raw.iterrows():
    rows = json.loads(r["rows_json"]) if r["rows_json"] else None
    outcome, detail = grade(r["family_id"], r["status"], r["sql"], rows)
    records.append({"run_label": RUN_LABEL, "space_label": r["space_label"], "family_id": r["family_id"],
                    "variant_id": r["variant_id"], "lang": r["lang"], "repeat_idx": int(r["repeat_idx"]),
                    "question": r["question"], "outcome": outcome, "detail": detail, "sql": r["sql"]})

graded = pd.DataFrame(records)
graded["variant_set"] = graded.variant_id.str.contains(r"-H(?:EN|FR)\d+$", regex=True).map({True: "holdout", False: "main"})
spark.createDataFrame(
    graded,
    schema="run_label string, space_label string, family_id string, variant_id string, lang string, "
           "repeat_idx int, question string, outcome string, detail string, sql string, variant_set string",
).write.mode("overwrite").option("overwriteSchema", "true").saveAsTable(GRADED_TABLE)
print(f"{len(graded)} answers graded.")
display(graded.groupby(["space_label", "outcome"]).size().reset_index(name="count"))

# COMMAND ----------

# MAGIC %md
# MAGIC ## Summary per space and per question family
# MAGIC - **accuracy**: share of correct phrasings (control repetitions excluded).
# MAGIC - **consistency**: share of phrasings giving the majority outcome. 100% = always right
# MAGIC   or always wrong; 50% = a coin flip depending on phrasing.

# COMMAND ----------

main = graded[(graded.repeat_idx == 0) & (graded.variant_set == "main")]


def pct_correct(s):
    return round(100 * (s == "correct").mean(), 1) if len(s) else None


rows_fam = []
for (space, fam), g in main.groupby(["space_label", "family_id"]):
    share = (g.outcome == "correct").mean()
    rows_fam.append({
        "space": space, "family": fam, "n": len(g),
        "accuracy_%": pct_correct(g.outcome),
        "accuracy_EN_%": pct_correct(g[g.lang == "en"].outcome),
        "accuracy_FR_%": pct_correct(g[g.lang == "fr"].outcome),
        "consistency_%": round(100 * max(share, 1 - share), 1),
        "partial": int((g.outcome == "partial").sum()),
        "trap_hit": int((g.outcome == "trap_hit").sum()),
        "needs_review": int((g.outcome == "needs_review").sum()),
        "no_answer": int((g.outcome == "no_answer").sum()),
    })
by_family = pd.DataFrame(rows_fam)
display(by_family)

rows_space = []
for space, g in main.groupby("space_label"):
    fams = by_family[by_family.space == space]
    rows_space.append({
        "space": space, "n": len(g),
        "accuracy_%": pct_correct(g.outcome),
        "accuracy_EN_%": pct_correct(g[g.lang == "en"].outcome),
        "accuracy_FR_%": pct_correct(g[g.lang == "fr"].outcome),
        "families_all_correct": int((fams["accuracy_%"] == 100).sum()),
        "families_tested": len(fams),
    })
display(pd.DataFrame(rows_space))

# COMMAND ----------

# MAGIC %md
# MAGIC ## Randomness control: the exact same sentence, asked several times

# COMMAND ----------

ctrl = graded[(graded.variant_set == "main") & graded.variant_id.str.contains(r"(?:EN1|FR1)$", regex=True)]
control = (ctrl.groupby(["space_label", "variant_id"])
               .agg(repetitions=("outcome", "size"),
                    outcomes=("outcome", lambda s: ", ".join(s)),
                    identical=("outcome", lambda s: s.nunique() == 1))
               .reset_index())
display(control)

# COMMAND ----------

# MAGIC %md
# MAGIC ## Held-out phrasings: does the fix generalise?
# MAGIC Phrasings written after the diagnosis, never used to build spaces C and D.

# COMMAND ----------

hold = graded[(graded.repeat_idx == 0) & (graded.variant_set == "holdout")]
if len(hold):
    display(hold.pivot_table(index=["family_id", "variant_id", "question"], columns="space_label",
                             values="outcome", aggfunc="first").reset_index())
    display(hold.groupby(["space_label", "family_id"])
                .apply(lambda g: pd.Series({"n": len(g), "correct": int((g.outcome == "correct").sum())}))
                .reset_index())
else:
    print("No held-out answers yet.")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Answers to review (everything that is not correct)

# COMMAND ----------

display(graded[graded.outcome != "correct"][["space_label", "variant_id", "question", "outcome", "detail", "sql"]])
