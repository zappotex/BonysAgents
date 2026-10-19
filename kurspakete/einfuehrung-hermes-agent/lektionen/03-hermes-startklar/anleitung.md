# Hermes startklar

## 1. Agent-PC starten

Im Hauptfenster von Bony's Agents deinen Agent-PC wählen → **„Starten“** (falls er noch nicht läuft). Warte, bis
der Desktop erscheint.

## 2. Hermes öffnen

Doppelklicke im Agent-PC auf das Symbol **Hermes Agent**. Ein Terminal öffnet sich.

## 3. Hermes einrichten (nur beim ersten Mal)

Gib ein:

```
hermes setup
```

- Bei der Anbieter-Wahl den obersten Punkt **Nous** wählen und dort ein **kostenloses (free) Modell**.
- Fragt Hermes nach einer Anmeldung, meldest du dich mit deinem **eigenen** Konto an – nie mit einem fremden.
- Mit den Pfeiltasten wählst du aus, mit der Eingabetaste bestätigst du. Telegram kannst du überspringen.

*Alternative:* Anbieter **OpenRouter** und ein Modell mit `:free` im Namen (eigenes Konto bei openrouter.ai, eigener
API-Schlüssel).

## 4. Prüfen und loslegen

```
hermes doctor
hermes --tui
```

`hermes doctor` prüft die Installation. `hermes --tui` startet die übersichtliche Oberfläche (oder einfach
`hermes`). Schreib: **Hallo! Wer bist du und was kannst du?**

## Nützliche Befehle in Hermes

| Befehl | Was er tut |
|---|---|
| `/tools` | zeigt die Werkzeuge, die Hermes benutzen darf |
| `/help` | zeigt alle Befehle |
| `/model` | wechselt das Modell (im Terminal auch `hermes model`) |

::: hinweis
Kostenlose Modelle haben **Nutzungsgrenzen** und sind manchmal langsam. Kommt „Rate limit“ oder „zu viele
Anfragen“, kurz warten oder mit `/model` ein anderes kostenloses Modell wählen.
:::

Fertig? Klick auf **„Prüfen“**.
