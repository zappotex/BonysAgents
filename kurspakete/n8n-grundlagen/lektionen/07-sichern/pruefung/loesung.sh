#!/bin/bash
# Lösung – läuft nur bei „Kurspaket prüfen“ im Editor, nie bei Teilnehmern
ordner=$(xdg-user-dir DOWNLOAD 2>/dev/null || echo "$HOME/Downloads")
mkdir -p "$ordner"
cat > "$ordner/Nachrichten_per_Telegram.json" <<'EOF'
{"name": "Nachrichten per Telegram",
 "nodes": [{"name": "RSS Feed Trigger", "type": "n8n-nodes-base.rssFeedReadTrigger", "typeVersion": 1,
            "position": [0, 0], "parameters": {"feedUrl": "https://www.tagesschau.de/index~rss2.xml"}},
           {"name": "Send a text message", "type": "n8n-nodes-base.telegram", "typeVersion": 1.2,
            "position": [220, 0], "parameters": {"chatId": "123456789", "text": "={{ $json.title }}"}}],
 "connections": {"RSS Feed Trigger": {"main": [[{"node": "Send a text message", "type": "main", "index": 0}]]}}}
EOF
