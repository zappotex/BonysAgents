// Bony's Agents – Vorführung: Name und Code eingeben (Code kann aus dem QR-Code hinter „#“ mitkommen)
// Sprache: /assets/texte.js (Sprache des Browsers)
const tr = window.tr || ((text, kw) => (kw ? text.replace(/\{(\w+)\}/g, (m, k) => (k in kw ? String(kw[k]) : m)) : text));
const form = document.getElementById("form");
const msg = document.getElementById("msg");
const nameInput = document.getElementById("name");
const codeInput = document.getElementById("code");

const frag = new URLSearchParams(location.hash.slice(1));
if (frag.get("code")) codeInput.value = frag.get("code");
let stored = "";
try { stored = localStorage.getItem("bonys-name") || ""; } catch (e) { /* privat */ }
nameInput.value = frag.get("name") || stored;
if (location.hash) history.replaceState(null, "", "/");  // Code nicht in der Adresszeile stehen lassen
window.addEventListener("hashchange", () => location.reload());  // neuer QR-Code im selben Tab
(nameInput.value ? codeInput : nameInput).focus();

fetch("/bonys/v1/present/status", { credentials: "same-origin" }).then(r => r.json()).then(s => {
  if (s.title) document.getElementById("title").textContent =
    tr("Der Kursleiter zeigt „{titel}“. Du kannst nur zuschauen.", { titel: s.title });
  if (s.state === "live" || s.state === "paused") location.replace("/view");  // schon beigetreten
}).catch(() => {});

form.addEventListener("submit", async (ev) => {
  ev.preventDefault();
  msg.textContent = "";
  document.getElementById("go").disabled = true;
  try {
    const r = await fetch("/bonys/v1/present/join", {
      method: "POST", credentials: "same-origin", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name: nameInput.value, code: codeInput.value }),
    });
    const data = await r.json().catch(() => ({}));
    if (r.ok) {
      try { localStorage.setItem("bonys-name", nameInput.value); } catch (e) { /* privat */ }
      location.replace("/view");
      return;
    }
    msg.textContent = data.error || tr("Fehler {status}", { status: r.status });
  } catch (e) {
    msg.textContent = tr("Keine Verbindung zum Rechner des Kursleiters.");
  }
  document.getElementById("go").disabled = false;
});
