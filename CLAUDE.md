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

- SSH: port 21098, user `gladcodes`, key `~/.ssh/id_ed25519_gladcodes`
  (`ssh -i ~/.ssh/id_ed25519_gladcodes -o IdentitiesOnly=yes -p 21098 gladcodes@glad.codes`).
  Repo lives at `~/gladcodes_app` (= the Passenger app root). Server Python
  is **3.9** (`~/virtualenv/gladcodes_app/3.9/`), so no 3.10+ syntax
  (`X | None`, `match`). Deploying over SSH = `git pull --ff-only`, pip
  install into that venv, `touch tmp/restart.txt` — the same tasks
  `.cpanel.yml` runs.
- cPanel Git Version Control clone → cPanel "Setup Python App"
  (application root `gladcodes_app`, application URL `/`, startup file
  `passenger_wsgi.py`) → set env vars in the app panel → in the app's venv,
  `pip install -r requirements.txt` → `python create_admin.py <username>`
  on the server.
- To restart after a deploy: touch `~/gladcodes_app/tmp/restart.txt`
  (or use the cPanel "Restart" button, which does the same thing).
- **Routine deploy = push, then cPanel Git Version Control → Update from
  Remote → Deploy HEAD Commit.** `.cpanel.yml` pip-installs requirements
  into the app's virtualenv, (re)installs the reminder cron line, and
  touches `tmp/restart.txt`. On restart `passenger_wsgi.py` runs
  `database/schema.sql` (it's idempotent) and creates push keys if
  missing — so schema changes need no manual import. Keep it that way:
  anything a deploy needs should be automated here, not a manual step.
- Why the app does setup itself instead of the deploy shell or cron: env
  vars set in the cPanel Python App panel (DB password, etc.) are only
  visible to Passenger, not to `.cpanel.yml` tasks or cron. So the
  reminder cron job just `curl`s `/gc-admin/reminders/tick` (auth-exempt,
  always 204, sends only an already-due reminder, at most once via
  `checkin_app_state.reminder_last_sent`).
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
- The private daily check-in (`/gc-admin/today`, `blueprints/admin/checkin.py`,
  `daily_checkins` table) is the admin's landing page after login until
  today's row exists — the point is to make the site the first thing
  opened each morning instead of social media. Mood, meds, gratitude, etc.
  are personal: nothing in `blueprints/public` ever reads this table.
  "Today" is the calendar day in the timezone the Today page's browser
  last reported (`checkin_app_state.local_timezone`, sent with check-in
  saves and push subscribes), falling back to `LOCAL_TIMEZONE`; `tzdata` is in requirements because Windows
  dev machines have no system tz database for `zoneinfo`.
- The public dashboard's GitHub chart (`services/github.get_weekly_activity`)
  counts **pushes**, not commits, from the public events feed — GitHub
  removed commit counts from PushEvent payloads in 2025. Same
  `{"labels", "data"}` shape and `github_cache` pattern as everything else.
- The admin is an installable PWA ("Today", start URL `/gc-admin/today`)
  with Web Push reminders, modeled on Secret Santa's setup. To keep the
  admin URL secret, **nothing PWA-related lives in `/static/`**: the
  manifest and service worker are routes in `blueprints/admin/app_shell.py`
  (`/gc-admin/manifest.webmanifest`, `/gc-admin/sw.js`), and the install/
  push JS is inline in `today.html`. The `<link rel="manifest">` and SW
  registration are in `_shell.html` (authenticated pages), never
  `base_admin.html`, so the login page stays bare. Manifest + SW are the
  auth-exempt admin endpoints besides login and the reminder tick (`routes.PUBLIC_ENDPOINTS`)
  so installs and background SW updates survive JWT expiry. The SW has no
  fetch handler/offline cache on purpose — admin pages must always be live.
- `url_for('static', ...)` appends `?v=<mtime>` (`app.py::static_cache_bust`)
  so deploys aren't masked by browser-cached CSS/JS.
- Login has a "Remember this device" checkbox: a `REMEMBER_DEVICE_DAYS`
  (30) JWT instead of the default 30 minutes, so the installed Today app
  and reminder taps don't bounce to login. JWTs are stateless, so the only
  way to revoke remembered devices is rotating `JWT_SECRET`. The checkbox
  is plain text with no branding, consistent with the bare login page.
- Auto-generated VAPID keys live in `checkin_app_state` (a deliberate,
  narrow exception to "secrets only in .env": they're created by the app,
  not by a person, and panel env vars can't be written programmatically).
  Never put them — or anything private — in `site_settings`, whose rows go
  to every public template as `settings`. Env `VAPID_*` vars override.
- **Personal area is separate from the website CMS.** Sidebar has a
  "Personal" group (Today, My dashboard `/gc-admin/me`, Medicines) above
  the "Website" group (Site dashboard `/gc-admin/` + all site editors).
  After login: Today until checked in, then My dashboard.
- Today **autosaves** (whole form POSTed with `X-Requested-With: fetch` on
  every change; `<noscript>` Save fallback). Medicine doses save per
  checkbox via `/gc-admin/today/dose`. `medications` is a `simple_crud`
  resource; `doses_per_day` (1–8) = number of checkboxes; `frequency`
  daily / every_other_day / weekly (weekday of `start_date`) / as_needed.
- Sleep and Instagram time are **never typed in** — phone automations POST
  to `/gc-admin/track/sleep` and `/gc-admin/track/app` with
  `Authorization: Bearer <checkin_app_state.ingest_token>` (shown on My
  dashboard). Those two endpoints skip JWT + CSRF (`routes.TOKEN_ENDPOINTS`)
  and 404 on a bad token. They write `sleep_logs` / `app_sessions`, not
  `daily_checkins`, so an early sleep upload doesn't count as checked in.
- Period tracking = the `period_day` checkbox; runs of days (bridging one
  forgotten day) become periods in `services/tracking.periods_from_days`,
  with average cycle + predicted next start on My dashboard.
- App ideas are a standalone list (`app_ideas` simple_crud resource,
  Personal nav), not a daily question; the old `daily_checkins.app_ideas`
  column is kept but unused (schema.sql copied its contents over once).
  The daily "What did you learn today?" answer is `daily_checkins.learnings`.
- `simple_crud` resources can set `"group_by": "<column>"` (skills use
  `category`): the admin list shows one card grid per group under a
  heading, in first-appearance sort_order (same as the public page), with
  a "+ Add to <group>" link that pre-fills the column. Drag-reorder works
  within a group; a drop saves the order of every card on the page so
  sort_order stays one sequence. New rows in grouped resources get
  `MAX(sort_order)+1`, so adding one never jumps its group to the top.
- Every admin page except Today and the site dashboard shows a **Back**
  button (`_shell.html` `before_content` block, `routes.back_url()`). It
  goes to the page's *parent* (edit/create → its list, personal pages →
  Today, `<x>_edit/_new` → `<x>_index`, else site dashboard), never
  `history.back()`: that lands on just-saved forms, and the installed app
  has no browser back button. Sidebar "View site" opens `/` in a new tab
  (admin may link to the public site, never the reverse).
- **Home is an AIDA landing page** (gpt-taste principles, adapted to this
  stack: no React/Tailwind, brand fonts kept, no stock photos). Asymmetric
  hero with the NOW card floating over it (pulled up under the nav so the
  ambient mesh runs behind the pill); a gapless 4-col bento (metrics 2x2 +
  stats 2x1 + learning 2x1, GitHub 4x1 only when it loads,
  `grid-auto-flow: dense`); pinned-split timeline; projects horizontal
  accordion; journal; community as still cards (no marquee, by request);
  one navy CTA. The "why hire me" scrub statement and the toolbox were
  removed from home by request: toolbox_items is no longer shown on any
  public page (its admin editor still exists). No eyebrow meta-labels on
  home. Motion = `static/js/home-motion.js` (GSAP 3.12.5 + ScrollTrigger
  from cdnjs, same as resume) and must stay a progressive enhancement:
  every section reads fully with no JS and under reduced motion. Don't
  GSAP-animate elements that also carry `.reveal` (they fight over opacity).
- Public nav is a floating glass pill (`base.css`); `main` has
  `overflow-x: clip` (not `hidden`, which would break sticky/pinning).
- **Interior pages share the landing-page treatment** (pages.css): page-hero
  with the same ambient mesh, pulled up under the nav, big balanced H1 and a
  CSS rise-in (`.hero-fade` elements on about/resume keep their own JS
  stagger); roomier sections; no eyebrow meta-labels anywhere public; a
  shared closing CTA (`_closing_cta.html` via the `closing_cta` block in
  base_public, overridden empty on home/contact/resume, which have their own
  endings). Projects = accordion rows (`project_slice` macro, `|batch(4)`),
  Journal = newest post as a feature card, Dashboard = navy stats tile + 2-col
  chart bento (odd last chart spans both). Shared button variants, text
  links and journal/tutorial card styles live in base.css, not home.css.
- `animations.js` count-up only fires on elements that are **both**
  `.reveal` and `data-count-to` — put `.reveal` on the number itself, not
  its wrapper (the dashboard showed 0s for this reason).
- About and Resume follow the same language as the rest: About adds a
  by-the-numbers bento counted from `resume_timeline` rows (never typed
  in) and restyles the zig-zag timeline (navy squircle dots, sand
  background); Resume has hero actions, a sticky-pinned Experience split
  with role cards, and its own navy download band in the `closing_cta`
  block. Their cards are GSAP-animated by `resume-timeline.js`, so their
  hover only changes box-shadow: never add a CSS transform transition to
  an element GSAP tweens (it makes the tween lag).
- `/lets-connect` (links.html) is a link-in-bio: one centered panel on the
  page-hero ambient background (photo ring, socials, link cards), no
  closing CTA. Admins only enter label + URL in the Links editor; each
  card's icon and the small address hint are derived from the URL in the
  template (`link_icon`/`link_hint` macros). Lucide has no brand logos,
  so GitHub/LinkedIn/Instagram use `macros.social_icon`.
