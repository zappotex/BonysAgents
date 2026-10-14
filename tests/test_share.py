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
    s = share.Share(_bundle(tmp_path), port=0, bind="127.0.0.1", advertise=False, max_downloads=2)
    s.start()
    yield s
    s.stop()


def _target(s: share.Share, code=None, fp=None) -> share.Target:
    return share.parse_target(f"127.0.0.1:{s.port}", s.code if code is None else code,
                              s.fingerprint if fp is None else fp)


# ---------- Code, Adresse ----------
def test_code_format_and_normalize():
    codes = {share.new_code() for _ in range(50)}
    assert len(codes) > 45
    for c in codes:
        assert len(c) == 9 and c[:4].isdigit() and c[4] == "-" and all(x in share.CODE_LETTERS for x in c[5:])
    assert share.normalize_code("4711-bony") == "4711-BONY"
    assert share.normalize_code(" 47 11 b0ny ") == "4711-BONY"   # Null im Buchstabenteil = O
    assert share.normalize_code("47O1BONY") == "4701-BONY"       # O im Zahlenteil = Null


def test_parse_target_variants():
    fp = "ab" * 32
    t = share.parse_target("192.168.1.5")
    assert (t.host, t.port, t.code, t.fingerprint) == ("192.168.1.5", share.DEFAULT_PORT, "", "")
    t = share.parse_target("kurs.local:5000", "4711bony")
    assert (t.host, t.port, t.code) == ("kurs.local", 5000, "4711-BONY")
    t = share.parse_target(share.share_link("10.8.0.1", 47111, "4711-BONY", fp))
    assert (t.host, t.port, t.code, t.fingerprint) == ("10.8.0.1", 47111, "4711-BONY", fp)
    t = share.parse_target("[fd00::5]:47110")
    assert t.host == "fd00::5" and t.netloc == "[fd00::5]:47110"
    with pytest.raises(ValueError):
        share.parse_target("")
    with pytest.raises(ValueError, match="Fingerabdruck"):
        share.parse_target("1.2.3.4", fingerprint="abc")


def test_certificate_is_valid_and_unique():
    c1, k1 = share.make_certificate()
    c2, _k2 = share.make_certificate()
    assert c1 != c2 and hashlib.sha256(c1).digest() != hashlib.sha256(c2).digest()
    share.server_context(c1, k1)  # OpenSSL akzeptiert Zertifikat und Schlüssel
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


def _raw(s: share.Share, method: str, path: str, code: str | None = None) -> tuple[int, bytes]:
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
    (dest / "kurs-1.0.bonys.teil.json").write_text(json.dumps({"sha256": "0" * 64, "size": 1}))
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
    s = share.Share(_bundle(tmp_path), port=0, bind="127.0.0.1", advertise=False, max_downloads=1)
    a, b, c = (s.participant(f"10.0.0.{i}", f"pc{i}") for i in (1, 2, 3))
    assert s.acquire(a) == 0
    assert s.acquire(b) == 1 and s.acquire(c) == 2 and b.status == "wartet"
    s.release()
    assert s.acquire(c) == 1  # c fragt zuerst – aber b steht vorn
    assert s.acquire(b) == 0
    s.release()
    assert s.acquire(c) == 0


def test_queue_over_http(tmp_path):
    s = share.Share(_bundle(tmp_path), port=0, bind="127.0.0.1", advertise=False, max_downloads=1)
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
    s = share.Share(_bundle(tmp_path), port=0, bind="127.0.0.1", advertise=False)
    s.start()
    s.deadline = time.monotonic() - 1
    assert s.stopped.wait(5) and "Zeit abgelaufen" in s.stop_reason
    with pytest.raises(share.ShareError):
        share.fetch_info(_target(s))


def test_port_in_use_gives_clear_error(running):
    other = share.Share(running.file, port=running.port, bind="127.0.0.1", advertise=False, sha256=running.sha256)
    with pytest.raises(share.ShareError, match="Port"):
        other.start()


# ---------- mDNS ----------
def test_mdns_records_roundtrip_without_code(running):
    adv = mdns.Advertiser("kurs 1.0", running.port, ["192.168.1.5", "fe80::1"],
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
    assert share.cached_bundle(t) is None
    target = share.cache_target(t, "1.0")
    target.write_bytes(_bundle(tmp_path).read_bytes())
    sha = share.remember_cache(t, target)
    assert share.cached_bundle(t) == (target, sha)
    t.created = "2026-10-02T00:00:00+00:00"   # Vorlage neu erstellt → Zwischenspeicher veraltet
    assert share.cached_bundle(t) is None


def test_cli_parses_share_and_join():
    from bonys_agents import cli

    p = cli.build_parser()
    a = p.parse_args(["share", "kurs", "--port", "47111", "--timeout", "30", "--max-downloads", "8"])
    assert (a.name, a.port, a.timeout, a.max_downloads) == ("kurs", 47111, 30, 8)
    a = p.parse_args(["join", "192.168.1.5:47110", "4711-BONY", "--create", "pc-1"])
    assert (a.address, a.code, a.create) == ("192.168.1.5:47110", "4711-BONY", "pc-1")
    a = p.parse_args(["join"])
    assert a.address is None
