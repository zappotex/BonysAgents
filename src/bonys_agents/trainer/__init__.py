# SPDX-License-Identifier: GPL-3.0-or-later
"""Kursleiter-Funktionen – nur in „Bony's Agents Kursleiter“.

Vorlage im Netzwerk freigeben (``share_server``), Vorführen (``present``, mit noVNC unter ``resources/novnc``),
Hilfe-Anfragen annehmen (``helpdesk``), mDNS-Ankündigung (``announce``), Kommandozeile (``cli``) und Oberfläche
(``gui``). Die Anwender-Version wird ohne dieses Unterpaket gebaut; das Hauptpaket importiert es nur, wenn
``bonys_agents.edition.IS_TRAINER`` gilt.
"""
