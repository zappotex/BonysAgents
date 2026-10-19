#!/bin/bash
# Prüfung: ~/Kurs/einkaufsliste.txt existiert und enthält „Käse“ (Vorlage aus Bony's Agents)
datei="$HOME"/Kurs/einkaufsliste.txt
test -s "$datei" || exit 1
grep -qiF -- 'Käse' "$datei"
