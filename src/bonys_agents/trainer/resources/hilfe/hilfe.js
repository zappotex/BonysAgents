// SPDX-License-Identifier: GPL-3.0-or-later
// Hilfe-Funktion (Aufgabe 06): Agent-PC eines Teilnehmers im Fenster „Hilfe“ des Kursleiters.
//
// Python (trainer/gui/hilfe_fenster.py) gibt über QWebChannel das Objekt „betrachter“:
//   Signale  verbindung(json) – {url, passwort, modus, titel}, ende(text) – Hilfe ist vorbei, schliessen()
//   Slots    bereit(), verbunden(), getrennt(text), beenden()
// url zeigt auf die Brücke der App (nur 127.0.0.1, eine Verbindung), die zu x11vnc im Agent-PC weiterleitet.
import RFB from "/novnc/core/rfb.js";

const $ = (id) => document.getElementById(id);
let betrachter = null;
let rfb = null;
let passwort = null;
let fertig = false;

function zustand(art, text) {
  $("zustand").className = "zustand " + art;
  $("zustand").textContent = text;
}

function meldung(text) {
  $("meldung-text").textContent = text;
  $("meldung").hidden = false;
}

function start(json) {
  let d;
  try { d = JSON.parse(json); } catch (e) { return; }
  passwort = d.passwort;
  const bedienen = d.modus === "bedienen";
  $("info").textContent = (d.titel || "") + (bedienen ? " · Ansehen und bedienen" : " · Nur ansehen");
  $("cad").hidden = !bedienen;
  rfb = new RFB($("bild"), d.url, { wsProtocols: ["binary"], shared: false, credentials: { password: passwort } });
  rfb.viewOnly = !bedienen;
  rfb.scaleViewport = $("skalieren").checked;
  rfb.background = "#000";
  rfb.focusOnClick = bedienen;
  rfb.addEventListener("credentialsrequired", () => rfb.sendCredentials({ password: passwort }));
  rfb.addEventListener("connect", () => {
    passwort = null;   // nur für diese eine Anmeldung
    zustand("ok", bedienen ? "Verbunden – du kannst bedienen" : "Verbunden – nur ansehen");
    betrachter.verbunden();
    if (bedienen) rfb.focus();
  });
  rfb.addEventListener("securityfailure", (e) => {
    fertig = true;
    zustand("aus", "Abgelehnt");
    const grund = (e.detail && e.detail.reason) || "";
    betrachter.getrennt("Der Agent-PC hat die Anmeldung abgelehnt." + (grund ? " (" + grund + ")" : ""));
  });
  rfb.addEventListener("disconnect", (e) => {
    rfb = null;
    if (fertig) return;
    fertig = true;
    zustand("aus", "Getrennt");
    betrachter.getrennt(e.detail && e.detail.clean ? "Die Hilfe ist beendet." :
      "Die Verbindung zum Agent-PC ist abgebrochen.");
  });
}

function zeigen(text) {   // Python meldet das Ende (Teilnehmer hat beendet, Kurs pausiert …)
  fertig = true;
  if (rfb) { try { rfb.disconnect(); } catch (e) { /* schon weg */ } }
  zustand("aus", "Getrennt");
  meldung(text);
}

$("skalieren").addEventListener("change", () => { if (rfb) rfb.scaleViewport = $("skalieren").checked; });
$("cad").addEventListener("click", () => { if (rfb) rfb.sendCtrlAltDel(); });
$("beenden").addEventListener("click", () => betrachter.beenden());
$("schliessen").addEventListener("click", () => betrachter.beenden());

new QWebChannel(qt.webChannelTransport, (kanal) => {
  betrachter = kanal.objects.betrachter;
  betrachter.verbindung.connect(start);
  betrachter.ende.connect(zeigen);
  betrachter.schliessen.connect(() => {
    fertig = true;
    if (rfb) { try { rfb.disconnect(); } catch (e) { /* egal */ } }
  });
  betrachter.bereit();
});
