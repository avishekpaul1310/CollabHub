@echo off
echo Starting CollabHub Components...

:: Start Redis Server
start cmd /k "title Redis Server && cd /d C:\Users\Avishek Paul\Downloads\Redis-x64-5.0.14.1 && redis-server.exe"

:: Start Celery Worker
start cmd /k "title Celery Worker && cd /d C:\Users\Avishek Paul\CollabHub && venv\Scripts\activate && celery -A collabhub worker --pool=solo -l info"

:: Start Celery Beat
start cmd /k "title Celery Beat && cd /d C:\Users\Avishek Paul\CollabHub && venv\Scripts\activate && celery -A collabhub beat -l info"

:: Start Daphne Server (replacing Django dev server)
start cmd /k "title Daphne Server && cd /d C:\Users\Avishek Paul\CollabHub && venv\Scripts\activate && daphne -p 8000 collabhub.asgi:application"

echo All components started!