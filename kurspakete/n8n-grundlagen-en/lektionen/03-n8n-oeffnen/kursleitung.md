- No "n8n" icon: Agent PC created without n8n → start the Agent PC, in the detail view next to "Programs" → "Add
  programs …" → n8n (takes a few minutes, downloads the official Docker image).
- The page stays empty: n8n is still starting (up to a minute after booting). Then F5.
- For the account, any address in the format `name@example.com` is enough – n8n doesn't send mail. But remember the
  password, otherwise n8n is locked after signing out.
- The check only asks n8n's database **whether** a user with an e-mail address exists – it reads neither the address
  nor the password.
