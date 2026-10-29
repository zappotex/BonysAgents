#!/bin/bash
# Solution – only runs with "Check course package" in the editor, never for participants
ordner=$(xdg-user-dir DOWNLOAD 2>/dev/null || echo "$HOME/Downloads")
mkdir -p "$ordner"
cat > "$ordner/News_via_Telegram.json" <<'EOF'
{"name": "News via Telegram",
 "nodes": [{"name": "RSS Feed Trigger", "type": "n8n-nodes-base.rssFeedReadTrigger", "typeVersion": 1,
            "position": [0, 0], "parameters": {"feedUrl": "https://feeds.bbci.co.uk/news/rss.xml"}},
           {"name": "Send a text message", "type": "n8n-nodes-base.telegram", "typeVersion": 1.2,
            "position": [220, 0], "parameters": {"chatId": "123456789", "text": "={{ $json.title }}"}}],
 "connections": {"RSS Feed Trigger": {"main": [[{"node": "Send a text message", "type": "main", "index": 0}]]}}}
EOF
