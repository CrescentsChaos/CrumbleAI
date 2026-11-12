@echo off
cd /d "%~dp0"
echo Starting Crumble in SHARE mode. Windows may ask to allow network access: click Allow (private networks).
python Crumble.py --share
pause
