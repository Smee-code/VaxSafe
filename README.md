# VaxSafe

A management system for an animal bite treatment center. It covers patient registration and triage, bite assessment, vaccination schedules, vaccine inventory and the cold chain, and reports.

Built with Python and Django on the server side, and plain HTML, CSS and JavaScript in the browser. Data is stored in SQLite, in a single file (`db.sqlite3`), so the whole system can run from a USB drive.

## Getting started

Requires Python 3.12 or newer.

For local use, turn on debug mode by creating a file named `.env` in the project folder containing the line `VAXSAFE_DEBUG=1`. (`run.bat` does this for you.) Without it, VaxSafe starts in production mode and asks for a secret key. See `.env.example` for every setting.

```bash
pip install -r requirements.txt
echo VAXSAFE_DEBUG=1 > .env
python manage.py migrate
python manage.py seed            # default categories, vaccines, barangays and the 3 accounts
python manage.py seed --demo     # optional: 70 sample patients, stock and temperature logs
python manage.py runserver
```

Then open http://127.0.0.1:8000. On Windows, you can double-click `run.bat` instead.

Demo accounts (all use the password `VaxSafe@2026`; change them before real use):

| Username | Role |
|---|---|
| `admin` | Administrator |
| `staff` | Health Staff |
| `personnel` | Authorized Personnel |

## Roles

| Feature | Admin | Health Staff | Authorized Personnel |
|---|---|---|---|
| User management, settings, backup | ✅ | ❌ | ❌ |
| Patients, triage, bite assessment | ✅ | ✅ | ❌ (summary figures only) |
| Vaccination schedule and appointments | ✅ | ✅ | ❌ (completion figures only) |
| Inventory and temperature log | ✅ | ✅ | 👁 view only, no patient names |
| Reports | ✅ all | ✅ completion, stock, expiry, temperature | ✅ all |
| Audit log | ✅ | ❌ | ❌ |

## How it works

- **Case workflow:** register the patient, record the visit and triage, complete the bite assessment, then create the schedule. The schedule's dates come from the vaccine's regimen. For example, the PVRV regimen `0,3,7,14,28` creates 5 doses counted from Day 0.
- **Recording a dose** takes one dose out of the chosen lot and adds an entry to the usage log. Expired or empty lots can't be selected.
- **Missed doses:** a scheduled dose shows as *Overdue* once its date has passed. Staff can record it late, reschedule it, or mark it *Missed*. All of these appear under Appointments → Missed and overdue.
- **Alerts** (dashboard and the bell icon): low stock, lots expiring within the warning window, expired lots still in stock, temperatures outside the safe range, and storage units with no reading in the last 24 hours. Administrators set all the limits in Settings.
- **Audit log:** every create, update and delete on patients, visits, assessments, doses, stock, settings and users is recorded with who made it, when, the field changes and the IP address. Sign-ins, failed sign-ins and exports are recorded too.
- **Reports** can be filtered and exported to Excel or PDF, or printed. They contain aggregated figures only.

## Project layout

```
vaxsafe/      Django settings and URLs
accounts/     User model with roles, sign-in, user management
core/         Center settings, categories, barangays, audit log, alerts, dashboards, backup, seed command
clinic/       Patients, visits, bite assessments, doses, schedule generation, appointments
inventory/    Vaccine types, lots, stock movements, storage units, temperature logs
reports/      Report builders (shared by screen, Excel and PDF) and exporters
templates/    HTML templates
static/       CSS, JavaScript, and Chart.js (stored locally so it works offline)
```

## Backup and restore

Administrators can download the database or a JSON export from **Backup**. To restore a database backup, stop the server and replace `db.sqlite3` with the downloaded file.

## Deploying online (PythonAnywhere)

Step-by-step instructions are in [DEPLOY_PYTHONANYWHERE.md](DEPLOY_PYTHONANYWHERE.md). A ready-to-paste WSGI file is in [deploy/pythonanywhere_wsgi.py](deploy/pythonanywhere_wsgi.py).

## Deploying on the center's network

To serve VaxSafe from one PC to others on the same network over plain HTTP:

1. Copy `.env.example` to `.env` and set `VAXSAFE_DEBUG=0`, a generated `VAXSAFE_SECRET_KEY`, and `VAXSAFE_ALLOWED_HOSTS=<this PC's IP address>,localhost`. Also add `VAXSAFE_SECURE_COOKIES=0`, because sign-in cookies are HTTPS-only by default.
2. Run `python manage.py collectstatic`, then serve the app with a production server such as `waitress-serve --port=8000 vaxsafe.wsgi:application`.
3. Change every demo password.

## Planned features

- SMS reminders for upcoming and missed doses. The Appointments list already shows who to contact.
