# A head without hands

A language model is a **clever head**: it understands your request and knows what would need to be done. For it to
actually **do** something, it needs **tools** – hands, so to speak.

## What is an MCP server?

**MCP** stands for *Model Context Protocol*. It's a common language through which an agent can use tools. An **MCP
server** is a small program that offers an agent a **toolbox** – for example "open PDF", "rotate page", "merge
PDFs".

- Hermes asks the MCP server: *Which tools do you have?*
- For your task, Hermes chooses the right tool and uses it.
- The MCP server runs in the Agent PC and may only do what you allow it – for example only one particular folder.

## Try it: Hermes without a PDF tool

The course package has put three sample PDFs in `~/Agent-Files/pdf`: two invoices and the minutes of a made-up
garden club.

Ask Hermes: *"Page 2 of ~/Agent-Files/pdf/minutes.pdf is sideways. Rotate it upright."*

Watch what happens: does Hermes look for a detour in the terminal? Does it ask back? Does it say it can't do it?
**Don't confirm** if it wants to install programs – we'll do that ourselves properly in a moment.

::: tipp
Hermes often manages to **read** text from a PDF even without an extra tool, using programs already in the Agent
PC. Rotating or deleting pages or merging PDFs works **more reliably** with a real PDF tool – and you see exactly
what it uses.
:::

Finally: the **quiz**.
