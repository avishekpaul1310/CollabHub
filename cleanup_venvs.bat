@echo off
echo Removing unused virtual environments...
rmdir /s /q venv_fixed
rmdir /s /q venv
rmdir /s /q .venv
echo Done! Only venv_new has been kept.
pause
