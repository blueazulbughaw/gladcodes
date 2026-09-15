-- GladCodes schema (MySQL / phpMyAdmin-importable).
-- Safe to re-run: uses CREATE TABLE IF NOT EXISTS and INSERT ... ON DUPLICATE
-- KEY UPDATE / guarded INSERTs for seed rows. Never DROP DATABASE.

SET NAMES utf8mb4;

-- ============================================================================
-- Phase 1 tables
-- ============================================================================

CREATE TABLE IF NOT EXISTS admin_users (
    id INT AUTO_INCREMENT PRIMARY KEY,
    username VARCHAR(50) NOT NULL UNIQUE,
    password_hash VARCHAR(255) NOT NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
-- No seed row: created via `python create_admin.py` on the server.

CREATE TABLE IF NOT EXISTS now_card (
    id INT PRIMARY KEY,
    location VARCHAR(255) NOT NULL,
    building TEXT NOT NULL,
    drinking VARCHAR(255) NOT NULL,
    reading VARCHAR(255) NOT NULL,
    goal_this_week TEXT NOT NULL,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

INSERT INTO now_card (id, location, building, drinking, reading, goal_this_week)
SELECT * FROM (SELECT
    1 AS id,
    'Manila, Philippines' AS location,
    'GladCodes — my founder platform and building-in-public site' AS building,
    'Iced oat milk latte' AS drinking,
    'The Mom Test by Rob Fitzpatrick' AS reading,
    'Ship the public metrics dashboard' AS goal_this_week
) AS tmp
WHERE NOT EXISTS (SELECT 1 FROM now_card WHERE id = 1);

CREATE TABLE IF NOT EXISTS timeline_milestones (
    id INT AUTO_INCREMENT PRIMARY KEY,
    month_label VARCHAR(20) NOT NULL,
    title VARCHAR(255) NOT NULL,
    description TEXT,
    is_done TINYINT(1) NOT NULL DEFAULT 0,
    sort_order INT NOT NULL DEFAULT 0
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

INSERT INTO timeline_milestones (month_label, title, description, is_done, sort_order)
SELECT * FROM (SELECT 'Jan 2026' AS month_label, 'Idea + validation' AS title, 'Talked to 20 engineers about what a founder-in-public site should show.' AS description, 1 AS is_done, 1 AS sort_order UNION ALL
    SELECT 'Feb 2026', 'Design system', 'Locked palette, typography, and component style.', 1, 2 UNION ALL
    SELECT 'Mar 2026', 'Public site v1', 'Home, journal, and projects pages live.', 1, 3 UNION ALL
    SELECT 'Apr 2026', 'Metrics dashboard', 'Chart.js dashboard wired to real data.', 1, 4 UNION ALL
    SELECT 'May 2026', 'Custom CMS', 'Admin editors for every section, no more hand-editing SQL.', 1, 5 UNION ALL
    SELECT 'Jun 2026', 'GitHub integration', 'Live repo + commit activity on the home page.', 0, 6 UNION ALL
    SELECT 'Jul 2026', 'Newsletter + launch', 'Public launch and first newsletter subscribers.', 0, 7
) AS tmp
WHERE NOT EXISTS (SELECT 1 FROM timeline_milestones);

CREATE TABLE IF NOT EXISTS projects (
    id INT AUTO_INCREMENT PRIMARY KEY,
    title VARCHAR(255) NOT NULL,
    description TEXT,
    icon VARCHAR(50) NOT NULL DEFAULT 'code',
    status ENUM('in_progress', 'experimental', 'launched') NOT NULL DEFAULT 'in_progress',
    progress_pct TINYINT UNSIGNED NOT NULL DEFAULT 0,
    url VARCHAR(500),
    sort_order INT NOT NULL DEFAULT 0,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

INSERT INTO projects (title, description, icon, status, progress_pct, url, sort_order)
SELECT * FROM (SELECT 'GladCodes' AS title, 'This site — a founder platform and building-in-public log.' AS description, 'rocket' AS icon, 'in_progress' AS status, 70 AS progress_pct, 'https://glad.codes/' AS url, 1 AS sort_order UNION ALL
    SELECT 'CommitPulse', 'A small GitHub activity visualizer I use on my own dashboard.', 'activity', 'experimental', 35, NULL, 2 UNION ALL
    SELECT 'FaithTech Manila Toolkit', 'Volunteer tooling for a local FaithTech chapter''s events.', 'heart-handshake', 'launched', 100, NULL, 3
) AS tmp
WHERE NOT EXISTS (SELECT 1 FROM projects);

CREATE TABLE IF NOT EXISTS journal_posts (
    id INT AUTO_INCREMENT PRIMARY KEY,
    slug VARCHAR(255) NOT NULL UNIQUE,
    title VARCHAR(255) NOT NULL,
    excerpt TEXT,
    content_markdown LONGTEXT NOT NULL,
    cover_image VARCHAR(500),
    tags VARCHAR(500),
    status ENUM('draft', 'published') NOT NULL DEFAULT 'draft',
    published_at DATETIME,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

INSERT INTO journal_posts (slug, title, excerpt, content_markdown, tags, status, published_at)
SELECT * FROM (SELECT
    'why-im-building-in-public' AS slug,
    'Why I''m building in public' AS title,
    'I don''t know exactly what I''m doing. But writing it down in public keeps me honest.' AS excerpt,
    '# Why I''m building in public\n\nI don''t know exactly what I''m doing. But I''m doing it anyway, and writing it down keeps me honest about progress instead of just vibes.' AS content_markdown,
    'founder,journal' AS tags,
    'published' AS status,
    '2026-03-02 09:00:00' AS published_at
    UNION ALL SELECT
    'from-tpm-to-founder', 'From TPM to founder', 'Ten years of program management taught me more about shipping than any framework did.',
    '# From TPM to founder\n\nProgram management across Japan and Hong Kong taught me how to ship under constraints. Now I''m applying that to my own roadmap.',
    'career,founder', 'published', '2026-03-16 09:00:00'
    UNION ALL SELECT
    'first-month-of-metrics', 'What my first month of metrics taught me', 'Tracking coding hours weekly made the "I''m not doing enough" feeling measurable, and mostly wrong.',
    '# What my first month of metrics taught me\n\nOnce I started logging coding hours and features shipped, the anxious feeling of not doing enough turned into an actual number I could act on.',
    'metrics,building-in-public', 'published', '2026-04-10 09:00:00'
    UNION ALL SELECT
    'community-over-clout', 'Community over clout', 'Why I show up for Google Developer Groups and Women Techmakers instead of just posting online.',
    '# Community over clout\n\nShowing up in person for GDG and Women Techmakers events has taught me more than any amount of solo posting.',
    'community', 'published', '2026-05-05 09:00:00'
) AS tmp
WHERE NOT EXISTS (SELECT 1 FROM journal_posts);

CREATE TABLE IF NOT EXISTS stat_counters (
    id INT AUTO_INCREMENT PRIMARY KEY,
    label VARCHAR(100) NOT NULL,
    value INT NOT NULL DEFAULT 0,
    suffix VARCHAR(20) NOT NULL DEFAULT '',
    sort_order INT NOT NULL DEFAULT 0
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

INSERT INTO stat_counters (label, value, suffix, sort_order)
SELECT * FROM (SELECT 'Projects building' AS label, 3 AS value, '' AS suffix, 1 AS sort_order UNION ALL
    SELECT 'Journal posts published', 4, '', 2 UNION ALL
    SELECT 'GitHub commits this year', 248, '+', 3 UNION ALL
    SELECT 'Coding streak', 57, ' days', 4
) AS tmp
WHERE NOT EXISTS (SELECT 1 FROM stat_counters);

CREATE TABLE IF NOT EXISTS chart_metrics (
    id INT AUTO_INCREMENT PRIMARY KEY,
    metric_key VARCHAR(100) NOT NULL,
    label VARCHAR(255),
    period_label VARCHAR(50) NOT NULL,
    value DECIMAL(10, 2) NOT NULL,
    sort_order INT NOT NULL DEFAULT 0
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

INSERT INTO chart_metrics (metric_key, label, period_label, value, sort_order)
SELECT * FROM (
    SELECT 'coding_hours_weekly' AS metric_key, 'Coding hours' AS label, 'W1' AS period_label, 8 AS value, 1 AS sort_order UNION ALL
    SELECT 'coding_hours_weekly', 'Coding hours', 'W2', 11, 2 UNION ALL
    SELECT 'coding_hours_weekly', 'Coding hours', 'W3', 9, 3 UNION ALL
    SELECT 'coding_hours_weekly', 'Coding hours', 'W4', 14, 4 UNION ALL
    SELECT 'coding_hours_weekly', 'Coding hours', 'W5', 12, 5 UNION ALL
    SELECT 'coding_hours_weekly', 'Coding hours', 'W6', 16, 6 UNION ALL
    SELECT 'coding_hours_weekly', 'Coding hours', 'W7', 15, 7 UNION ALL
    SELECT 'coding_hours_weekly', 'Coding hours', 'W8', 18, 8 UNION ALL
    SELECT 'features_shipped_monthly', 'Features shipped', 'Jan', 2, 9 UNION ALL
    SELECT 'features_shipped_monthly', 'Features shipped', 'Feb', 3, 10 UNION ALL
    SELECT 'features_shipped_monthly', 'Features shipped', 'Mar', 5, 11 UNION ALL
    SELECT 'features_shipped_monthly', 'Features shipped', 'Apr', 4, 12 UNION ALL
    SELECT 'features_shipped_monthly', 'Features shipped', 'May', 6, 13 UNION ALL
    SELECT 'beta_users', 'Beta users', 'current', 42, 14 UNION ALL
    SELECT 'beta_users', 'Beta users', 'target', 100, 15 UNION ALL
    SELECT 'learning_metrics', 'Hours studied', 'Rust', 22, 16 UNION ALL
    SELECT 'learning_metrics', 'Hours studied', 'System design', 30, 17 UNION ALL
    SELECT 'learning_metrics', 'Hours studied', 'Public speaking', 14, 18
) AS tmp
WHERE NOT EXISTS (SELECT 1 FROM chart_metrics);

CREATE TABLE IF NOT EXISTS learning_progress (
    id INT AUTO_INCREMENT PRIMARY KEY,
    skill VARCHAR(255) NOT NULL,
    progress_pct TINYINT UNSIGNED NOT NULL DEFAULT 0,
    sort_order INT NOT NULL DEFAULT 0
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

INSERT INTO learning_progress (skill, progress_pct, sort_order)
SELECT * FROM (SELECT 'Rust' AS skill, 40 AS progress_pct, 1 AS sort_order UNION ALL
    SELECT 'System design', 65, 2 UNION ALL
    SELECT 'Public speaking', 55, 3 UNION ALL
    SELECT 'Growth marketing', 25, 4
) AS tmp
WHERE NOT EXISTS (SELECT 1 FROM learning_progress);

CREATE TABLE IF NOT EXISTS toolbox_items (
    id INT AUTO_INCREMENT PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    icon VARCHAR(50) NOT NULL DEFAULT 'wrench',
    url VARCHAR(500),
    sort_order INT NOT NULL DEFAULT 0
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

INSERT INTO toolbox_items (name, icon, url, sort_order)
SELECT * FROM (SELECT 'VS Code' AS name, 'code-2' AS icon, 'https://code.visualstudio.com/' AS url, 1 AS sort_order UNION ALL
    SELECT 'Flask', 'flask-conical', 'https://flask.palletsprojects.com/', 2 UNION ALL
    SELECT 'Chart.js', 'bar-chart-3', 'https://www.chartjs.org/', 3 UNION ALL
    SELECT 'Figma', 'pen-tool', 'https://www.figma.com/', 4 UNION ALL
    SELECT 'GitHub', 'github', 'https://github.com/', 5
) AS tmp
WHERE NOT EXISTS (SELECT 1 FROM toolbox_items);

CREATE TABLE IF NOT EXISTS community_links (
    id INT AUTO_INCREMENT PRIMARY KEY,
    org_name VARCHAR(255) NOT NULL,
    url VARCHAR(500) NOT NULL,
    icon VARCHAR(50) NOT NULL DEFAULT 'users',
    sort_order INT NOT NULL DEFAULT 0
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

INSERT INTO community_links (org_name, url, icon, sort_order)
SELECT * FROM (SELECT 'Google Developer Groups' AS org_name, 'https://developers.google.com/community/gdg' AS url, 'users' AS icon, 1 AS sort_order UNION ALL
    SELECT 'Women Techmakers', 'https://womentechmakers.withgoogle.com/', 'users', 2 UNION ALL
    SELECT 'FaithTech', 'https://faithtech.com/', 'heart-handshake', 3 UNION ALL
    SELECT 'Filipinas in Computing', 'https://www.filipinasincomputing.org/', 'users', 4
) AS tmp
WHERE NOT EXISTS (SELECT 1 FROM community_links);

CREATE TABLE IF NOT EXISTS page_links (
    id INT AUTO_INCREMENT PRIMARY KEY,
    label VARCHAR(255) NOT NULL,
    url VARCHAR(500) NOT NULL,
    sort_order INT NOT NULL DEFAULT 0,
    is_visible TINYINT(1) NOT NULL DEFAULT 1
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

INSERT INTO page_links (label, url, sort_order, is_visible)
SELECT * FROM (SELECT 'GitHub' AS label, 'https://github.com/blueazulbughaw' AS url, 1 AS sort_order, 1 AS is_visible UNION ALL
    SELECT 'LinkedIn', 'https://www.linkedin.com/', 2, 1 UNION ALL
    SELECT 'Resume', '/resume', 3, 1 UNION ALL
    SELECT 'Journal', '/journal', 4, 1 UNION ALL
    SELECT 'Newsletter', '/#newsletter', 5, 1
) AS tmp
WHERE NOT EXISTS (SELECT 1 FROM page_links);

CREATE TABLE IF NOT EXISTS speaking_events (
    id INT AUTO_INCREMENT PRIMARY KEY,
    title VARCHAR(255) NOT NULL,
    event_name VARCHAR(255) NOT NULL,
    event_date DATE,
    link VARCHAR(500),
    description TEXT,
    sort_order INT NOT NULL DEFAULT 0
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

INSERT INTO speaking_events (title, event_name, event_date, link, description, sort_order)
SELECT * FROM (SELECT
    'Building in public as a solo founder' AS title,
    'GDG Manila Meetup' AS event_name,
    '2026-04-18' AS event_date,
    NULL AS link,
    'A talk on why publishing metrics and journal entries in public builds trust faster than a polished landing page.' AS description,
    1 AS sort_order
    UNION ALL SELECT
    'From engineer to TPM to founder', 'Women Techmakers Manila', '2026-06-05', NULL,
    'Panel discussion on nonlinear career paths in tech.', 2
) AS tmp
WHERE NOT EXISTS (SELECT 1 FROM speaking_events);

-- Events I plan to attend (as opposed to speaking_events, which are talks I'm
-- giving) — a separate table/page since the two lists don't overlap.
CREATE TABLE IF NOT EXISTS attending_events (
    id INT AUTO_INCREMENT PRIMARY KEY,
    event_name VARCHAR(255) NOT NULL,
    event_date DATE,
    location VARCHAR(255),
    link VARCHAR(500),
    description TEXT,
    sort_order INT NOT NULL DEFAULT 0
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

INSERT INTO attending_events (event_name, event_date, location, link, description, sort_order)
SELECT * FROM (SELECT
    'PyCon Philippines' AS event_name,
    '2026-05-14' AS event_date,
    'Manila, Philippines' AS location,
    NULL AS link,
    'Attending to scout talks on developer tooling and meet other solo builders.' AS description,
    1 AS sort_order
    UNION ALL SELECT
    'Google I/O Extended Manila', '2026-07-09', 'Manila, Philippines', NULL,
    'Local watch party and networking event for the year''s I/O announcements.', 2
) AS tmp
WHERE NOT EXISTS (SELECT 1 FROM attending_events);

CREATE TABLE IF NOT EXISTS resume_meta (
    id INT PRIMARY KEY,
    file_path VARCHAR(500),
    last_updated DATE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

INSERT INTO resume_meta (id, file_path, last_updated)
SELECT * FROM (SELECT 1 AS id, NULL AS file_path, '2026-06-01' AS last_updated) AS tmp
WHERE NOT EXISTS (SELECT 1 FROM resume_meta WHERE id = 1);

-- Flat, category+skill_name rows — grouped by category (in sort_order,
-- first-appearance order) when rendered, same pattern as timeline_milestones
-- grouping by month. Admin can add a brand-new category just by typing one
-- on a new skill row, and a category disappears once its last skill is
-- deleted — no separate "categories" table needed.
CREATE TABLE IF NOT EXISTS skills (
    id INT AUTO_INCREMENT PRIMARY KEY,
    category VARCHAR(100) NOT NULL,
    skill_name VARCHAR(100) NOT NULL,
    sort_order INT NOT NULL DEFAULT 0
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

INSERT INTO skills (category, skill_name, sort_order)
SELECT * FROM (SELECT 'Engineering' AS category, 'Python' AS skill_name, 1 AS sort_order UNION ALL
    SELECT 'Engineering', 'Flask', 2 UNION ALL
    SELECT 'Engineering', 'JavaScript', 3 UNION ALL
    SELECT 'Engineering', 'SQL', 4 UNION ALL
    SELECT 'Engineering', 'REST APIs', 5 UNION ALL
    SELECT 'Program & product', 'Roadmapping', 6 UNION ALL
    SELECT 'Program & product', 'Cross-functional leadership', 7 UNION ALL
    SELECT 'Program & product', 'Agile delivery', 8 UNION ALL
    SELECT 'Program & product', 'Stakeholder management', 9 UNION ALL
    SELECT 'Business', 'MBA — MIS', 10 UNION ALL
    SELECT 'Business', 'Data-informed strategy', 11 UNION ALL
    SELECT 'Business', 'Founder operations', 12 UNION ALL
    SELECT 'Community', 'Public speaking', 13 UNION ALL
    SELECT 'Community', 'Mentorship', 14 UNION ALL
    SELECT 'Community', 'Developer communities', 15
) AS tmp
WHERE NOT EXISTS (SELECT 1 FROM skills);

CREATE TABLE IF NOT EXISTS github_cache (
    id INT AUTO_INCREMENT PRIMARY KEY,
    cache_key VARCHAR(100) NOT NULL UNIQUE,
    payload LONGTEXT NOT NULL,
    fetched_at DATETIME NOT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS subscribers (
    id INT AUTO_INCREMENT PRIMARY KEY,
    email VARCHAR(255) NOT NULL UNIQUE,
    subscribed_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    is_active TINYINT(1) NOT NULL DEFAULT 1
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS site_settings (
    id INT AUTO_INCREMENT PRIMARY KEY,
    setting_key VARCHAR(100) NOT NULL UNIQUE,
    setting_value TEXT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

INSERT INTO site_settings (setting_key, setting_value)
SELECT * FROM (SELECT 'github_username' AS setting_key, 'blueazulbughaw' AS setting_value UNION ALL
    SELECT 'linkedin_url', 'https://www.linkedin.com/' UNION ALL
    SELECT 'instagram_url', 'https://www.instagram.com/' UNION ALL
    SELECT 'site_title', 'GladCodes — Software Engineer, TPM, Founder Who Ships' UNION ALL
    SELECT 'site_description', 'Building in public: a founder platform tracking projects, metrics, and lessons from an engineer-turned-founder.' UNION ALL
    SELECT 'contact_email', 'glad.cedeno@gmail.com' UNION ALL
    SELECT 'hero_bio', 'Software engineer turned founder, writing down every project, metric, and lesson in the open — from shipping code across Japan and Hong Kong to building GladCodes from a blank folder.' UNION ALL
    SELECT 'footer_copyright', '© 2026 Glad.'
) AS tmp
WHERE NOT EXISTS (SELECT 1 FROM site_settings);

-- ============================================================================
-- Phase 2 (Tutorials/Videos/Instagram/PDF library are fully built; API keys
-- panel remains a "Coming soon" admin-nav stub with no table of its own).
-- ============================================================================

CREATE TABLE IF NOT EXISTS tutorials (
    id INT AUTO_INCREMENT PRIMARY KEY,
    title VARCHAR(255) NOT NULL,
    slug VARCHAR(255) NOT NULL UNIQUE,
    series_name VARCHAR(255),
    excerpt TEXT,
    content_markdown LONGTEXT,
    cover_image VARCHAR(500),
    status ENUM('draft', 'published') NOT NULL DEFAULT 'draft',
    published_at DATETIME,
    sort_order INT NOT NULL DEFAULT 0,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- Idempotent upgrade path for installs that already have the old, narrower
-- tutorials table (CREATE TABLE IF NOT EXISTS above is a no-op for them).
ALTER TABLE tutorials ADD COLUMN IF NOT EXISTS excerpt TEXT AFTER series_name;
ALTER TABLE tutorials ADD COLUMN IF NOT EXISTS cover_image VARCHAR(500) AFTER content_markdown;
ALTER TABLE tutorials ADD COLUMN IF NOT EXISTS published_at DATETIME AFTER status;
ALTER TABLE tutorials ADD COLUMN IF NOT EXISTS updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP AFTER created_at;

CREATE TABLE IF NOT EXISTS videos (
    id INT AUTO_INCREMENT PRIMARY KEY,
    title VARCHAR(255) NOT NULL,
    youtube_url VARCHAR(500) NOT NULL,
    description TEXT,
    published_at DATE,
    sort_order INT NOT NULL DEFAULT 0
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS instagram_posts (
    id INT AUTO_INCREMENT PRIMARY KEY,
    embed_code TEXT NOT NULL,
    caption TEXT,
    posted_at DATE,
    sort_order INT NOT NULL DEFAULT 0
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS pdf_assets (
    id INT AUTO_INCREMENT PRIMARY KEY,
    title VARCHAR(255) NOT NULL,
    file_path VARCHAR(500) NOT NULL,
    is_product TINYINT(1) NOT NULL DEFAULT 0,
    price DECIMAL(10, 2),
    description TEXT,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
