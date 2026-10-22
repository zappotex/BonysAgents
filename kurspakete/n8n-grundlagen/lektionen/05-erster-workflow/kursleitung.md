**Ablauf:** 8 Minuten vorführen (Schritt für Schritt, Teilnehmer bauen mit), 12 Minuten fertig bauen, 5 Minuten
Puffer.

- Den **Token nicht zeigen**: Beim Anlegen der Credential das geteilte Fenster kurz anhalten oder vorher eine
  Credential anlegen und nur auswählen.
- **„Fetch Test Event“** holt den neuesten Artikel – so sehen alle sofort Daten, mit denen sie das Feld Text füllen
  können.
- Feld **Text**: Ziehen (Drag & Drop) aus der linken Spalte ist am einfachsten. Wer tippt, muss das Feld auf
  **Expression** umstellen, sonst steht `{{ $json.title }}` wörtlich in der Nachricht.
- Telegram-Fehler „chat not found“: Chat-ID falsch oder dem Bot noch nie geschrieben. „Unauthorized“: Token falsch
  kopiert.
- Nach **„Publish“** prüft n8n jede Stunde. Neue Artikel kommen also nicht sofort – das ist richtig so. Zum
  Vorführen „Every Minute“ wählen und danach wieder zurückstellen.
- Unten in jeder Nachricht steht „This message was sent automatically with n8n“ – abschalten in Lektion 6.
- Die Prüfung liest aus der Datenbank von n8n nur, ob ein **veröffentlichter** Workflow die Knoten-Typen
  „RSS Feed Trigger“ und „Telegram“ enthält – keine Zugangsdaten.
