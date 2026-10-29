// Bony's Agents – Hilfe-Modus beim Kursleiter: Agent-PC eines Teilnehmers ansehen (und mit seiner Zustimmung
// steuern). Ob Eingaben ankommen, entscheidet der Rechner des Teilnehmers – hier wird nur angezeigt.
// noVNC erst nach der Anmeldung laden – vorher fehlt der Schlüssel, den der Server dafür verlangt
let RFB = null;

const frag = new URLSearchParams(location.hash.slice(1));
const sid = (location.pathname.match(/^\/help\/([0-9a-f]{8})$/) || [])[1] || "";
const token = frag.get("t");
if (location.hash) history.replaceState(null, "", location.pathname);   // Schlüssel nicht stehen lassen
window.addEventListener("hashchange", () => location.reload());

// Sprache: /assets/texte.js (Sprache des Browsers)
const tr = window.tr || ((text, kw) => (kw ? text.replace(/\{(\w+)\}/g, (m, k) => (k in kw ? String(kw[k]) : m)) : text));
const screenEl = document.getElementById("screen");
const stateEl = document.getElementById("state");
const infoEl = document.getElementById("info");
const overlay = document.getElementById("overlay");
const btnControl = document.getElementById("control");
const btnRelease = document.getElementById("release");
let rfb = null;
let final = false;
let connecting = false;

function setState(cls, text) { stateEl.className = "state " + cls; stateEl.textContent = text; }
function show(title, text) {
  document.getElementById("overlay-title").textContent = title;
  document.getElementById("overlay-text").textContent = text || "";
  overlay.hidden = false;
}
async function post(name) {
  const r = await fetch(`/bonys/v1/help/${name}`, { method: "POST", credentials: "same-origin",
    headers: { "Content-Type": "application/json" }, body: JSON.stringify({ s: sid, t: token || "" }) });
  return r.json().catch(() => ({}));
}

function connect(control) {
  if (rfb || connecting || final) return;
  connecting = true;
  rfb = new RFB(screenEl, `wss://${location.host}/bonys/v1/help/view?s=${encodeURIComponent(sid)}`,
                { wsProtocols: ["binary"], shared: true });
  rfb.viewOnly = !control;
  rfb.scaleViewport = true;
  rfb.background = "#000";
  rfb.addEventListener("connect", () => { connecting = false; overlay.hidden = true; });
  rfb.addEventListener("disconnect", () => { rfb = null; connecting = false; });
}

async function poll() {
  let s;
  try {
    const r = await fetch(`/bonys/v1/help/status?s=${encodeURIComponent(sid)}`, { credentials: "same-origin",
      cache: "no-store" });
    s = await r.json();
  } catch (e) {
    setState("lost", tr("Verbindung verloren")); show(tr("Verbindung verloren"), tr("Läuft der Hilfe-Schalter noch?"));
    return;
  }
  infoEl.textContent = s.name ? `${s.name} · ${s.vm}` : "";
  btnControl.hidden = !(s.view && !s.control);
  btnControl.disabled = !!s.control_requested;
  btnControl.textContent = s.control_requested ? tr("Steuerung angefragt …") : tr("Steuerung anfragen");
  btnRelease.hidden = !s.control;
  if (!s.connected || s.state === "beendet" || s.state === "abgelehnt" || s.state === "unbekannt") {
    final = true;
    if (rfb) rfb.disconnect();
    setState("ended", s.state === "abgelehnt" ? tr("Abgelehnt") : tr("Beendet"));
    show(s.state === "abgelehnt" ? tr("Der Teilnehmer hat abgelehnt") : tr("Hilfe beendet"),
         s.connected === false ? tr("Der Teilnehmer ist nicht mehr verbunden.") :
         (s.error || tr("In Bony's Agents kannst du erneut „Ansehen“ wählen.")));
    return;
  }
  if (!s.view) {
    setState("paused", tr("Warte auf Zustimmung"));
    show(tr("Warte auf Zustimmung …"), tr("{name} wird gefragt, ob du den Agent-PC „{vm}“ ansehen darfst.",
                                          { name: s.name, vm: s.vm }));
    return;
  }
  setState(s.control ? "live" : "paused", s.control ? tr("Du steuerst") : tr("Nur ansehen"));
  if (rfb) rfb.viewOnly = !s.control;
  else connect(s.control);
}

btnControl.addEventListener("click", () => post("control").then(poll));
btnRelease.addEventListener("click", () => post("release").then(poll));
document.getElementById("stop").addEventListener("click", async () => {
  await post("stop");
  final = true;
  if (rfb) rfb.disconnect();
  setState("ended", tr("Beendet"));
  show(tr("Hilfe beendet"), tr("Du kannst dieses Fenster schließen."));
});

(async () => {
  if (token) {
    const r = await post("auth");
    if (r.error) { final = true; setState("ended", tr("Ungültig")); show(tr("Ansicht nicht gültig"), r.error); return; }
  }
  try {
    RFB = (await import("/novnc/core/rfb.js")).default;
  } catch (e) {
    final = true; setState("ended", tr("Ungültig"));
    show(tr("Ansicht nicht gültig"), tr("In Bony's Agents erneut „Ansehen“ wählen.")); return;
  }
  poll();
  setInterval(() => { if (!final) poll(); }, 1500);
})();
