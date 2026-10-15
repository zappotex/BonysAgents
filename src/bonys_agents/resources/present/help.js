// Bony's Agents – Hilfe-Modus beim Kursleiter: Agent-PC eines Teilnehmers ansehen (und mit seiner Zustimmung
// steuern). Ob Eingaben ankommen, entscheidet der Rechner des Teilnehmers – hier wird nur angezeigt.
// noVNC erst nach der Anmeldung laden – vorher fehlt der Schlüssel, den der Server dafür verlangt
let RFB = null;

const frag = new URLSearchParams(location.hash.slice(1));
const sid = frag.get("s") || sessionStorage.getItem("bonys-help-s") || "";
const token = frag.get("t");
if (frag.get("s")) sessionStorage.setItem("bonys-help-s", sid);
if (location.hash) history.replaceState(null, "", "/help/");
// „Ansehen“ erneut gewählt, Browser nutzt diesen Tab: nur der Teil hinter „#“ ändert sich – dann neu laden
window.addEventListener("hashchange", () => location.reload());

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
    setState("lost", "Verbindung verloren"); show("Verbindung verloren", "Läuft der Hilfe-Schalter noch?");
    return;
  }
  infoEl.textContent = s.name ? `${s.name} · ${s.vm}` : "";
  btnControl.hidden = !(s.view && !s.control);
  btnControl.disabled = !!s.control_requested;
  btnControl.textContent = s.control_requested ? "Steuerung angefragt …" : "Steuerung anfragen";
  btnRelease.hidden = !s.control;
  if (!s.connected || s.state === "beendet" || s.state === "abgelehnt" || s.state === "unbekannt") {
    final = true;
    if (rfb) rfb.disconnect();
    setState("ended", s.state === "abgelehnt" ? "Abgelehnt" : "Beendet");
    show(s.state === "abgelehnt" ? "Der Teilnehmer hat abgelehnt" : "Hilfe beendet",
         s.connected === false ? "Der Teilnehmer ist nicht mehr verbunden." :
         (s.error || "In Bony's Agents kannst du erneut „Ansehen“ wählen."));
    return;
  }
  if (!s.view) {
    setState("paused", "Warte auf Zustimmung");
    show("Warte auf Zustimmung …", `${s.name} wird gefragt, ob du den Agent-PC „${s.vm}“ ansehen darfst.`);
    return;
  }
  setState(s.control ? "live" : "paused", s.control ? "Du steuerst" : "Nur ansehen");
  if (rfb) rfb.viewOnly = !s.control;
  else connect(s.control);
}

btnControl.addEventListener("click", () => post("control").then(poll));
btnRelease.addEventListener("click", () => post("release").then(poll));
document.getElementById("stop").addEventListener("click", async () => {
  await post("stop");
  final = true;
  if (rfb) rfb.disconnect();
  setState("ended", "Beendet");
  show("Hilfe beendet", "Du kannst dieses Fenster schließen.");
});

(async () => {
  if (token) {
    const r = await post("auth");
    if (r.error) { final = true; setState("ended", "Ungültig"); show("Ansicht nicht gültig", r.error); return; }
  }
  try {
    RFB = (await import("/novnc/core/rfb.js")).default;
  } catch (e) {
    final = true; setState("ended", "Ungültig");
    show("Ansicht nicht gültig", "In Bony's Agents erneut „Ansehen“ wählen."); return;
  }
  poll();
  setInterval(() => { if (!final) poll(); }, 1500);
})();
