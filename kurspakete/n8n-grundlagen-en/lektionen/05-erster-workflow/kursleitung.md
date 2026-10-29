**Flow:** 8 minutes demo (step by step, participants build along), 12 minutes finishing, 5 minutes buffer.

- **Don't show the token**: pause the shared window briefly while creating the credential, or create a credential
  beforehand and only select it.
- **"Fetch Test Event"** fetches the latest article – so everyone immediately sees data to fill the Text field with.
- **Text** field: dragging (drag & drop) from the left column is easiest. If you type, you have to switch the field to
  **Expression**, otherwise `{{ $json.title }}` appears literally in the message.
- Telegram error "chat not found": wrong chat ID or nobody has written to the bot yet. "Unauthorized": token copied
  wrongly.
- After **"Publish"**, n8n checks every hour. New articles don't arrive right away – that's correct. For the demo,
  choose "Every Minute" and switch it back afterwards.
- At the bottom of every message it says "This message was sent automatically with n8n" – turned off in lesson 6.
- The check only reads from n8n's database whether a **published** workflow contains the node types "RSS Feed
  Trigger" and "Telegram" – no credentials.
