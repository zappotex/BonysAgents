# Saving and wrap-up

## 1. Save the workflow as a file

Open your workflow, click **"…"** at the top right and choose **"Export JSON"**. The file lands in your Agent PC's
**Downloads** folder.

With this file you can take the workflow into another n8n: there **"…"** → **"Import"** → **"From file"**.

::: hinweis
The file contains **no token** – only the name of the credential. After an import you enter the credentials again.
:::

Done? Click **"Check"**.

## 2. Where n8n stores its data

Your workflows are kept in their own storage in the Agent PC (Docker volume `n8n_data`). They survive n8n updates.
**Templates** you pass on do **not** contain n8n and its data (license) – that's why the exported file is the way to
pass on a workflow.

## 3. What you learned today

- triggers, nodes, connections and executions
- creating a Telegram bot – and treating the token like a password
- testing (**Fetch Test Event**, **Execute step**), saving, **publishing**
- saving with **Export JSON**

## How to continue

- **Hermes and n8n as a team:** Hermes summarizes articles before n8n sends them – and starts workflows on request.
- The **User Guide**, chapter "n8n", and the documentation at docs.n8n.io.

Finally: the **quiz**.
