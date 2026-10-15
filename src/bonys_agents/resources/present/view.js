// Bony's Agents – Vorführung ansehen: noVNC nur zum Zuschauen, Status, automatische Wiederverbindung.
// Der Server lässt ohnehin keine Eingaben durch – viewOnly verhindert nur, dass der Browser es versucht.
import RFB from "/novnc/core/rfb.js";

const screenEl = document.getElementById("screen");
const stateEl = document.getElementById("state");
const infoEl = document.getElementById("info");
const overlay = document.getElementById("overlay");
const overlayTitle = document.getElementById("overlay-title");
const overlayText = document.getElementById("overlay-text");
const overlayLink = document.getElementById("overlay-link");

let rfb = null;
let final = false;
let connecting = false;
let retry = 1000;

function setState(cls, text) {
  stateEl.className = "state " + cls;
  stateEl.textContent = text;
}

function showOverlay(title, text, link = false) {
  overlayTitle.textContent = title;
  overlayText.textContent = text || "";
  overlayLink.hidden = !link;
  overlay.hidden = false;
}

function connect() {
  if (rfb || connecting || final) return;
  connecting = true;
  const url = `wss://${location.host}/bonys/v1/present/ws`;
  try {
    rfb = new RFB(screenEl, url, { wsProtocols: ["binary"], shared: true });
  } catch (e) {
    connecting = false;
    return;
  }
  rfb.viewOnly = true;
  rfb.scaleViewport = true;
  rfb.resizeSession = false;
  rfb.clipViewport = false;
  rfb.focusOnClick = false;
  rfb.showDotCursor = false;
  rfb.background = "#000";
  rfb.addEventListener("connect", () => {
    connecting = false;
    retry = 1000;
    overlay.hidden = true;
    setState("live", "Verbunden");
  });
  rfb.addEventListener("disconnect", () => {
    rfb = null;
    connecting = false;
    poll(true);
  });
}

async function poll(afterDisconnect = false) {
  let s;
  try {
    const r = await fetch("/bonys/v1/present/status", { credentials: "same-origin", cache: "no-store" });
    s = await r.json();
  } catch (e) {
    setState("lost", "Verbindung verloren");
    showOverlay("Verbindung verloren", "Versuche es gleich wieder … (WLAN verbunden?)");
    return;
  }
  infoEl.textContent = s.title ? `${s.title} · ${s.viewers} Zuschauer` : "";
  if (s.state === "ended") {
    final = true;
    if (rfb) rfb.disconnect();
    setState("ended", "Beendet");
    showOverlay("Vorführung beendet", "Danke fürs Zuschauen!");
  } else if (s.state === "removed" || s.state === "unknown") {
    final = true;
    if (rfb) rfb.disconnect();
    setState("ended", s.state === "removed" ? "Entfernt" : "Nicht beigetreten");
    showOverlay(s.state === "removed" ? "Du wurdest vom Kursleiter entfernt" : "Nicht beigetreten", "", true);
  } else if (s.state === "paused") {
    if (rfb) rfb.disconnect();
    setState("paused", "Pause");
    showOverlay(s.message || "Gleich geht's weiter …", "Der Kursleiter hat kurz pausiert.");
  } else if (s.state === "live") {
    if (!rfb) {
      if (afterDisconnect) {
        setState("lost", "Verbinde neu …");
        setTimeout(connect, retry);
        retry = Math.min(retry * 2, 10000);
      } else {
        connect();
      }
    }
  }
}

document.getElementById("full").addEventListener("click", () => {
  if (document.fullscreenElement) document.exitFullscreen();
  else document.documentElement.requestFullscreen?.().catch(() => {});
});
document.getElementById("leave").addEventListener("click", async () => {
  final = true;
  if (rfb) rfb.disconnect();
  await fetch("/bonys/v1/present/leave", { method: "POST", credentials: "same-origin",
    headers: { "Content-Type": "application/json" }, body: "{}" }).catch(() => {});
  location.replace("/");
});

poll();
setInterval(() => { if (!final) poll(); }, 2500);
