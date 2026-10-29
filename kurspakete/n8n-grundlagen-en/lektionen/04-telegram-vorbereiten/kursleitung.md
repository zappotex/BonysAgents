- Decide beforehand: **everyone their own bot** (recommended, everyone only gets their own messages) or a shared course
  bot. With a shared bot you pass on the token – then create a new one with `/revoke` at BotFather after the course.
- Most common errors: the username doesn't end in `bot` or is taken; `getUpdates` returns `[]` because nobody has
  written to the bot yet.
- **Screen sharing:** never show the token when presenting – don't share the window beforehand or cover the token.
- The chat ID is a number (negative for groups). For this course, the chat with your own bot is enough.
