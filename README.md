# GladCodes

Personal founder platform and building-in-public site for [glad.codes](https://glad.codes/).
One Flask app: public site, public metrics dashboard, and a hidden custom
CMS at `/gc-admin/`. See [CLAUDE.md](CLAUDE.md) for architecture rules.

## Local dev (Windows / PowerShell)

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env
# edit .env with real values (at minimum DB_PASSWORD)
```

Create the database tables (import `database/schema.sql` via phpMyAdmin,
or locally via the MySQL client of your choice), then:

```powershell
flask --app app run --debug
```

Visit http://127.0.0.1:5000/ .

To create the admin login:

```powershell
python create_admin.py <username>
```

## Deploy (Namecheap cPanel)

1. cPanel → Git Version Control → clone this repo.
2. cPanel → Setup Python App: application root `gladcodes_app`,
   application URL `/`, startup file `passenger_wsgi.py`.
3. Set environment variables in the app panel (same keys as `.env.example`).
4. In the app's venv: `pip install -r requirements.txt`.
5. `python create_admin.py <username>` on the server.
6. Restart: `touch ~/gladcodes_app/tmp/restart.txt` (or the cPanel button).

Full rules and rationale: [CLAUDE.md](CLAUDE.md).
