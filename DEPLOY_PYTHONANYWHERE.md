# Deploying VaxSafe on PythonAnywhere

This guide puts VaxSafe online at `https://YOURUSERNAME.pythonanywhere.com`. Replace `YOURUSERNAME` with your PythonAnywhere username everywhere below.

It takes about 15 minutes. You need a PythonAnywhere account; a free "Beginner" account is enough for a demo.

## Before you start

- **Don't upload** `db.sqlite3`, `.env`, `credentials.txt` or the `media/` folder from your computer. They hold the demo patients, local settings and demo passwords. The live site gets a fresh, empty database.
- The project needs **Python 3.12 or newer** (Django 6.1 requires it).

## 1. Upload the project

**Option A: from GitHub (recommended).** Push the project to a GitHub repository. The `.gitignore` already leaves out the files above. Then open a **Bash console** on PythonAnywhere (Dashboard → Consoles → Bash) and run:

```bash
cd ~
git clone https://github.com/YOUR-GITHUB-NAME/VaxSafe.git
```

**Option B: as a zip file.** On your computer, zip the VaxSafe folder *without* `db.sqlite3`, `.env`, `credentials.txt`, `media/` and any `__pycache__` folders. On PythonAnywhere, open the **Files** tab, upload the zip to `/home/YOURUSERNAME/`, then in a Bash console run:

```bash
cd ~
unzip VaxSafe.zip
```

Either way, the project should end up at `/home/YOURUSERNAME/VaxSafe`, with `manage.py` directly inside it.

## 2. Create a virtual environment and install packages

In the Bash console:

```bash
cd ~/VaxSafe
mkvirtualenv vaxsafe --python=python3.13
pip install -r requirements.txt
```

If `python3.13` isn't offered on your account, use `python3.12`. The prompt now starts with `(vaxsafe)`. If you open a new console later, run `workon vaxsafe` first.

## 3. Create the settings file (.env)

Generate a secret key:

```bash
python -c "import secrets; print(secrets.token_urlsafe(50))"
```

Copy the output, then create the settings file:

```bash
cp .env.example .env
nano .env
```

Set these three lines, then save with **Ctrl+O**, **Enter**, and exit with **Ctrl+X**:

```
VAXSAFE_DEBUG=0
VAXSAFE_SECRET_KEY=paste-the-generated-key-here
VAXSAFE_ALLOWED_HOSTS=YOURUSERNAME.pythonanywhere.com
```

## 4. Set up the database and static files

```bash
python manage.py migrate
python manage.py collectstatic --noinput
python manage.py seed
python manage.py check --deploy
```

`seed` loads the exposure categories, vaccine types, barangays and storage units, and creates the three accounts (`admin`, `staff`, `personnel`) with **random passwords that are printed once**. Copy them somewhere safe straight away. (Use `python manage.py seed --demo` instead only if you want the 70 sample patients for a demonstration; that uses the shared demo password `VaxSafe@2026`.)

`check --deploy` should end with `System check identified no issues`.

## 5. Create the web app

1. Open the **Web** tab and click **Add a new web app**.
2. Click **Next** on the domain screen.
3. Choose **Manual configuration** (not "Django"), then the same Python version you used in step 2.
4. On the web app's page, fill in these sections:

**Code**
- Source code: `/home/YOURUSERNAME/VaxSafe`
- Working directory: `/home/YOURUSERNAME/VaxSafe`

**WSGI configuration file:** click the link (it ends in `_wsgi.py`), delete everything in it, and paste the contents of [`deploy/pythonanywhere_wsgi.py`](deploy/pythonanywhere_wsgi.py). Change `YOURUSERNAME` and click **Save**.

**Virtualenv:** enter `vaxsafe` and click the check mark. It expands to `/home/YOURUSERNAME/.virtualenvs/vaxsafe`.

**Static files:** add two entries.

| URL | Directory |
|---|---|
| `/static/` | `/home/YOURUSERNAME/VaxSafe/staticfiles` |
| `/media/` | `/home/YOURUSERNAME/VaxSafe/media` |

**Security:** turn on **Force HTTPS**.

5. Click the green **Reload** button at the top, then open `https://YOURUSERNAME.pythonanywhere.com`.

## 6. After the first sign-in

1. Sign in as `admin` with the password from step 4.
2. Open **Settings** and enter the center's name, address and logo, and check the alert limits.
3. Review the vaccine types and barangays, and change them to match the center.
4. Give the `staff` and `personnel` passwords to the right people, or create named accounts for each person under **Users** and deactivate the generic ones.

## Updating the site later

```bash
workon vaxsafe
cd ~/VaxSafe
git pull                      # or upload the changed files
pip install -r requirements.txt
python manage.py migrate
python manage.py collectstatic --noinput
```

Then click **Reload** on the Web tab. Your data in `db.sqlite3` is kept.

## Backups

Use **Backup** in the app (admin only) to download the database regularly, or download `/home/YOURUSERNAME/VaxSafe/db.sqlite3` from the Files tab.

## If something goes wrong

| What you see | What to do |
|---|---|
| "Something went wrong :-(" | Open the **Error log** link on the Web tab and read the last lines. |
| `VAXSAFE_SECRET_KEY is not set` in the error log | The `.env` file is missing or not in `/home/YOURUSERNAME/VaxSafe`. Repeat step 3. |
| "Bad Request (400)" | `VAXSAFE_ALLOWED_HOSTS` in `.env` doesn't match the address in the browser. Fix it and reload. |
| Page has no styling | The `/static/` mapping is missing or wrong, or `collectstatic` wasn't run. Check step 4 and step 5. |
| "CSRF verification failed" when signing in | Make sure you open the site with `https://` and that `VAXSAFE_ALLOWED_HOSTS` is correct. Reload the web app after any change to `.env`. |
| `ModuleNotFoundError: No module named 'django'` | The virtualenv path on the Web tab is wrong, or step 2 was skipped. |

## Free account notes

- A free web app stops after 3 months unless you click **Run until 3 months from today** on the Web tab. PythonAnywhere emails you a reminder.
- Free accounts have a daily CPU allowance. Normal use is fine; generating many large PDF reports in a row uses the most.
