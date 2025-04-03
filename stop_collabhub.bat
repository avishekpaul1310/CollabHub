@echo off
echo Stopping CollabHub Components...

taskkill /FI "WINDOWTITLE eq Redis Server" /T /F
taskkill /FI "WINDOWTITLE eq Celery Worker" /T /F
taskkill /FI "WINDOWTITLE eq Celery Beat" /T /F
taskkill /FI "WINDOWTITLE eq Daphne Server" /T /F

echo All components stopped!
