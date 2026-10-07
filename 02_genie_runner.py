# Databricks notebook source
# MAGIC %md
# MAGIC # Genie Stability Score - answer collection
# MAGIC Asks every phrasing in the question file to every Genie space and stores the raw answers
# MAGIC (generated SQL, result, text) in a Delta table.
# MAGIC
# MAGIC Grading happens in a separate notebook: if a grading rule changes, there is no need to ask
# MAGIC Genie again (about 20 s per question).
# MAGIC
# MAGIC **Automatic resume:** if the run stops, run it again. Questions already answered are skipped.

# COMMAND ----------

# ---------- CONFIGURATION ----------
# One entry per Genie space: label -> space ID
SPACES = {
    "A_tables_only": "<SPACE_ID_A>",
    "B_configured": "<SPACE_ID_B>",
    "C_definitions": "<SPACE_ID_C>",
    "D_fixed_rule": "<SPACE_ID_D>",
}
QUESTIONS_FILE = "genie_stability_questions.json"   # in the same folder as this notebook
RESULTS_TABLE = "bramblepeak_retail.genie_study.raw_runs"
RUN_LABEL = "run1"

# Randomness control: extra repetitions of the EN1 and FR1 phrasings (same sentence, asked several times)
CONTROL_REPEATS = 2

# Filters: None = everything. Questions already answered are skipped automatically.
FAMILY_FILTER = None
SPACE_FILTER = None

PAUSE_BETWEEN_QUESTIONS_S = 5

# COMMAND ----------

import json, os, time, datetime
from databricks.sdk import WorkspaceClient

w = WorkspaceClient()  # automatic authentication inside a Databricks notebook
TERMINAL = {"COMPLETED", "FAILED", "CANCELLED", "QUERY_RESULT_EXPIRED"}
TRANSIENT_MARKERS = ("429", "RESOURCE_EXHAUSTED", "Too Many", "TEMPORARILY_UNAVAILABLE", "503")


def _call(method, path, body=None, retries=4):
    """API call, retried with backoff when the rate limit is reached."""
    delay = 30
    for attempt in range(retries + 1):
        try:
            if body is None:
                return w.api_client.do(method, path)
            return w.api_client.do(method, path, body=body)
        except Exception as e:
            if any(m in str(e) for m in TRANSIENT_MARKERS) and attempt < retries:
                print(f"   rate limit reached, retrying in {delay} s...")
                time.sleep(delay)
                delay *= 2
            else:
                raise


def ask_genie(space_id, question, timeout_s=300):
    """Asks one question in a NEW conversation and returns the raw answer."""
    base = f"/api/2.0/genie/spaces/{space_id}"
    t0 = time.time()
    out = {"status": None, "sql": None, "columns_json": None, "rows_json": None,
           "text": None, "error": None, "conversation_id": None}
    try:
        start = _call("POST", f"{base}/start-conversation", {"content": question})
        conv_id = start.get("conversation_id") or start["conversation"]["id"]
        msg_id = start.get("message_id") or start["message"]["id"]
        out["conversation_id"] = conv_id

        msg = {}
        while time.time() - t0 < timeout_s:
            msg = _call("GET", f"{base}/conversations/{conv_id}/messages/{msg_id}")
            if msg.get("status") in TERMINAL:
                break
            time.sleep(3)
        status = msg.get("status")
        out["status"] = status if status in TERMINAL else "TIMEOUT"
        if msg.get("error"):
            out["error"] = json.dumps(msg["error"])[:2000]

        texts = []
        for att in msg.get("attachments") or []:
            if att.get("text"):
                texts.append(att["text"].get("content") or "")
            if att.get("query") and out["sql"] is None:
                out["sql"] = att["query"].get("query")
                res = _call("GET", f"{base}/conversations/{conv_id}/messages/{msg_id}"
                                   f"/query-result/{att['attachment_id']}")
                sr = res.get("statement_response", {})
                cols = [c.get("name") for c in sr.get("manifest", {}).get("schema", {}).get("columns", [])]
                out["columns_json"] = json.dumps(cols)
                out["rows_json"] = json.dumps(sr.get("result", {}).get("data_array") or [])
        out["text"] = "\n".join(texts) if texts else None
    except Exception as e:
        out["status"] = out["status"] or "ERROR"
        out["error"] = str(e)[:2000]
    out["latency_s"] = round(time.time() - t0, 1)
    return out

# COMMAND ----------

path = QUESTIONS_FILE if os.path.isabs(QUESTIONS_FILE) else os.path.join(os.getcwd(), QUESTIONS_FILE)
if not os.path.exists(path):
    raise FileNotFoundError(
        f"File not found: {path}. Import genie_stability_questions.json into the same folder "
        "as this notebook, or set its full path in QUESTIONS_FILE (e.g. /Workspace/Users/<email>/...)."
    )
with open(path, encoding="utf-8") as fh:
    QS = json.load(fh)

spark.sql("CREATE SCHEMA IF NOT EXISTS bramblepeak_retail.genie_study")

done = set()
if spark.catalog.tableExists(RESULTS_TABLE):
    for r in spark.sql(
        f"SELECT space_label, variant_id, repeat_idx FROM {RESULTS_TABLE} "
        f"WHERE run_label = '{RUN_LABEL}' AND status = 'COMPLETED'"
    ).collect():
        done.add((r.space_label, r.variant_id, r.repeat_idx))

tasks = []
for space_label, space_id in SPACES.items():
    if SPACE_FILTER and space_label not in SPACE_FILTER:
        continue
    if not space_id or space_id.startswith("<"):
        print(f"Space {space_label} skipped: missing ID.")
        continue
    for fam in QS["families"]:
        if FAMILY_FILTER and fam["id"] not in FAMILY_FILTER:
            continue
        for v in fam["variants"]:
            is_control = v.get("set", "main") == "main" and v["id"].endswith(("EN1", "FR1"))
            reps = 1 + (CONTROL_REPEATS if is_control else 0)
            for rep in range(reps):
                if (space_label, v["id"], rep) not in done:
                    tasks.append((space_label, space_id, fam["id"], v, rep))

print(f"{len(tasks)} questions to ask ({len(done)} already done), "
      f"about {len(tasks) * 25 / 60:.0f} minutes.")

# COMMAND ----------

SCHEMA = ("run_label string, space_label string, space_id string, family_id string, variant_id string, "
          "lang string, repeat_idx int, question string, status string, sql string, columns_json string, "
          "rows_json string, text string, error string, latency_s double, conversation_id string, "
          "asked_at timestamp")

for i, (space_label, space_id, fam_id, v, rep) in enumerate(tasks, 1):
    r = ask_genie(space_id, v["text"])
    row = (RUN_LABEL, space_label, space_id, fam_id, v["id"], v["lang"], rep, v["text"],
           r["status"], r["sql"], r["columns_json"], r["rows_json"], r["text"], r["error"],
           float(r["latency_s"]), r["conversation_id"], datetime.datetime.now())
    spark.createDataFrame([row], SCHEMA).write.mode("append").saveAsTable(RESULTS_TABLE)
    print(f"[{i}/{len(tasks)}] {space_label} {v['id']} rep{rep} -> {r['status']} ({r['latency_s']} s)")
    time.sleep(PAUSE_BETWEEN_QUESTIONS_S)

print("Done.")

# COMMAND ----------

display(spark.sql(
    f"SELECT space_label, variant_id, repeat_idx, question, status, rows_json, latency_s "
    f"FROM {RESULTS_TABLE} WHERE run_label = '{RUN_LABEL}' ORDER BY asked_at DESC"
))
