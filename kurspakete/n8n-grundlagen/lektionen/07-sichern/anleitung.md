# Sichern und Abschluss

## 1. Workflow als Datei sichern

Öffne deinen Workflow, klick oben rechts auf **„…“** und wähle **„Export JSON“**. Die Datei landet im Ordner
**Downloads** deines Agent-PCs.

Mit dieser Datei kannst du den Workflow in ein anderes n8n übernehmen: dort **„…“** → **„Import“** →
**„From file“**.

::: hinweis
Die Datei enthält **keinen Token** – nur den Namen der Zugangsdaten. Nach einem Import trägst du die Zugangsdaten
neu ein.
:::

Fertig? Klick auf **„Prüfen“**.

## 2. Wo n8n seine Daten speichert

Deine Workflows liegen in einem eigenen Speicher im Agent-PC (Docker-Volume `n8n_data`). Sie überstehen Updates von
n8n. Weitergegebene **Vorlagen** enthalten n8n und seine Daten **nicht** (Lizenz) – deshalb ist die exportierte
Datei der Weg, einen Workflow weiterzugeben.

## 3. Was du heute gelernt hast

- Auslöser, Knoten, Verbindungen und Ausführungen
- einen Telegram-Bot anlegen – und den Token wie ein Passwort behandeln
- testen (**Fetch Test Event**, **Execute step**), speichern, **veröffentlichen**
- sichern mit **Export JSON**

## Wie es weitergeht

- **Hermes und n8n im Team:** Hermes fasst Artikel zusammen, bevor n8n sie schickt – und startet Workflows auf
  Zuruf.
- Das **Benutzerhandbuch**, Kapitel „n8n“, und die Dokumentation unter docs.n8n.io.

Zum Schluss: das **Quiz**.
