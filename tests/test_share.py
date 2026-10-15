# SPDX-License-Identifier: GPL-3.0-or-later
"""Schulungen – Teilnehmer-Seite und gemeinsame Teile (beide Editionen, ohne Kursleiter-Server).

Das Zusammenspiel mit einem echten Server prüft ``test_share_server.py`` (nur Kursleiter-Version).
"""

import pytest

from bonys_agents import __version__, share


# ---------- Code, Adresse ----------
def test_normalize_code():
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


def test_local_addresses_skip_bridges_and_mark_vpn(monkeypatch):
    import socket as so
    from types import SimpleNamespace as NS

    import psutil

    def a(ip, mask="255.255.255.0"):
        return NS(family=so.AF_INET, address=ip, netmask=mask)
    monkeypatch.setattr(psutil, "net_if_addrs", lambda: {
        "lo": [a("127.0.0.1", "255.0.0.0")], "eno1": [a("192.168.178.5")], "docker0": [a("172.17.0.1")],
        "br-1a2b": [a("172.18.0.1")], "virbr0": [a("192.168.122.1")], "wg0": [a("10.8.0.2")],
        "kurs_vpn": [a("10.20.30.2", "255.255.255.255")]})
    addrs = share.local_addresses()
    assert addrs == ["192.168.178.5", "10.8.0.2", "10.20.30.2"]
    assert [share.address_kind(x) for x in addrs] == ["LAN", "VPN", "VPN"]


# ---------- Kurs-Protokoll ----------
def test_protocol_same_or_missing_is_fine():
    share.check_protocol(share.PROTOCOL)
    share.check_protocol(str(share.PROTOCOL), "0.18.0")
    share.check_protocol(None)          # ältere Versionen schicken keine Angabe → Protokoll 1
    assert share.remote_protocol("") == 1 and share.remote_protocol("x") == 0
    assert share.protocol_headers() == {share.PROTOCOL_HEADER: str(share.PROTOCOL), share.VERSION_HEADER: __version__}


def test_protocol_mismatch_says_who_should_update():
    with pytest.raises(share.ProtocolMismatch, match=r"Kursleiter \(Bony's Agents 9.0.0\) nutzt Version 2.*Der "
                                                     r"Teilnehmer sollte Bony's Agents aktualisieren"):
        share.check_protocol(share.PROTOCOL + 1, "9.0.0")
    with pytest.raises(share.ProtocolMismatch, match="Der Kursleiter sollte"):
        share.check_protocol(share.PROTOCOL + 1, we_are="Kursleiter")
    with pytest.raises(share.ProtocolMismatch, match="Der Kursleiter sollte"):
        share.check_protocol(0)


def test_cli_parses_join():
    from bonys_agents import cli

    p = cli.build_parser()
    a = p.parse_args(["join", "192.168.1.5:47110", "4711-BONY", "--create", "pc-1"])
    assert (a.address, a.code, a.create) == ("192.168.1.5:47110", "4711-BONY", "pc-1")
    a = p.parse_args(["join"])
    assert a.address is None
