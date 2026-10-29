#!/bin/bash
# Check: ~/Course/shopping-list.txt exists and contains "cheese" (template from Bony's Agents)
datei="$HOME"/Course/shopping-list.txt
test -s "$datei" || exit 1
grep -qiF -- 'cheese' "$datei"
