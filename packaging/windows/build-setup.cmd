@echo off
rem Baut BonysAgents-Setup-<Version>.exe (Doppelklick genuegt)
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0build-setup.ps1"
