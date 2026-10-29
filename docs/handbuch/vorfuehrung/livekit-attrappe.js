// SPDX-License-Identifier: GPL-3.0-or-later
// Attrappe von livekit-client für die Bildschirmfotos des Handbuchs (nur im Vorführmodus, nie im Programm).
//
// Sie stellt genau die Teile von „LivekitClient“ bereit, die resources/kursraum/kursraum.js benutzt, und spielt einen
// Kursraum mit erfundenen Teilnehmern vor: kein Server, kein Netz, keine echte Kamera. Statt Videos zeichnet sie
// Platzhalter (Anfangsbuchstabe auf Farbfläche) und für den geteilten Bildschirm ein Beispielbild.
//
// Gesteuert wird sie aus Python über window.Vorfuehrung (page().runJavaScript), z. B.
//   Vorfuehrung.chat('ben', 'Bei mir startet Hermes nicht.')   Vorfuehrung.hand('ben', true)
//   Vorfuehrung.daten('clara', 'hilfe-bitte', {an: true})        Vorfuehrung.getrennt('ROOM_DELETED')
'use strict';

(function () {
  const Source = { Camera: 'camera', Microphone: 'microphone', ScreenShare: 'screen_share' };
  const Kind = { Audio: 'audio', Video: 'video' };
  const ConnectionState = { Connected: 'connected', Disconnected: 'disconnected', Connecting: 'connecting' };
  const RoomEvent = {};
  for (const n of ['ParticipantConnected', 'ParticipantDisconnected', 'TrackSubscribed', 'TrackUnsubscribed',
    'TrackMuted', 'TrackUnmuted', 'TrackPublished', 'TrackUnpublished', 'LocalTrackPublished', 'LocalTrackUnpublished',
    'ParticipantMetadataChanged', 'ParticipantNameChanged', 'ActiveSpeakersChanged', 'DataReceived', 'Reconnecting',
    'SignalReconnecting', 'Reconnected', 'AudioPlaybackStatusChanged', 'MediaDevicesError', 'Disconnected']) {
    RoomEvent[n] = n;
  }
  const DisconnectReason = { PARTICIPANT_REMOVED: 4, ROOM_DELETED: 5, ROOM_CLOSED: 10, DUPLICATE_IDENTITY: 2 };

  // ---------------------------------------------------------------- Bilder (Platzhalter statt Kameras)
  const FARBEN = { eva: '#8e5bd6', anna: '#2f8f6b', ben: '#c4622d', clara: '#2d6fc4' };

  function kameraBild(name, farbe) {
    const c = document.createElement('canvas');
    c.width = 480; c.height = 270;
    const x = c.getContext('2d');
    x.fillStyle = farbe; x.fillRect(0, 0, c.width, c.height);
    x.fillStyle = 'rgba(255,255,255,0.18)';
    x.beginPath(); x.arc(240, 125, 70, 0, Math.PI * 2); x.fill();
    x.fillStyle = '#fff'; x.font = '600 76px sans-serif'; x.textAlign = 'center'; x.textBaseline = 'middle';
    x.fillText(name[0], 240, 128);
    x.font = '20px sans-serif'; x.fillStyle = 'rgba(255,255,255,0.8)';
    x.fillText(document.documentElement.lang === 'en' ? 'Camera (sample)' : 'Kamera (Beispiel)', 240, 235);
    return c;
  }

  function bildschirmBild() {
    // Beispiel: Bildschirm der Kursleiterin mit dem Agent-PC und einem Terminal, in dem Hermes läuft
    const c = document.createElement('canvas');
    c.width = 1600; c.height = 900;
    const x = c.getContext('2d');
    const zeichnen = (bild) => {
      if (bild) x.drawImage(bild, 0, 0, c.width, c.height);
      else { x.fillStyle = '#16314a'; x.fillRect(0, 0, c.width, c.height); }
      x.fillStyle = 'rgba(10,14,20,0.92)'; x.fillRect(0, 852, c.width, 48);
      x.fillStyle = '#e8eef5'; x.font = '22px sans-serif'; x.fillText('Menü    Brave    Telegram    Hermes Agent', 24, 884);
      x.fillText('10:15', c.width - 90, 884);
      // Terminal-Fenster
      x.fillStyle = 'rgba(0,0,0,0.35)'; x.fillRect(268, 128, 1080, 620);
      x.fillStyle = '#2b2f36'; x.fillRect(260, 120, 1080, 44);
      x.fillStyle = '#e8eef5'; x.font = '22px sans-serif'; x.fillText('Hermes Agent – Terminal', 280, 150);
      x.fillStyle = '#101418'; x.fillRect(260, 164, 1080, 576);
      x.font = '26px monospace';
      const zeilen = [
        ['#4cc38a', 'agent@agent-kursleitung:~$ hermes'],
        ['#93a4b8', '  Hermes Agent – bereit.'],
        ['#e8eef5', '> Lege eine Datei einkaufsliste.txt an mit'],
        ['#e8eef5', '  Brot, Milch und Äpfel.'],
        ['#f5a623', '  ✓ Datei ~/einkaufsliste.txt angelegt (3 Zeilen).'],
        ['#e8eef5', '> Zeig mir den Inhalt.'],
        ['#93a4b8', '  Brot'],
        ['#93a4b8', '  Milch'],
        ['#93a4b8', '  Äpfel'],
        ['#e8eef5', '> _'],
      ];
      zeilen.forEach(([farbe, text], i) => { x.fillStyle = farbe; x.fillText(text, 290, 214 + i * 50); });
    };
    zeichnen(null);
    const bild = new Image();
    bild.onload = () => zeichnen(bild);
    bild.src = 'vorfuehrung/hintergrund.jpg';
    return c;
  }

  // ---------------------------------------------------------------- Spuren und Teilnehmer
  let sidNr = 0;

  class Spur {
    constructor(kind, quelle, leinwand) {
      this.kind = kind;
      this.source = quelle;
      this.sid = 'TR_' + (++sidNr);
      this.leinwand = leinwand;
      this.strom = null;
      this.elemente = [];
    }
    _strom() {
      if (!this.strom && this.leinwand) {
        this.strom = this.leinwand.captureStream(2);
        // ein paar Punkte nachzeichnen, damit der Strom Bilder liefert
        const x = this.leinwand.getContext('2d');
        setInterval(() => { const d = x.getImageData(0, 0, 1, 1); x.putImageData(d, 0, 0); }, 400);
      }
      return this.strom;
    }
    attach(el) {
      const e = el || document.createElement(this.kind === Kind.Audio ? 'audio' : 'video');
      if (this.kind === Kind.Video) {
        e.autoplay = true; e.muted = true; e.playsInline = true;
        e.srcObject = this._strom();
      }
      this.elemente.push(e);
      return e;
    }
    detach(el) {
      const weg = el ? [el] : this.elemente.splice(0);
      for (const e of weg) e.srcObject = null;
      return weg;
    }
  }

  class Teilnehmer {
    constructor(identity, name, rolle) {
      this.identity = identity;
      this.name = name;
      this.metadata = rolle === 'kursleiter' ? JSON.stringify({ rolle: 'kursleiter' }) : '{}';
      this.spuren = new Map();   // quelle → {track, isMuted, trackSid, source}
    }
    _setzen(quelle, an, leinwand) {
      if (an) {
        const kind = quelle === Source.Microphone ? Kind.Audio : Kind.Video;
        const t = new Spur(kind, quelle, leinwand);
        this.spuren.set(quelle, { track: t, isMuted: false, trackSid: t.sid, source: quelle });
      } else {
        this.spuren.delete(quelle);
      }
    }
    getTrackPublication(quelle) { return this.spuren.get(quelle); }
    get isMicrophoneEnabled() { return this.spuren.has(Source.Microphone); }
    get isCameraEnabled() { return this.spuren.has(Source.Camera); }
    get isScreenShareEnabled() { return this.spuren.has(Source.ScreenShare); }
  }

  class Lokal extends Teilnehmer {
    constructor(room, identity, name, rolle) {
      super(identity, name, rolle);
      this.room = room;
    }
    async setMicrophoneEnabled(an) { this._setzen(Source.Microphone, an); this.room._melden(RoomEvent.LocalTrackPublished, {}); }
    async setCameraEnabled(an) {
      this._setzen(Source.Camera, an, an ? kameraBild(this.name, FARBEN[this.identity] || '#555') : null);
      this.room._melden(RoomEvent.LocalTrackPublished, {});
    }
    async setScreenShareEnabled(an) {
      this._setzen(Source.ScreenShare, an, an ? bildschirmBild() : null);
      this.room._melden(RoomEvent.LocalTrackPublished, {});
    }
    async publishData() { /* geht nirgends hin */ }
  }

  // ---------------------------------------------------------------- Raum
  let aktuellerRaum = null;

  class Room {
    constructor() {
      this.state = ConnectionState.Disconnected;
      this.remoteParticipants = new Map();
      this.activeSpeakers = [];
      this.canPlaybackAudio = true;
      this.hoerer = new Map();
      this.localParticipant = null;
      aktuellerRaum = this;
    }
    on(ereignis, fn) {
      if (!this.hoerer.has(ereignis)) this.hoerer.set(ereignis, []);
      this.hoerer.get(ereignis).push(fn);
      return this;
    }
    _melden(ereignis, ...werte) {
      for (const fn of this.hoerer.get(ereignis) || []) fn(...werte);
    }
    async connect(url) {
      const rolle = /vorfuehrung=kursleiter/.test(url) ? 'kursleiter' : 'teilnehmer';
      this.rolle = rolle;
      const leute = [
        ['eva', 'Eva', 'kursleiter'], ['anna', 'Anna', ''], ['ben', 'Ben', ''], ['clara', 'Clara', ''],
      ];
      const ich = rolle === 'kursleiter' ? 'eva' : 'anna';
      for (const [id, name, r] of leute) {
        if (id === ich) this.localParticipant = new Lokal(this, id, name, r);
        else this.remoteParticipants.set(id, new Teilnehmer(id, name, r));
      }
      const p = (id) => this.remoteParticipants.get(id);
      if (rolle === 'teilnehmer') {
        // Eva teilt ihren Bildschirm und spricht, Ben und Clara haben die Kamera an, Ben das Mikrofon
        p('eva')._setzen(Source.ScreenShare, true, bildschirmBild());
        p('eva')._setzen(Source.Microphone, true);
        p('eva')._setzen(Source.Camera, true, kameraBild('Eva', FARBEN.eva));
        p('ben')._setzen(Source.Camera, true, kameraBild('Ben', FARBEN.ben));
        p('ben')._setzen(Source.Microphone, true);
        p('clara')._setzen(Source.Camera, true, kameraBild('Clara', FARBEN.clara));
        this.activeSpeakers = [p('eva')];
      } else {
        p('anna')._setzen(Source.Camera, true, kameraBild('Anna', FARBEN.anna));
        p('anna')._setzen(Source.Microphone, true);
        p('ben')._setzen(Source.Camera, true, kameraBild('Ben', FARBEN.ben));
        p('clara')._setzen(Source.Camera, true, kameraBild('Clara', FARBEN.clara));
        p('clara')._setzen(Source.Microphone, true);
        this.activeSpeakers = [p('anna')];
      }
      this.state = ConnectionState.Connected;
    }
    async disconnect() {
      if (this.state === ConnectionState.Disconnected) return;
      this.state = ConnectionState.Disconnected;
      this._melden(RoomEvent.Disconnected, undefined);
    }
    async startAudio() { this.canPlaybackAudio = true; }
  }

  window.LivekitClient = {
    Room, Track: { Source, Kind }, ConnectionState, RoomEvent, DisconnectReason,
    ConnectionErrorReason: { NotAllowed: 1 },
    VideoPresets: { h540: { resolution: { width: 960, height: 540 } } },
    ScreenSharePresets: { h1080fps15: { resolution: { width: 1920, height: 1080 } } },
  };

  // ---------------------------------------------------------------- Steuerung aus Python
  const kodierer = new TextEncoder();
  window.Vorfuehrung = {
    daten(von, thema, inhalt) {
      const r = aktuellerRaum;
      r._melden(RoomEvent.DataReceived, kodierer.encode(JSON.stringify(inhalt)), r.remoteParticipants.get(von),
        undefined, thema);
    },
    chat(von, text) { this.daten(von, 'chat', { text }); },
    hand(von, oben) { this.daten(von, 'hand', { oben }); },
    eigeneKamera(an) { return aktuellerRaum.localParticipant.setCameraEnabled(an); },
    eigenesMikrofon(an) { return aktuellerRaum.localParticipant.setMicrophoneEnabled(an); },
    bildschirmTeilen(an) { return aktuellerRaum.localParticipant.setScreenShareEnabled(an); },
    verbindungWackelt() { aktuellerRaum._melden(RoomEvent.Reconnecting); },
    getrennt(grund) {
      const r = aktuellerRaum;
      r.state = ConnectionState.Disconnected;
      r._melden(RoomEvent.Disconnected, DisconnectReason[grund]);
    },
    klicken(id) { document.getElementById(id).click(); },
  };
}());
