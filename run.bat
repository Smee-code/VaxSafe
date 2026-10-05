@echo off
rem Starts VaxSafe on this computer for local use (debug mode on).
cd /d "%~dp0"
set VAXSAFE_DEBUG=1
python manage.py migrate --noinput
start "" http://127.0.0.1:8000
python manage.py runserver 127.0.0.1:8000
