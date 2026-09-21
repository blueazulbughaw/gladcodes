# CLAUDE.md — GladCodes

Permanent rules for anyone (human or Claude) working on this repo. These are
not suggestions — they encode decisions that were deliberate and should not
be silently "cleaned up".

## What this is

GladCodes (glad.codes) is a single Flask app serving a public building-in-public
site, a public metrics dashboard, and a hidden custom CMS at `/gc-admin/`.
No separate frontend build, no Node.js at runtime — Namecheap shared hosting
runs this only through Passenger (`passenger_wsgi.py`).

## Hard rules — do not violate

- **Never link `/gc-admin/` from any public template, nav, footer, sitemap,
  or robots "allow" rule.** It is discovered by URL only. Every response
  under `/gc-admin/` gets `X-Robots-Tag: noindex, nofollow` (see
  `app.py::add_admin_noindex_header`) and its templates carry
  `<meta name="robots" content="noindex,nofollow">`.
- **Silent-redirect auth rule.** If the JWT cookie is missing, invalid, or
  expired, redirect to the login page with no message, no flash, no query
  param explaining why. The login page itself gives no hints about why the
  visitor landed there (no "session expired", no branding beyond a plain
  form). This is deliberate: never leak that an admin panel exists or why
  a request was rejected.
- **No Node.js, no JS build step, ever.** Interactivity is vanilla JS.
  Charts are Chart.js loaded from CDN. Icons are Lucide from CDN. If a task
  seems to need a bundler, find a CDN-script way to do it instead.
- **All DB access goes through `database/db.py`.** Parameterized queries
  only — never string-format SQL. No ORM.
- **Never `DROP DATABASE`.** `database/schema.sql` only ever uses
  `CREATE TABLE IF NOT EXISTS` plus idempotent seed inserts guarded by
  `WHERE NOT EXISTS (...)`. Re-running the file must be safe.
- **Secrets only in `.env`**, never in code, templates, or committed files.
  `.env.example` documents every variable with no real values.
- Markdown → HTML for journal posts is always sanitized with `bleach`
  before rendering. Never render raw Markdown output directly.
- CSRF protection is required on every admin POST. Upload endpoints
  validate file type and size before touching disk; uploaded files get
  randomized filenames.
- GitHub API calls must degrade gracefully: on any failure (rate limit,
  timeout, network error), hide the GitHub section — never break the page.
  Responses are cached (`github_cache` table, 1 hour TTL) so a page load
  never blocks on GitHub.

## Design tokens (don't reinvent these)

- Fonts: Space Grotesk 600/700 (headings/hero), Inter 400/500/600
  (body/UI), Caveat (script accent lines only) — all via Google Fonts CDN
  with `display=swap`.
- Palette (CSS variables, one tokens file):
  `--navy:#1A2E44` `--teal:#0E8A8A` `--aqua:#5EC4C4` `--ocean:#3F88C5`
  `--sand:#FAF6EF` `--cream:#FFFDF8` `--card:#FFFFFF`
  `--success:#3BA55D` `--warn:#E7A93C`
- Cards: soft shadows, 12–16px radius.
- Respect `prefers-reduced-motion`: disable fade-ins, hover lifts,
  progress-bar fills, and count-up animations when set.
- Positioning: every page should quietly answer "why hire Glad" — software
  engineer, TPM, MBA-MIS, founder who ships, community leader.

## Local dev (PowerShell only — this is a Windows machine)

No `&&`, no `source`. Use:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env   # then fill in real values
flask run
```

## Deploy (Namecheap / cPanel)

- SSH: port 21098, user `gladcodes`.
- cPanel Git Version Control clone → cPanel "Setup Python App"
  (application root `gladcodes_app`, application URL `/`, startup file
  `passenger_wsgi.py`) → set env vars in the app panel → in the app's venv,
  `pip install -r requirements.txt` → `python create_admin.py <username>`
  on the server.
- To restart after a deploy: touch `~/gladcodes_app/tmp/restart.txt`
  (or use the cPanel "Restart" button, which does the same thing).
- Passenger is the **only** way Python runs here — there is no standalone
  `python app.py` server in production.

## Database

- Names are verbatim and must never be changed casually: DB
  `gladcodes_maindb`, user `gladcodes_admn`, host `localhost`.
- Password lives only in `.env` (`DB_PASSWORD`) — never hardcode it.

## GitHub cache pattern

`services/github.py` checks `github_cache` (keyed by `cache_key`, e.g.
`profile:<username>`) before calling the GitHub API. A row older than
`GITHUB_CACHE_TTL_SECONDS` (1 hour) is treated as stale. On any API failure,
return `None`/`[]` and let the caller hide the section — never raise up
into a page render.

## Phase 2

Tutorials, Videos, Instagram/Reels, and the PDF library are fully built
(admin editors + public pages). Only the API keys panel remains a "Coming
soon" admin-nav stub with no table of its own — there's no real API surface
yet to gate access to (`blueprints/api/` is still just stubs).

- **Tutorials**: same shape as Journal (Markdown + live preview, slug,
  cover image, draft/published), plus `series_name` for grouping. Public at
  `/tutorials` (filterable by series) and `/tutorials/<slug>` (shows a
  "more in this series" list). Code/terminal snippets use ordinary fenced
  Markdown code blocks — no syntax highlighting, just distinct dark
  monospace styling via the same `.prose pre/code` rules as Journal.
- **Videos**: a `simple_crud` resource (title, YouTube URL, description,
  date, sort order). Public at `/videos`. `services/content.youtube_embed_url()`
  (exposed as the `|youtube_embed` Jinja filter) turns any common YouTube
  URL shape into an embeddable `/embed/<id>` URL.
- **Instagram/Reels**: also a `simple_crud` resource. `embed_code` is
  rendered with `|safe`, **not** bleach-sanitized — sanitizing would strip
  the `<script>` tag Instagram's own embed snippet needs to actually
  render. Safe because only the authenticated admin can write this field
  (unlike Journal/Tutorial Markdown, which is sanitized as defense in
  depth even though it's also admin-only). Folded into the `/videos` page
  as a second section per its own request, not a separate `/instagram` page.
- **PDF library**: bespoke editor (`blueprints/admin/pdf_library.py`,
  reuses `uploads.save_resume_pdf` for validation) since `simple_crud`
  doesn't support file uploads. Public list lives on `/resources`
  (replacing its old placeholder). `is_product`+`price` items show a price
  tag and link to `/contact` instead of a real purchase flow — no payment
  integration yet, so "interested? send a message" is the actual CTA.

## Where the spec is silent (choices made and why)

- DB helper lives at `database/db.py` (not `services/db.py`) so it sits
  next to `schema.sql` — one place for everything database-related.
- `app.py` both defines `create_app()` (factory, used by tests/dev) and
  instantiates a module-level `app` so `passenger_wsgi.py` can do the
  literal `from app import app as application` the spec asked for.
- Blueprint template folders are namespaced (`templates/public/`,
  `templates/admin/`) to keep admin and public markup from ever
  accidentally sharing a template file.
- The build order's step 4 only named "the home-page dashboard teaser", but
  three home-page sections (Currently Learning, Toolbox, Community) were
  never assigned to any explicit step. They're simple DB-driven lists with
  no backend dependency (unlike the dashboard/GitHub/newsletter sections,
  which need Chart.js, an external API, and a capture endpoint
  respectively), so they were folded into step 4 to bring the home page to
  full completeness before moving on to auth/admin work.
- Chart data passed to templates is always shaped `{"labels": [...], "data": [...]}`,
  never `{"values": [...]}`. Jinja's `foo.values` resolves to Python's
  `dict.values()` bound method before it falls back to `foo["values"]`, so a
  `values` key silently renders a function object instead of the data —
  this broke the dashboard once already. Keep the same `data`-keyed shape
  for the GitHub commit-activity series when it lands in step 5.
- CSRF uses the double-submit-cookie pattern (`blueprints/admin/csrf.py`),
  not Flask-WTF's session-token approach — there's no server-side session
  to hang a token on, since auth is a stateless JWT cookie. A random token
  is set as a (non-HttpOnly) cookie and must be echoed back as a hidden
  `csrf_token` form field; a forged cross-site POST can't read the cookie
  to produce a matching field value. Every admin form needs that hidden
  field or its POST gets a flat 400.
- `blueprints/admin/simple_crud.py` is one generic, whitelisted CRUD engine
  covering flat sort_order-based tables (timeline, projects, learning,
  toolbox, community, links, stats) instead of one near-identical route
  file per table. `resource` (the URL segment) is only ever used as a
  `RESOURCES` dict lookup key — never concatenated into SQL — so the
  dynamic table/column names in its generated SQL can't be
  attacker-influenced even though they aren't parameterized (SQL can't
  parameterize identifiers, only values). Add new simple flat-table
  editors here before writing a bespoke route file.
- `database/db.utc_now()` is the one place the app writes "now" to a
  DATETIME column from Python — use it instead of MySQL's `NOW()` (server
  local time; see the GitHub cache pattern above for why that broke
  things) whenever the app, not the DB, decides the timestamp (e.g.
  journal `published_at`, NOW card `updated_at`).
- The `skills` table (resume page) follows the exact same flat
  category+sort_order grouping pattern as `timeline_milestones`
  (grouped by month): one row per skill, grouped by `category` in
  sort_order/first-appearance order at render time. Adding a brand-new
  category is just adding a skill row with a new category name via the
  `skills` simple_crud resource; a category disappears once its last
  skill is deleted. No separate categories table.
- The contact form (`/contact`) sends mail via Python's stdlib
  `smtplib`/`email`, not a paid transactional-email API — the
  production host is cPanel shared hosting, where Exim already accepts
  local unauthenticated submission on `localhost:25` for the account's
  domains, so no external service or API key is needed by default.
  `services/mail.py`'s `send_contact_email()` is configurable via
  `SMTP_HOST`/`SMTP_PORT`/`SMTP_USER`/`SMTP_PASSWORD` env vars for hosts
  that require authenticated submission instead, and always returns
  `False` on any failure rather than raising — the route shows a
  friendly error, never a crash. The form also carries a simple
  honeypot field (`company`, absolutely positioned off-screen); a
  filled honeypot silently "succeeds" without sending mail rather than
  telling the bot it was caught.
