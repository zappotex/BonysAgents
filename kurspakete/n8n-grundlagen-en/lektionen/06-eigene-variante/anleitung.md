# Exercise: your own variant

Now you make the workflow **yours**. Pick two or three points:

1. **Another feed:** swap the feed URL, for example:

   | Source | Feed URL |
   |---|---|
   | Ars Technica (technology) | `https://feeds.arstechnica.com/arstechnica/index` |
   | The Guardian (world news) | `https://www.theguardian.com/world/rss` |
   | NPR (news) | `https://feeds.npr.org/1001/rss.xml` |

   Or search your favorite site for "RSS".

2. **Another time:** under **Poll Times** e.g. **"Every Day"** with a time – then the news arrives once a day.

3. **A nicer message:** write something in front in the Text field, e.g. `📰 ` before the title. Under **Additional
   Fields** → turn off **Append n8n Attribution** – then the note "sent automatically with n8n" disappears.

4. **A second workflow:** build a second one for another feed with **"Create workflow"**.

After every change: **Ctrl + S** and **"Publish"** again, otherwise the old version keeps running.

::: tipp
**For fast learners:** add the **"Filter"** node between the trigger and Telegram and only let through articles whose
title contains a particular word.
:::
