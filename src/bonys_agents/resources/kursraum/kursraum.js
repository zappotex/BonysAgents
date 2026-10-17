// SPDX-License-Identifier: GPL-3.0-or-later
// Kursraum (Aufgabe 05): LiveKit im Fenster „Kursraum“ von Bony's Agents.
//
// Python (gui/kursraum_fenster.py) gibt über QWebChannel das Objekt „bruecke“:
//   Signale  karte(json)    – {url, token, rolle, raum, ablauf, kursname, teilen, teilen_hinweis} oder {fehler}
//            antwort(json)  – {id, ok, text} auf stumm/entfernen
//            schliessen()   – Fenster wird geschlossen: Raum sauber verlassen
//   Slots    bereit(), stumm(id, identity, trackSid), entfernen(id, identity), erneut(), verlassen()
//
// Chat und Handzeichen laufen als Datennachrichten (zuverlässig), Themen „chat“, „hand“ und „freigabe“, Inhalt JSON.
// Nichts wird gespeichert: Der Chat gilt nur, solange das Fenster offen ist.
'use strict';

(function () {
  const LK = window.LivekitClient;
  const QUELLE = LK.Track.Source;
  const KURSLEITER = 'kursleiter';
  const MAX_CHAT = 500;
  const kodierer = new TextEncoder();
  const dekodierer = new TextDecoder();

  const $ = (id) => document.getElementById(id);
  const el = {
    kursname: $('kursname'), verbindung: $('verbindung'), rolle: $('rolle'),
    buehne: $('buehne-video'), buehneLeer: $('buehne-leer'), buehneName: $('buehne-name'), kameras: $('kameras'),
    anzahl: $('anzahl'), teilnehmer: $('teilnehmer'), chat: $('chat'), chatForm: $('chat-form'),
    chatText: $('chat-text'), chatSenden: $('chat-senden'),
    mikrofon: $('mikrofon'), kamera: $('kamera'), hand: $('hand'), teilen: $('teilen'),
    freigabeWahl: $('freigabe-wahl'), freigabePflicht: $('freigabe-pflicht'), ton: $('ton'), verlassen: $('verlassen'),
    hinweis: $('hinweis'), schicht: $('schicht'), dialogText: $('dialog-text'), dialogKnoepfe: $('dialog-knoepfe'),
    audio: $('audio'),
  };

  let bruecke = null;
  let karte = null;
  let room = null;
  let gehtGerade = false;             // „Kursraum verlassen“ oder Fenster zu – Trennen ist gewollt
  let meineHand = false;
  const haende = new Map();           // identity → true
  const freigabe = { pflicht: false, erlaubt: new Set() };   // beim Kursleiter: die Einstellung; sonst: was er schickte
  const anfragen = new Map();         // id → Text für die Rückmeldung
  let anfrageNr = 0;
  let buehnenSpur = null;
  const kacheln = new Map();          // trackSid → {div, track}
  let hinweisUhr = 0;
  let zeichnenGeplant = false;

  const ichLeite = () => karte && karte.rolle === KURSLEITER;

  // ------------------------------------------------------------ Hilfen
  function rolleVon(p) {
    if (!p) return '';
    if (p === (room && room.localParticipant)) return karte ? karte.rolle : '';
    try {
      const m = JSON.parse(p.metadata || '{}');
      return m && m.rolle === KURSLEITER ? KURSLEITER : '';
    } catch (e) {
      return '';
    }
  }
  const istLeiter = (p) => rolleVon(p) === KURSLEITER;
  const nameVon = (p) => (p && (p.name || p.identity)) || '?';

  function hinweis(text, sekunden) {
    el.hinweis.textContent = text;
    el.hinweis.hidden = false;
    clearTimeout(hinweisUhr);
    hinweisUhr = setTimeout(() => { el.hinweis.hidden = true; }, (sekunden || 6) * 1000);
  }

  // Dialog über der Seite: knoepfe = [{text, aktion, art}] – ohne Knöpfe nur Text (z. B. „Verbinde …“)
  function dialog(text, knoepfe) {
    el.dialogText.textContent = text;
    el.dialogKnoepfe.replaceChildren();
    for (const k of knoepfe || []) {
      const b = document.createElement('button');
      b.type = 'button';
      b.textContent = k.text;
      if (k.art) b.className = k.art;
      b.addEventListener('click', () => { dialogZu(); if (k.aktion) k.aktion(); });
      el.dialogKnoepfe.appendChild(b);
    }
    el.schicht.hidden = false;
    const erster = el.dialogKnoepfe.querySelector('button:last-child');
    if (erster) erster.focus();
  }
  function dialogZu() { el.schicht.hidden = true; }

  function nachfragen(text, ja, aktion) {
    dialog(text, [{ text: 'Abbrechen' }, { text: ja, aktion, art: 'gefahr' }]);
  }

  function fehlerText(e) {
    const name = e && e.name;
    if (name === 'NotAllowedError') {
      return 'Der Zugriff wurde verweigert. Unter macOS: Systemeinstellungen → Datenschutz & Sicherheit → ' +
             'Kamera/Mikrofon bzw. Bildschirmaufnahme für Bony\'s Agents erlauben.';
    }
    if (name === 'NotFoundError') return 'Kein passendes Gerät gefunden.';
    if (name === 'NotReadableError') return 'Das Gerät wird gerade von einem anderen Programm benutzt.';
    return (e && e.message) || String(e);
  }

  async function senden(thema, daten, an) {
    if (!room || room.state !== LK.ConnectionState.Connected) return;
    const optionen = { reliable: true, topic: thema };
    if (an && an.length) optionen.destinationIdentities = an;
    try {
      await room.localParticipant.publishData(kodierer.encode(JSON.stringify(daten)), optionen);
    } catch (e) {
      hinweis('Nachricht nicht gesendet: ' + fehlerText(e));
    }
  }

  // ------------------------------------------------------------ Start
  function start(json) {
    let neu;
    try { neu = JSON.parse(json); } catch (e) { return; }
    if (neu.fehler) {
      dialog(neu.fehler, [{ text: 'Schließen', aktion: gehen }]);
      return;
    }
    karte = neu;
    el.kursname.textContent = karte.kursname ? 'Kursraum – ' + karte.kursname : 'Kursraum';
    document.title = el.kursname.textContent;
    el.rolle.textContent = ichLeite() ? 'Du leitest den Kurs' : 'Du nimmst teil';
    el.teilen.hidden = !ichLeite();
    el.freigabeWahl.hidden = !ichLeite();
    if (ichLeite() && !karte.teilen) el.teilen.title = karte.teilen_hinweis || '';
    verbinden();
  }

  async function verbinden() {
    if (room) {
      const alt = room;
      room = null;
      try { await alt.disconnect(); } catch (e) { /* schon getrennt */ }
    }
    haende.clear();
    meineHand = false;
    gehtGerade = false;
    dialog('Verbinde mit dem Kursraum …');
    room = new LK.Room({
      adaptiveStream: true,
      dynacast: true,
      audioCaptureDefaults: { echoCancellation: true, noiseSuppression: true, autoGainControl: true },
      videoCaptureDefaults: { resolution: LK.VideoPresets.h540.resolution },
    });
    ereignisse(room);
    try {
      await room.connect(karte.url, karte.token);
    } catch (e) {
      const r = room;
      room = null;   // sein „Disconnected“ soll die Meldung nicht überschreiben
      try { await r.disconnect(); } catch (e2) { /* nie verbunden */ }
      verbindenFehlgeschlagen(e);
      return;
    }
    dialogZu();
    for (const k of [el.mikrofon, el.kamera, el.hand, el.chatText, el.chatSenden]) k.disabled = false;
    el.teilen.disabled = false;
    systemNachricht('Du bist im Kursraum.');
    if (ichLeite()) {
      await mikrofonSetzen(true);   // Kursleiter kommt mit Mikrofon an, Teilnehmer mit allem aus
      freigabeSenden();
    }
    tonPruefen();
    zeichnen();
  }

  function abgelaufen() {
    return karte && karte.ablauf && Date.now() / 1000 >= karte.ablauf;
  }

  function verbindenFehlgeschlagen(e) {
    if (abgelaufen()) {
      erneutAnbieten('Deine Eintrittskarte ist abgelaufen (sie gilt 6 Stunden). Tritt bitte erneut ein.');
    } else if (e && e.reason === LK.ConnectionErrorReason.NotAllowed) {
      erneutAnbieten('Der Kursraum hat die Eintrittskarte nicht angenommen. Tritt bitte erneut ein.');
    } else {
      erneutAnbieten('Der Kursraum ist nicht erreichbar.\n\n' + fehlerText(e));
    }
  }

  function erneutAnbieten(text) {
    sperren();
    dialog(text, [{ text: 'Schließen', aktion: gehen }, { text: 'Erneut eintreten', aktion: erneut }]);
  }

  function erneut() {
    dialog('Hole eine neue Eintrittskarte …');
    bruecke.erneut();   // Python antwortet mit karte(json) – bei 409 mit {fehler}
  }

  function sperren() {
    for (const k of [el.mikrofon, el.kamera, el.hand, el.teilen, el.chatText, el.chatSenden]) k.disabled = true;
    el.verbindung.hidden = true;
  }

  async function gehen() {
    gehtGerade = true;
    if (room) {
      try { await room.disconnect(); } catch (e) { /* egal */ }
    }
    bruecke.verlassen();
  }

  // ------------------------------------------------------------ Ereignisse von LiveKit
  function ereignisse(r) {
    const E = LK.RoomEvent;
    const neu = () => zeichnenBald();
    r.on(E.ParticipantConnected, (p) => {
      systemNachricht(nameVon(p) + ' ist da.');
      if (meineHand) senden('hand', { oben: true }, [p.identity]);
      if (ichLeite()) freigabeSenden([p.identity]);
      neu();
    });
    r.on(E.ParticipantDisconnected, (p) => {
      haende.delete(p.identity);
      systemNachricht(nameVon(p) + ' ist gegangen.');
      neu();
    });
    r.on(E.TrackSubscribed, (track) => {
      if (track.kind === LK.Track.Kind.Audio) el.audio.appendChild(track.attach());
      neu();
    });
    r.on(E.TrackUnsubscribed, (track) => {
      if (track.kind === LK.Track.Kind.Audio) track.detach().forEach((a) => a.remove());
      neu();
    });
    for (const ev of [E.TrackMuted, E.TrackUnmuted, E.TrackPublished, E.TrackUnpublished, E.LocalTrackPublished,
      E.ParticipantMetadataChanged, E.ParticipantNameChanged]) {
      r.on(ev, neu);
    }
    r.on(E.LocalTrackUnpublished, (pub) => {
      if (pub.source === QUELLE.ScreenShare) hinweis('Bildschirm wird nicht mehr geteilt.');
      neu();
    });
    r.on(E.TrackMuted, (pub, p) => {
      if (p === r.localParticipant && pub.source === QUELLE.Microphone && !ichLeite()) {
        hinweis('Dein Mikrofon ist jetzt stumm.');
      }
    });
    r.on(E.ActiveSpeakersChanged, neu);
    r.on(E.DataReceived, (daten, p, _art, thema) => empfangen(daten, p, thema));
    r.on(E.Reconnecting, () => { el.verbindung.hidden = false; });
    r.on(E.SignalReconnecting, () => { el.verbindung.hidden = false; });
    r.on(E.Reconnected, () => { el.verbindung.hidden = true; neu(); });
    r.on(E.AudioPlaybackStatusChanged, tonPruefen);
    r.on(E.MediaDevicesError, (e) => hinweis(fehlerText(e)));
    r.on(E.Disconnected, (grund) => getrennt(r, grund));
  }

  function getrennt(r, grund) {
    if (r !== room) return;   // alter Raum nach „Erneut eintreten“
    el.verbindung.hidden = true;
    sperren();
    buehneSetzen(null, '');
    for (const k of kacheln.values()) k.div.remove();
    kacheln.clear();
    el.audio.replaceChildren();
    if (gehtGerade) return;
    const G = LK.DisconnectReason;
    if (grund === G.PARTICIPANT_REMOVED) {
      erneutAnbieten('Der Kursleiter hat dich aus dem Kursraum genommen.');
    } else if (grund === G.ROOM_DELETED || grund === G.ROOM_CLOSED) {
      erneutAnbieten('Der Kursraum wurde geschlossen – der Kurs ist beendet oder pausiert.');
    } else if (grund === G.DUPLICATE_IDENTITY) {
      erneutAnbieten('Du hast den Kursraum an einer anderen Stelle betreten (anderes Fenster oder anderer Rechner).');
    } else if (abgelaufen()) {
      erneutAnbieten('Deine Eintrittskarte ist abgelaufen (sie gilt 6 Stunden). Tritt bitte erneut ein.');
    } else {
      erneutAnbieten('Die Verbindung zum Kursraum ist abgebrochen.');
    }
  }

  function tonPruefen() {
    el.ton.hidden = !room || room.canPlaybackAudio;
  }

  // ------------------------------------------------------------ Datennachrichten: chat, hand, freigabe
  function empfangen(daten, p, thema) {
    if (!p) return;   // vom Server selbst – gibt es hier nicht
    let d;
    try { d = JSON.parse(dekodierer.decode(daten)); } catch (e) { return; }
    if (!d || typeof d !== 'object') return;
    if (thema === 'chat' && typeof d.text === 'string' && d.text.trim()) {
      chatNachricht(nameVon(p), d.text.slice(0, 1000), istLeiter(p));
    } else if (thema === 'hand') {
      const vorher = haende.has(p.identity);
      if (d.oben) haende.set(p.identity, true); else haende.delete(p.identity);
      if (d.oben && !vorher && ichLeite()) hinweis('✋ ' + nameVon(p) + ' meldet sich.');
      zeichnenBald();
    } else if (thema === 'freigabe' && istLeiter(p) && !ichLeite()) {
      freigabeEmpfangen(d);
    }
  }

  function freigabeEmpfangen(d) {
    const ich = room.localParticipant.identity;
    const durfte = darfSprechen();
    freigabe.pflicht = !!d.pflicht;
    freigabe.erlaubt = new Set(Array.isArray(d.erlaubt) ? d.erlaubt.filter((x) => typeof x === 'string') : []);
    const darf = darfSprechen();
    if (!darf && room.localParticipant.isMicrophoneEnabled) {
      mikrofonSetzen(false);
      hinweis('Sprechen nur nach Freigabe – dein Mikrofon ist aus. Heb die Hand, um dich zu melden.');
    } else if (darf && !durfte && freigabe.erlaubt.has(ich)) {
      hinweis('Du darfst jetzt sprechen – schalte dein Mikrofon ein.');
      if (meineHand) handSetzen(false);
    } else if (freigabe.pflicht && !darf && durfte) {
      hinweis('Sprechen nur nach Freigabe durch den Kursleiter. Heb die Hand, um dich zu melden.');
    }
    zeichnenBald();
  }

  function darfSprechen() {
    return ichLeite() || !freigabe.pflicht || (room && freigabe.erlaubt.has(room.localParticipant.identity));
  }

  function freigabeSenden(an) {
    senden('freigabe', { pflicht: freigabe.pflicht, erlaubt: [...freigabe.erlaubt] }, an);
  }

  // ------------------------------------------------------------ Chat
  function zeit() {
    return new Date().toLocaleTimeString('de-DE', { hour: '2-digit', minute: '2-digit' });
  }

  function chatZeile(div) {
    const unten = el.chat.scrollHeight - el.chat.scrollTop - el.chat.clientHeight < 40;
    el.chat.appendChild(div);
    while (el.chat.childElementCount > MAX_CHAT) el.chat.firstElementChild.remove();
    if (unten) el.chat.scrollTop = el.chat.scrollHeight;
  }

  function chatNachricht(name, text, leiter) {
    const div = document.createElement('p');
    div.className = 'nachricht';
    const b = document.createElement('b');
    b.textContent = name + (leiter ? ' (Kursleiter)' : '');
    const z = document.createElement('span');
    z.className = 'zeit';
    z.textContent = zeit();
    div.append(b, z, document.createElement('br'), document.createTextNode(text));
    chatZeile(div);
  }

  function systemNachricht(text) {
    const div = document.createElement('p');
    div.className = 'nachricht system';
    div.textContent = zeit() + ' – ' + text;
    chatZeile(div);
  }

  el.chatForm.addEventListener('submit', (ev) => {
    ev.preventDefault();
    const text = el.chatText.value.trim();
    if (!text || !room) return;
    el.chatText.value = '';
    senden('chat', { text });
    chatNachricht(nameVon(room.localParticipant), text, ichLeite());
  });

  // ------------------------------------------------------------ Knöpfe unten
  async function mikrofonSetzen(an) {
    if (an && !darfSprechen()) {
      hinweis('Sprechen nur nach Freigabe durch den Kursleiter. Heb die Hand, um dich zu melden.');
      return;
    }
    try {
      await room.localParticipant.setMicrophoneEnabled(an);
    } catch (e) {
      hinweis('Mikrofon: ' + fehlerText(e), 10);
    }
    zeichnenBald();
  }

  async function kameraSetzen(an) {
    try {
      await room.localParticipant.setCameraEnabled(an);
    } catch (e) {
      hinweis('Kamera: ' + fehlerText(e), 10);
    }
    zeichnenBald();
  }

  async function teilenSetzen(an) {
    if (an && !karte.teilen) {
      hinweis(karte.teilen_hinweis || 'Bildschirm teilen geht hier nicht.', 12);
      return;
    }
    try {
      await room.localParticipant.setScreenShareEnabled(an, {
        audio: false, contentHint: 'detail', resolution: LK.ScreenSharePresets.h1080fps15.resolution,
      });
    } catch (e) {
      if (e && e.name === 'NotAllowedError' && /cancel|abgebrochen|Permission denied by user/i.test(e.message || '')) {
        return;   // Auswahl abgebrochen
      }
      hinweis('Bildschirm teilen: ' + fehlerText(e), 12);
    }
    zeichnenBald();
  }

  function handSetzen(oben) {
    meineHand = oben;
    if (oben) haende.set(room.localParticipant.identity, true);
    else haende.delete(room.localParticipant.identity);
    senden('hand', { oben });
    zeichnenBald();
  }

  el.mikrofon.addEventListener('click', () => mikrofonSetzen(!room.localParticipant.isMicrophoneEnabled));
  el.kamera.addEventListener('click', () => kameraSetzen(!room.localParticipant.isCameraEnabled));
  el.teilen.addEventListener('click', () => teilenSetzen(!room.localParticipant.isScreenShareEnabled));
  el.hand.addEventListener('click', () => handSetzen(!meineHand));
  el.ton.addEventListener('click', async () => {
    try { await room.startAudio(); } catch (e) { hinweis('Ton: ' + fehlerText(e)); }
    tonPruefen();
  });
  el.verlassen.addEventListener('click', () => {
    if (!room || room.state !== LK.ConnectionState.Connected) { gehen(); return; }
    nachfragen('Kursraum verlassen?', 'Verlassen', gehen);
  });
  el.freigabePflicht.addEventListener('change', () => {
    freigabe.pflicht = el.freigabePflicht.checked;
    freigabeSenden();
    systemNachricht(freigabe.pflicht ? 'Teilnehmer sprechen jetzt nur nach Freigabe.' : 'Alle dürfen sprechen.');
    zeichnenBald();
  });

  // ------------------------------------------------------------ Kursleiter-Steuerung (über Python → LiveKit-Server)
  function anfrage(text) {
    anfrageNr += 1;
    const id = 'a' + anfrageNr;
    anfragen.set(id, text);
    return id;
  }

  function antwort(json) {
    let d;
    try { d = JSON.parse(json); } catch (e) { return; }
    const text = anfragen.get(d.id);
    anfragen.delete(d.id);
    hinweis(d.ok ? (text || 'Erledigt.') : d.text || 'Das hat nicht geklappt.', d.ok ? 4 : 10);
  }

  function stummSchalten(p) {
    const pub = p.getTrackPublication(QUELLE.Microphone);
    if (!pub || !pub.trackSid) return;
    bruecke.stumm(anfrage(nameVon(p) + ' ist stumm geschaltet.'), p.identity, pub.trackSid);
  }

  function entfernen(p) {
    nachfragen('„' + nameVon(p) + '“ aus dem Kursraum entfernen?\n\nIm Kurs bleibt der Teilnehmer und kann ' +
               'wieder eintreten. Ganz aus dem Kurs nimmst du ihn in der Kursansicht („Entfernen …“).',
    'Entfernen', () => bruecke.entfernen(anfrage(nameVon(p) + ' ist nicht mehr im Kursraum.'), p.identity));
  }

  function freigabeUmschalten(p) {
    if (freigabe.erlaubt.has(p.identity)) {
      freigabe.erlaubt.delete(p.identity);
      const pub = p.getTrackPublication(QUELLE.Microphone);
      if (pub && !pub.isMuted && pub.trackSid) {
        bruecke.stumm(anfrage(nameVon(p) + ' darf nicht mehr sprechen.'), p.identity, pub.trackSid);
      }
    } else {
      freigabe.erlaubt.add(p.identity);
      haende.delete(p.identity);
    }
    freigabeSenden();
    zeichnenBald();
  }

  // ------------------------------------------------------------ Anzeige
  function zeichnenBald() {
    if (zeichnenGeplant) return;
    zeichnenGeplant = true;
    requestAnimationFrame(() => { zeichnenGeplant = false; zeichnen(); });
  }

  function alle() {
    if (!room) return [];
    const liste = [room.localParticipant, ...room.remoteParticipants.values()];
    return liste.sort((a, b) => (istLeiter(b) - istLeiter(a)) ||
      (a === room.localParticipant ? -1 : b === room.localParticipant ? 1 : 0) ||
      nameVon(a).localeCompare(nameVon(b), 'de'));
  }

  function spur(p, quelle) {
    const pub = p.getTrackPublication(quelle);
    return pub && pub.track && !pub.isMuted ? pub.track : null;
  }

  function zeichnen() {
    if (!room) return;
    const leute = alle();
    const sprecher = new Set(room.activeSpeakers.map((p) => p.identity));

    // Bühne: Bildschirm des Kursleiters, sonst seine Kamera
    const leiter = leute.filter(istLeiter);
    let buehne = null;
    let buehneVon = null;
    for (const p of leiter) {
      const t = spur(p, QUELLE.ScreenShare);
      if (t) { buehne = t; buehneVon = p; break; }
    }
    let kameraAufBuehne = null;
    if (!buehne) {
      for (const p of leiter) {
        const t = spur(p, QUELLE.Camera);
        if (t) { buehne = t; buehneVon = p; kameraAufBuehne = t; break; }
      }
    }
    buehneSetzen(buehne, buehneVon ? nameVon(buehneVon) : '');

    // Kamerastreifen: alle Kameras, die an sind (außer der auf der Bühne)
    const sichtbar = new Set();
    for (const p of leute) {
      const t = spur(p, QUELLE.Camera);
      if (!t || t === kameraAufBuehne) continue;
      const sid = t.sid || p.identity + ':kamera';
      sichtbar.add(sid);
      let k = kacheln.get(sid);
      if (!k || k.track !== t) {
        if (k) { k.track.detach(k.video); k.div.remove(); }
        const div = document.createElement('div');
        div.className = 'kachel';
        const video = t.attach();
        video.muted = true;
        const name = document.createElement('span');
        div.append(video, name);
        k = { div, video, name, track: t };
        kacheln.set(sid, k);
      }
      k.name.textContent = nameVon(p) + (p === room.localParticipant ? ' (du)' : '');
      k.div.classList.toggle('spricht', sprecher.has(p.identity));
      el.kameras.appendChild(k.div);   // hängt in Reihenfolge an
    }
    for (const [sid, k] of kacheln) {
      if (!sichtbar.has(sid)) { k.track.detach(k.video); k.div.remove(); kacheln.delete(sid); }
    }

    // Teilnehmerliste
    el.anzahl.textContent = '(' + leute.length + ')';
    el.teilnehmer.replaceChildren(...leute.map((p) => zeile(p, sprecher.has(p.identity))));

    // Knöpfe unten
    const lp = room.localParticipant;
    knopf(el.mikrofon, lp.isMicrophoneEnabled, 'Mikrofon aus', 'Mikrofon an');
    el.mikrofon.disabled = room.state !== LK.ConnectionState.Connected || (!lp.isMicrophoneEnabled && !darfSprechen());
    el.mikrofon.title = !darfSprechen() ? 'Erst nach Freigabe durch den Kursleiter – heb die Hand.' : '';
    knopf(el.kamera, lp.isCameraEnabled, 'Kamera aus', 'Kamera an');
    knopf(el.hand, meineHand, '✋ Hand senken', '✋ Hand heben');
    knopf(el.teilen, lp.isScreenShareEnabled, 'Teilen beenden', 'Bildschirm teilen');
  }

  function knopf(b, an, textAn, textAus) {
    b.classList.toggle('an', !!an);
    b.textContent = an ? textAn : textAus;
  }

  function buehneSetzen(track, name) {
    if (track === buehnenSpur) {
      el.buehneName.textContent = track ? name : '';
      return;
    }
    if (buehnenSpur) buehnenSpur.detach(el.buehne);
    buehnenSpur = track;
    if (track) track.attach(el.buehne);
    else el.buehne.srcObject = null;
    el.buehneLeer.hidden = !!track;
    el.buehneName.textContent = track ? name : '';
  }

  function zeile(p, spricht) {
    const li = document.createElement('li');
    if (spricht) li.classList.add('spricht');
    const mik = document.createElement('span');
    const an = p.isMicrophoneEnabled;
    mik.className = 'mik' + (an ? '' : ' aus');
    mik.textContent = an ? '🎤' : '🔇';
    mik.title = an ? 'Mikrofon an' : 'Mikrofon aus';
    const name = document.createElement('span');
    name.className = 'name';
    name.textContent = nameVon(p) + (p === room.localParticipant ? ' (du)' : '');
    li.append(mik, name);
    if (istLeiter(p)) {
      const m = document.createElement('span');
      m.className = 'marke';
      m.textContent = 'Kursleiter';
      li.appendChild(m);
    }
    if (haende.has(p.identity)) {
      const h = document.createElement('span');
      h.textContent = '✋';
      h.title = 'meldet sich';
      li.appendChild(h);
    }
    if (ichLeite() && p !== room.localParticipant && !istLeiter(p)) {
      const steuer = document.createElement('div');
      steuer.className = 'steuer';
      if (freigabe.pflicht) {
        const erlaubt = freigabe.erlaubt.has(p.identity);
        steuer.appendChild(kleinerKnopf(erlaubt ? 'Freigabe entziehen' : 'Sprechen erlauben',
          () => freigabeUmschalten(p)));
      }
      if (an) steuer.appendChild(kleinerKnopf('Stumm', () => stummSchalten(p)));
      steuer.appendChild(kleinerKnopf('Entfernen …', () => entfernen(p), 'gefahr'));
      li.appendChild(steuer);
    }
    return li;
  }

  function kleinerKnopf(text, aktion, art) {
    const b = document.createElement('button');
    b.type = 'button';
    b.className = 'klein' + (art ? ' ' + art : '');
    b.textContent = text;
    b.addEventListener('click', aktion);
    return b;
  }

  // ------------------------------------------------------------ Verbindung zu Python
  if (!LK) {
    dialog('Die Bibliothek für den Kursraum fehlt (livekit-client).');
    return;
  }
  if (typeof QWebChannel === 'undefined' || !window.qt) {
    dialog('Diese Seite läuft nur im Fenster „Kursraum“ von Bony\'s Agents.');
    return;
  }
  new QWebChannel(qt.webChannelTransport, (kanal) => {
    bruecke = kanal.objects.bruecke;
    bruecke.karte.connect(start);
    bruecke.antwort.connect(antwort);
    bruecke.schliessen.connect(gehen);
    bruecke.bereit();
  });
}());
