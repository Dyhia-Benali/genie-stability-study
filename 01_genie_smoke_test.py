# Databricks notebook source
# MAGIC %md
# MAGIC # Genie Stability Score - connection test
# MAGIC Sends ONE question to a Genie space through the Genie Conversation API, then prints the generated SQL and the result.
# MAGIC
# MAGIC **Before running:** replace `SPACE_ID` with your space ID
# MAGIC (the characters after `/genie/rooms/` in the space URL, without the `?o=...` part).

# COMMAND ----------

import time
from databricks.sdk import WorkspaceClient

SPACE_ID = "<SPACE_ID_A>"
QUESTION = "What was our total revenue last month?"

w = WorkspaceClient()  # automatic authentication inside a Databricks notebook, no token needed
base = f"/api/2.0/genie/spaces/{SPACE_ID}"

start = w.api_client.do("POST", f"{base}/start-conversation", body={"content": QUESTION})
conv_id = start.get("conversation_id") or start["conversation"]["id"]
msg_id = start.get("message_id") or start["message"]["id"]

msg = {}
for _ in range(60):  # waits up to about 3 minutes
    msg = w.api_client.do("GET", f"{base}/conversations/{conv_id}/messages/{msg_id}")
    if msg.get("status") in ("COMPLETED", "FAILED", "CANCELLED", "QUERY_RESULT_EXPIRED"):
        break
    time.sleep(3)

print("Status:", msg.get("status"))
if msg.get("error"):
    print("Error:", msg["error"])

for att in msg.get("attachments") or []:
    if att.get("text"):
        print("Text:", att["text"].get("content"))
    if att.get("query"):
        print("Generated SQL:\n", att["query"].get("query"))
        res = w.api_client.do(
            "GET", f"{base}/conversations/{conv_id}/messages/{msg_id}/query-result/{att['attachment_id']}"
        )
        rows = res.get("statement_response", {}).get("result", {}).get("data_array")
        print("Result:", rows)
