# GladCodes

Personal founder platform and building-in-public site for [glad.codes](https://glad.codes/).
One Flask app: public site, public metrics dashboard, and a hidden custom
CMS at `/gc-admin/`. See [CLAUDE.md](CLAUDE.md) for architecture rules.

## What's here

- **Public site**: home (hero, NOW card, animated stats, build-in-public
  timeline, projects, journal preview, dashboard teaser, currently
  learning, toolbox, live GitHub repos, community, newsletter),
  `/journal` (search + tag filter) and `/journal/<slug>`, `/projects`,
  `/dashboard` (Chart.js), `/resume`, `/speaking`, `/lets-connect`, `/about`
  and `/resources` (Phase 2 placeholders).
- **Admin CMS** at `/gc-admin/` (never linked publicly — see CLAUDE.md):
  JWT-cookie auth with a silent-redirect gate, CSRF-protected editors for
  every Phase 1 content type (NOW card, timeline, projects, journal with
  live Markdown preview, metrics, learning, toolbox, community, links,
  resume upload, speaking, subscribers + CSV export, settings), and a
  Phase 2 nav marked "Coming soon" (tutorials, videos, Instagram/Reels,
  PDF library, API keys — schema exists, no UI yet).
- **SEO**: JSON-LD (Person + WebSite), Open Graph/Twitter tags,
  `sitemap.xml`, `robots.txt`.

## Local dev (Windows / PowerShell)

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env
# edit .env with real values (at minimum DB_PASSWORD)
```

Create the database tables (import `database/schema.sql` via phpMyAdmin,
or locally via the MySQL client of your choice — it's idempotent, safe to
re-run), then:

```powershell
flask --app app run --debug
```

Visit http://127.0.0.1:5000/ for the public site, http://127.0.0.1:5000/gc-admin/
for the CMS.

Create the admin login (required before the CMS is usable):

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
