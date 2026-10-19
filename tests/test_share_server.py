# SPDX-License-Identifier: GPL-3.0-or-later
"""Schulungs-Freigabe: Code, Zertifikat/Fingerabdruck, nur lesend, Fehlversuche, Warteschlange,
Abbruch und Fortsetzen des Downloads, mDNS-Einträge (ohne Code)."""

import hashlib
import http.client
import json
import ssl
import threading
import time
from pathlib import Path

import pytest

from bonys_agents import bonysfile, mdns, share, templates
from bonys_agents.trainer import announce, share_server

pytestmark = pytest.mark.kursleiter


def _bundle(tmp_path: Path, size: int = 3 * 1024 * 1024 + 123) -> Path:
    disk = tmp_path / "disk.qcow2"
    disk.write_bytes(b"QFI\xfb" + bytes(range(256)) * (size // 256) + b"x" * (size % 256))
    t = templates.Template(path=tmp_path, name="kurs", arch="x86_64", apps=["brave"], description="Kurs")
    m = bonysfile.build_manifest(t, creator="Kursleitung", version="1.0", disk_size=disk.stat().st_size,
                                 disk_sha256=hashlib.sha256(disk.read_bytes()).hexdigest(), virtual_size=2**30,
                                 debian="13.1", versions={}, removed=[])
    return bonysfile.write_bundle(tmp_path / "kurs-1.0.bonys", m, disk)


@pytest.fixture
def running(tmp_path):
    s = share_server.Share(_bundle(tmp_path), port=0, bind="127.0.0.1", advertise=False, max_downloads=2)
    s.start()
    yield s
    s.stop()


def _target(s: share_server.Share, code=None, fp=None) -> share.Target:
    return share.parse_target(f"127.0.0.1:{s.port}", s.code if code is None else code,
                              s.fingerprint if fp is None else fp)


# ---------- Code ----------
def test_new_code_format():
    codes = {share_server.new_code() for _ in range(50)}
    assert len(codes) > 45
    for c in codes:
        assert len(c) == 9 and c[:4].isdigit() and c[4] == "-" and all(x in share.CODE_LETTERS for x in c[5:])
        assert share.normalize_code(c.lower()) == c

def test_certificate_is_valid_and_unique():
    c1, k1 = share_server.make_certificate()
    c2, _k2 = share_server.make_certificate()
    assert c1 != c2 and hashlib.sha256(c1).digest() != hashlib.sha256(c2).digest()
    share_server.server_context(c1, k1)  # OpenSSL akzeptiert Zertifikat und Schlüssel
    pem = ssl.DER_cert_to_PEM_cert(c1)
    assert "BEGIN CERTIFICATE" in pem


# ---------- Server und Client ----------
def test_info_download_and_fingerprint(running, tmp_path):
    info = share.fetch_info(_target(running))
    assert info.fingerprint == running.fingerprint and info.size == running.size
    assert info.manifest["name"] == "kurs" and info.file_name == "kurs-1.0.bonys"
    steps = []
    out = share.download(info, tmp_path / "laden", progress=lambda p, f, m: steps.append((p, f)))
    assert hashlib.sha256(out.read_bytes()).hexdigest() == running.sha256
    assert steps[-1] == ("verify", 1) and not list((tmp_path / "laden").glob("*.teil*"))
    assert [p.status for p in running.participants.values()] == ["fertig"]
    # die geladene Datei lässt sich wie eine kopierte lesen
    assert bonysfile.read_manifest(out)["creator"] == "Kursleitung"


def test_wrong_code_rejected_and_locked(running):
    with pytest.raises(share.WrongCode):
        share.fetch_info(_target(running, code="0000-AAAA"))
    for _ in range(share.MAX_FAILS_PER_ADDR - 1):
        with pytest.raises(share.WrongCode):
            share.fetch_info(_target(running, code="0000-AAAA"))
    # jetzt gesperrt – auch der richtige Code geht eine Weile nicht
    with pytest.raises(share.ShareError, match="warten"):
        share.fetch_info(_target(running))
    with pytest.raises(share.WrongCode, match="Code"):
        share.fetch_info(_target(running, code=""))


def test_fingerprint_mismatch_is_refused(running):
    with pytest.raises(share.FingerprintMismatch):
        share.fetch_info(_target(running, fp="00" * 32))


def _raw(s: share_server.Share, method: str, path: str, code: str | None = None) -> tuple[int, bytes]:
    conn = http.client.HTTPSConnection("127.0.0.1", s.port, timeout=10, context=share.client_context())
    conn.request(method, path, headers={share.CODE_HEADER: s.code if code is None else code})
    resp = conn.getresponse()
    body = resp.read()
    conn.close()
    return resp.status, body


def test_read_only_and_nothing_else_reachable(running):
    assert _raw(running, "POST", f"{share.API}/download")[0] == 405
    assert _raw(running, "PUT", f"{share.API}/info")[0] == 405
    for path in ("/", "/etc/passwd", f"{share.API}/../../manifest.json", f"{share.API}/info/../download2",
                 "/bonys/v1/files/disk.qcow2"):
        assert _raw(running, "GET", path)[0] == 404, path
    status, body = _raw(running, "GET", f"{share.API}/info")
    assert status == 200 and json.loads(body)["file"]["sha256"] == running.sha256
    assert _raw(running, "GET", f"{share.API}/info", code="falsch")[0] == 403


def test_kurspaket_in_der_schulung(tmp_path, datadir, monkeypatch):
    """Kurspaket mit der Vorlage: Teilnehmer holt es (gleicher Fingerabdruck), meldet nur Lektion und geschafft."""
    from test_kurspaket import paket_ordner

    from bonys_agents import kurse, kurspaket

    monkeypatch.setattr(kurspaket, "mitgeliefert_dirs", lambda: [])
    paket = kurspaket.laden(paket_ordner(tmp_path / "pakete"))
    daten = kurse.paket_packen(paket)
    s = share_server.Share(_bundle(tmp_path), port=0, bind="127.0.0.1", advertise=False,
                           kurspaket=(daten, {"paket_id": paket.id, "name": paket.name, "version": paket.version,
                                              "lektionen": len(paket.lektionen)}))
    s.start()
    try:
        # ohne Code: nichts
        assert _raw(s, "GET", f"{share.API}/kurspaket", code="falsch")[0] == 403
        info = share.fetch_info(_target(s))
        assert info.kurspaket["paket_id"] == "test-paket" and info.kurspaket["lektionen"] == 3
        assert info.kurspaket["sha256"] == hashlib.sha256(daten).hexdigest()
        geladen = share.kurspaket_holen(info)
        uebernommen = kurse.paket_uebernehmen(geladen, info.kurspaket["paket_id"], info.kurspaket["sha256"])
        assert uebernommen.herkunft == kurspaket.KURS
        share.fortschritt_melden(info, 1, True)
        [p] = s.participants.values()
        assert (p.lektion, p.geschafft) == (2, True)
        # nur gültige Meldungen, nur klein, nur mit Code
        with pytest.raises(share.ShareError):
            share.fortschritt_melden(info, 7, True)          # Lektion 8 gibt es nicht
        conn = http.client.HTTPSConnection("127.0.0.1", s.port, timeout=10, context=share.client_context())
        conn.request("POST", f"{share.API}/fortschritt", body=b"x" * 2000,
                     headers={share.CODE_HEADER: s.code, "Content-Type": "application/json"})
        assert conn.getresponse().status == 413
        conn.close()
        assert _raw(s, "POST", f"{share.API}/fortschritt", code="falsch")[0] in (403, 413)
        assert _raw(s, "PUT", f"{share.API}/fortschritt")[0] == 405
        assert (p.lektion, p.geschafft) == (2, True)
    finally:
        s.stop()


def test_ohne_kurspaket_kein_fortschritt(running):
    assert _raw(running, "GET", f"{share.API}/kurspaket")[0] == 404
    assert _raw(running, "POST", f"{share.API}/fortschritt")[0] == 405
    assert share.fetch_info(_target(running)).kurspaket is None


def test_cancel_and_resume_download(running, tmp_path):
    info = share.fetch_info(_target(running))
    cancel = threading.Event()

    def progress(phase, frac, msg):
        if phase == "download" and frac > 0.3:
            cancel.set()

    dest = tmp_path / "laden"
    with pytest.raises(bonysfile.Cancelled):
        share.download(info, dest, progress=progress, cancel=cancel)
    part = dest / "kurs-1.0.bonys.teil"
    have = part.stat().st_size
    assert 0 < have < info.size
    out = share.download(info, dest)  # setzt fort (HTTP-Range)
    assert hashlib.sha256(out.read_bytes()).hexdigest() == running.sha256
    assert any("fortgesetzt ab" in e for e in running.events)


def test_resume_discards_part_of_other_file(running, tmp_path):
    info = share.fetch_info(_target(running))
    dest = tmp_path / "laden"
    dest.mkdir()
    (dest / "kurs-1.0.bonys.teil").write_bytes(b"alt" * 1000)
    (dest / "kurs-1.0.bonys.teil.json").write_text(json.dumps({"sha256": "0" * 64, "size": 1}), encoding="utf-8")
    out = share.download(info, dest)
    assert hashlib.sha256(out.read_bytes()).hexdigest() == running.sha256


def test_corrupt_download_is_rejected(running, tmp_path, monkeypatch):
    info = share.fetch_info(_target(running))
    info.sha256 = "1" * 64  # Datei passt nicht zur angekündigten Prüfsumme
    monkeypatch.setattr(running, "sha256", "1" * 64)
    with pytest.raises(share.ShareError, match="Prüfsumme"):
        share.download(info, tmp_path / "laden")
    assert not list((tmp_path / "laden").glob("*.bonys"))


def test_queue_limits_parallel_downloads(tmp_path):
    s = share_server.Share(_bundle(tmp_path), port=0, bind="127.0.0.1", advertise=False, max_downloads=1)
    a, b, c = (s.participant(f"10.0.0.{i}", f"pc{i}") for i in (1, 2, 3))
    assert s.acquire(a) == 0
    assert s.acquire(b) == 1 and s.acquire(c) == 2 and b.status == "wartet"
    s.release()
    assert s.acquire(c) == 1  # c fragt zuerst – aber b steht vorn
    assert s.acquire(b) == 0
    s.release()
    assert s.acquire(c) == 0


def test_queue_over_http(tmp_path):
    s = share_server.Share(_bundle(tmp_path), port=0, bind="127.0.0.1", advertise=False, max_downloads=1)
    s.start()
    try:
        s.active = 1  # ein anderer Teilnehmer lädt gerade
        info = share.fetch_info(_target(s))
        seen = []

        def progress(phase, frac, msg):
            seen.append(phase)
            if phase == "queue" and seen.count("queue") == 2:
                s.release()  # der andere ist fertig

        out = share.download(info, tmp_path / "laden", progress=progress, retry_wait=0.2)
        assert "queue" in seen and out.exists()
    finally:
        s.stop()


def test_share_ends_automatically(tmp_path):
    s = share_server.Share(_bundle(tmp_path), port=0, bind="127.0.0.1", advertise=False)
    s.start()
    s.deadline = time.monotonic() - 1
    assert s.stopped.wait(5) and "Zeit abgelaufen" in s.stop_reason
    with pytest.raises(share.ShareError):
        share.fetch_info(_target(s))


def test_port_in_use_gives_clear_error(running):
    other = share_server.Share(running.file, port=running.port, bind="127.0.0.1", advertise=False,
                               sha256=running.sha256)
    with pytest.raises(share.ShareError, match="Port"):
        other.start()


# ---------- Kurs-Protokoll ----------
def test_newer_participant_is_told_to_wait_for_teacher(running, monkeypatch):
    monkeypatch.setattr(share, "PROTOCOL", share.PROTOCOL + 1)   # nur der Teilnehmer ist neuer
    with pytest.raises(share.ProtocolMismatch, match="Der Kursleiter sollte Bony's Agents aktualisieren"):
        share.fetch_info(_target(running))
    assert any("Kurs-Protokoll passt nicht" in e for e in running.events)


def test_newer_teacher_is_explained(running, monkeypatch):
    monkeypatch.setattr(share_server, "PROTOCOL", share.PROTOCOL + 1)   # nur der Kursleiter ist neuer
    with pytest.raises(share.ProtocolMismatch, match="Der Teilnehmer sollte Bony's Agents aktualisieren"):
        share.fetch_info(_target(running))


# ---------- mDNS ----------
def test_mdns_records_roundtrip_without_code(running):
    adv = announce.Advertiser("kurs 1.0", running.port, ["192.168.1.5", "fe80::1"],
                          {"name": "kurs", "version": "1.0", "creator": "K", "fp": running.fingerprint})
    flags, questions, records = mdns.parse(adv.response())
    assert flags & 0x8000 and not questions
    found = mdns.collect(records)
    assert len(found) == 1
    f = found[0]
    assert f.port == running.port and f.addresses == ["192.168.1.5"] and f.address == f"192.168.1.5:{running.port}"
    assert f.txt["fp"] == running.fingerprint and f.txt["name"] == "kurs"
    assert running.code not in adv.response().decode("latin-1")
    _f, q, _r = mdns.parse(mdns.query())
    assert adv.answers(q) and q[0][0] == mdns.SERVICE.lower()
    assert not adv.answers([("_http._tcp.local", mdns.T_PTR, 1)])
    # die Adresse aus dem Netz des Fragenden zuerst (nicht Docker oder VPN)
    adv.addresses = ["172.17.0.1", "10.20.30.2", "192.168.178.105"]
    assert mdns.collect(mdns.parse(adv.response(near="192.168.178.40"))[2])[0].addresses[0] == "192.168.178.105"
    assert mdns.order(["172.17.0.1", "10.8.0.1"], "10.8.0.7") == ["10.8.0.1", "172.17.0.1"]
    # Abmelden: TTL 0 → nicht mehr gefunden
    assert mdns.collect(mdns.parse(adv.response(ttl=0))[2]) == []


def test_cache_reuses_bundle_until_template_changes(datadir, tmp_path):
    from bonys_agents import vm

    d = templates.templates_dir(vm.vms_dir()) / "kurs"
    d.mkdir(parents=True)
    (d / "disk.qcow2").write_bytes(b"QFI\xfb" + b"\0" * 100)
    t = templates.Template(path=d, name="kurs", created="2026-10-01T00:00:00+00:00")
    t.save()
    assert share_server.cached_bundle(t) is None
    target = share_server.cache_target(t, "1.0")
    target.write_bytes(_bundle(tmp_path).read_bytes())
    sha = share_server.remember_cache(t, target)
    assert share_server.cached_bundle(t) == (target, sha)
    t.created = "2026-10-02T00:00:00+00:00"   # Vorlage neu erstellt → Zwischenspeicher veraltet
    assert share_server.cached_bundle(t) is None


def test_cli_parses_share():
    from bonys_agents import cli

    a = cli.build_parser().parse_args(["share", "kurs", "--port", "47111", "--timeout", "30", "--max-downloads", "8"])
    assert (a.name, a.port, a.timeout, a.max_downloads) == ("kurs", 47111, 30, 8)
