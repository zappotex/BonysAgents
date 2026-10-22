#!/bin/bash
# Lösung – läuft nur bei „Kurspaket prüfen“ im Editor, nie bei Teilnehmern
cd ~/Agent-Dateien/pdf && pdfunite rechnung-maerz.pdf rechnung-april.pdf rechnungen-gesamt.pdf
