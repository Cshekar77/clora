# Clora and Co - Flask E-commerce Store

Flask + SQLite (SQLAlchemy) + Bootstrap 5. Database (`clora.db`) and sample data are created automatically on first run.

## Demo credentials
| Role | Email | Password |
|---|---|---|
| Admin | admin@cloraandco.com | Admin@123 |
| Customer | customer@example.com | Customer@123 |

## Run locally
    pip install -r requirements.txt
    python app.py        # http://127.0.0.1:5000

## Deploy on PythonAnywhere
1. Upload `clora_and_co.zip` (Files tab) and in a Bash console: `unzip clora_and_co.zip`
2. Create a virtualenv (optional but recommended):
   `mkvirtualenv clora --python=python3.10 && pip install -r ~/clora_and_co/requirements.txt`
3. Web tab -> **Add a new web app** -> Manual configuration -> pick the same Python version.
4. Set **Source code** and **Working directory** to `/home/<username>/clora_and_co`; set **Virtualenv** to `/home/<username>/.virtualenvs/clora`.
5. Open the **WSGI configuration file** link, replace its contents with `wsgi.py` from this project, and set `PROJECT_DIR` and `SECRET_KEY`.
6. Under **Static files** add URL `/static/` -> `/home/<username>/clora_and_co/static`.
7. Click **Reload**. Visit `<username>.pythonanywhere.com`.

## Before going live
- Change the admin password (sign in as admin, or edit in `seed()`), and set a strong `SECRET_KEY`.
- Payment is simulated; integrate a gateway (Stripe/Razorpay) for real payments.
- Change currency via `CURRENCY` in `app.py`.
- Uploaded images are stored in `static/uploads/`.
