# Hermes ready to go

## 1. Start the Agent PC

In the main window of Bony's Agents, choose your Agent PC → **"Start"** (if it isn't running yet). Wait until the
desktop appears.

## 2. Open Hermes

In the Agent PC, double-click the **Hermes Agent** icon. A terminal opens.

## 3. Set up Hermes (only the first time)

Type:

```
hermes setup
```

- When choosing the provider, pick the top entry **Nous** and a **free model** there.
- If Hermes asks you to sign in, sign in with your **own** account – never with someone else's.
- Select with the arrow keys, confirm with Enter. You can skip Telegram.

*Alternative:* provider **OpenRouter** and a model with `:free` in its name (your own account at openrouter.ai, your
own API key).

## 4. Check and get going

```
hermes doctor
hermes --tui
```

`hermes doctor` checks the installation. `hermes --tui` starts the clearer interface (or simply `hermes`). Write:
**Hello! Who are you and what can you do?**

## Useful commands in Hermes

| Command | What it does |
|---|---|
| `/tools` | shows the tools Hermes may use |
| `/help` | shows all commands |
| `/model` | switches the model (in the terminal also `hermes model`) |

::: hinweis
Free models have **usage limits** and are sometimes slow. If you see "rate limit" or "too many requests", wait a
moment or choose another free model with `/model`.
:::

Done? Click **"Check"**.
