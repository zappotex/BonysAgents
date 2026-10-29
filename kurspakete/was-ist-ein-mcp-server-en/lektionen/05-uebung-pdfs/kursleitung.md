**Flow:** 2 minutes explaining, 13 minutes working alone, 5 minutes bringing it together.

**Solution / expectation:**

1. Resolutions: the membership fee stays at **36 EUR** a year, summer party on **4 July**, a **rain barrel** for the
   community garden. All unanimous.
2. `minutes-upright.pdf`: page 2 rotated back by 90° (or −90°). Some models rotate in the wrong direction – then the
   page is upside down. A good occasion for "check yourself".
3. `invoices-total.pdf` with two pages: invoice 2026-031 (March), then 2026-042 (April).
4. For fast learners: 48.50 + 41.90 = **90.40 EUR**.

**Stumbling blocks:**

- Hermes uses the terminal (`pdftotext`, Python) instead of PdfCraft: say "use PdfCraft" explicitly; if PdfCraft
  isn't visible, Hermes wasn't restarted after `hermes mcp add` (`/reload-mcp`).
- "Access denied" or file not found: PdfCraft may only work in `~/Agent-Files/pdf`. Copy files from elsewhere there
  first.
- Free model overloaded ("rate limit"): wait a moment or switch with `/model`.

The check uses `pdfinfo` and `pdftotext` to see whether `invoices-total.pdf` has exactly two pages and contains both
invoice numbers.
