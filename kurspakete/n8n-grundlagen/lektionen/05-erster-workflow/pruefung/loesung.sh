#!/bin/bash
# Lösung – läuft nur bei „Kurspaket prüfen“ im Editor, nie bei Teilnehmern (als root).
# Importiert den Workflow „RSS → Telegram“ ohne Zugangsdaten über die Kommandozeile von n8n und veröffentlicht ihn.
set -e
cat > /tmp/kurs-workflow.json <<'EOF'
[{"id": "kursRssTelegram1", "name": "Nachrichten per Telegram", "active": false, "settings": {},
  "nodes": [
    {"id": "6b0c1a52-0000-4000-8000-000000000001", "name": "RSS Feed Trigger", "type": "n8n-nodes-base.rssFeedReadTrigger",
     "typeVersion": 1, "position": [0, 0],
     "parameters": {"pollTimes": {"item": [{"mode": "everyHour"}]}, "feedUrl": "https://www.tagesschau.de/index~rss2.xml"}},
    {"id": "6b0c1a52-0000-4000-8000-000000000002", "name": "Send a text message", "type": "n8n-nodes-base.telegram",
     "typeVersion": 1.2, "position": [220, 0],
     "parameters": {"chatId": "123456789", "text": "={{ $json.title }}\n{{ $json.link }}"}}],
  "connections": {"RSS Feed Trigger": {"main": [[{"node": "Send a text message", "type": "main", "index": 0}]]}}}]
EOF
docker cp /tmp/kurs-workflow.json n8n:/tmp/kurs-workflow.json
docker exec n8n n8n import:workflow --input=/tmp/kurs-workflow.json >/dev/null
docker exec n8n n8n publish:workflow --id=kursRssTelegram1 >/dev/null
docker restart n8n >/dev/null
rm -f /tmp/kurs-workflow.json
