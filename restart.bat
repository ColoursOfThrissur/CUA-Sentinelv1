@echo off
title Restart CUA-Sentinel
cd /d "%~dp0"
call "%~dp0launch.bat" --restart %*
