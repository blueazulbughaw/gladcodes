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

-- The standalone "Speaking" feature (speaking_events table + /speaking page)
-- was removed in favor of folding talks into this table via the
-- attending_as dropdown's "Speaker" option — one events list instead of two
-- overlapping ones. speaking_events itself is intentionally not dropped
-- here (schema.sql never removes tables), so any install that already
-- created it keeps its old rows on disk, just unused by the app now.
CREATE TABLE IF NOT EXISTS attending_events (
    id INT AUTO_INCREMENT PRIMARY KEY,
    event_name VARCHAR(255) NOT NULL,
    attending_as VARCHAR(255),
    datetime_from DATETIME,
    datetime_to DATETIME,
    status ENUM('tentative', 'confirmed') NOT NULL DEFAULT 'confirmed',
    location VARCHAR(255),
    link VARCHAR(500),
    description TEXT,
    sort_order INT NOT NULL DEFAULT 0
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- Idempotent upgrade path for installs that already have an older, narrower
-- attending_events table — CREATE TABLE above is a no-op for them. Older
-- columns (event_date, then date_from/date_to/time_from/time_to) are left
-- in place, unused, rather than dropped (schema.sql never removes columns
-- or tables, only adds).
ALTER TABLE attending_events ADD COLUMN IF NOT EXISTS attending_as VARCHAR(255) AFTER event_name;
ALTER TABLE attending_events ADD COLUMN IF NOT EXISTS date_from DATE AFTER attending_as;
ALTER TABLE attending_events ADD COLUMN IF NOT EXISTS date_to DATE AFTER date_from;
ALTER TABLE attending_events ADD COLUMN IF NOT EXISTS time_from TIME AFTER date_to;
ALTER TABLE attending_events ADD COLUMN IF NOT EXISTS time_to TIME AFTER time_from;
ALTER TABLE attending_events ADD COLUMN IF NOT EXISTS status ENUM('tentative', 'confirmed') NOT NULL DEFAULT 'confirmed' AFTER time_to;
ALTER TABLE attending_events ADD COLUMN IF NOT EXISTS datetime_from DATETIME AFTER time_to;
ALTER TABLE attending_events ADD COLUMN IF NOT EXISTS datetime_to DATETIME AFTER datetime_from;

-- One-time backfills, oldest column generation to newest.
UPDATE attending_events SET date_from = event_date WHERE date_from IS NULL AND event_date IS NOT NULL;
-- A NULL time_from/time_to meant "time TBA" under the old split fields;
-- collapsed into a single datetime it becomes midnight, and the admin cards
-- / public events page treat a midnight time as "no time given" so that
-- meaning isn't lost.
UPDATE attending_events SET datetime_from = TIMESTAMP(date_from, COALESCE(time_from, '00:00:00')) WHERE datetime_from IS NULL AND date_from IS NOT NULL;
UPDATE attending_events SET datetime_to = TIMESTAMP(date_to, COALESCE(time_to, '00:00:00')) WHERE datetime_to IS NULL AND date_to IS NOT NULL;

INSERT INTO attending_events (event_name, attending_as, datetime_from, datetime_to, status, location, link, description, sort_order)
SELECT * FROM (SELECT
    'PyCon Philippines' AS event_name,
    'Attendee' AS attending_as,
    '2026-05-14 00:00:00' AS datetime_from,
    '2026-05-16 00:00:00' AS datetime_to,
    'confirmed' AS status,
    'Manila, Philippines' AS location,
    NULL AS link,
    'Attending to scout talks on developer tooling and meet other solo builders.' AS description,
    1 AS sort_order
    UNION ALL SELECT
    'Google I/O Extended Manila', 'Attendee', '2026-07-09 18:00:00', '2026-07-09 21:00:00', 'tentative',
    'Manila, Philippines', NULL,
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

-- Career history for the /resume animated timeline. entry_type is purely
-- presentational (dot color + icon) — "side_venture" rows (WanderDeals,
-- GoGoBaon) are deliberately listed after the day job they ran alongside
-- rather than strictly by start date, since they read as a parallel track,
-- not the next sequential job.
CREATE TABLE IF NOT EXISTS resume_timeline (
    id INT AUTO_INCREMENT PRIMARY KEY,
    period_label VARCHAR(100) NOT NULL,
    title VARCHAR(255) NOT NULL,
    company VARCHAR(255) NOT NULL,
    entry_type ENUM('education', 'full_time', 'contract', 'side_venture', 'gap') NOT NULL DEFAULT 'full_time',
    summary TEXT,
    -- Separate voice for /resume (plain bullet points, one per line, no
    -- first-person narration) vs summary above, which is the first-person
    -- story told on /about — same facts, different register per page.
    resume_bullets TEXT,
    sort_order INT NOT NULL DEFAULT 0
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

ALTER TABLE resume_timeline ADD COLUMN IF NOT EXISTS resume_bullets TEXT AFTER summary;

INSERT INTO resume_timeline (period_label, title, company, entry_type, summary, resume_bullets, sort_order)
SELECT * FROM (SELECT
    '2002 - 2007' AS period_label,
    'B.S. Computer Engineering' AS title,
    'Mapua Institute of Technology' AS company,
    'education' AS entry_type,
    'Five years of engineering school in Manila - where I learned to pick up new things fast, a skill that''s carried every job since.' AS summary,
    'Foundation in software and computer engineering principles.' AS resume_bullets,
    1 AS sort_order
    UNION ALL SELECT
    'Jun 2007 - Sep 2007', 'Associate Consultant, Developer', 'Oracle (Philippines) Corporation', 'full_time',
    'My first real shot: a paid developer training program. Learned COBOL and Oracle''s billing platform from zero, in a fixed-length program built for engineers exactly like me.',
    'Completed a competitive, paid developer training program.\nLearned COBOL and Oracle Customer Care and Billing (CC&B) from the ground up.', 2
    UNION ALL SELECT
    'Mar 2008 - Dec 2008', 'IT Engineer / Software Programmer', 'Digital Information Technology (Japan)', 'full_time',
    'Moved to Kawasaki for this one. Worked entirely in Japanese - meetings, specs, all of it. Led small teams on an exam system, a social network clone, and a Visual C++ tool that caught discrepancies in hospital equipment data. Contract ended with the 2008 financial crisis.',
    'Led small development teams delivering an online exam system, a social networking platform, and a custom Visual C++ data-comparison tool for hospital equipment.\nOperated fully in Japanese across requirements, documentation, and client communication.', 3
    UNION ALL SELECT
    'May 2009 - Aug 2009', 'Japanese SAP Support Engineer', 'Hewlett-Packard Philippines', 'contract',
    'Short stint supporting SAP issues for Japanese enterprise clients before moving back into software development.',
    'Provided SAP support for Japanese enterprise clients.', 4
    UNION ALL SELECT
    'Aug 2009 - Mar 2011', 'Programmer (Web Developer)', 'Mozcom Inc.', 'full_time',
    'Built Drupal sites and OSCommerce stores for recognizable Philippine brands. Sat in on client meetings, then went and built whatever they actually needed.',
    'Built and maintained Drupal and OSCommerce sites for recognized Philippine brands.\nPartnered directly with clients to translate business requirements into technical solutions.', 5
    UNION ALL SELECT
    'Mar 2011 - Aug 2014', 'euHReka Software Engineer', 'NGA Human Resources (NorthgateArinso)', 'full_time',
    'Front-end engineer on a global HR platform for three and a half years. Built two modules, started mentoring junior engineers - the first hint that I''d end up leading more than coding.',
    'Developed the Enterprise Content Management and Recruitment modules for a global cloud HR platform.\nMentored junior engineers and supported system testing, troubleshooting, and performance optimization.', 6
    UNION ALL SELECT
    '2014 - 2016', 'Web Developer / Technical Support Engineer', 'Freelance + NetSuite Philippines', 'contract',
    'Freelanced WordPress and Drupal sites for US and Australian clients by night, supported NetSuite''s UK retail customers by day.',
    'Delivered WordPress and Drupal projects for US and Australian clients.\nProvided L1 technical support for an e-commerce platform''s UK retail clients.', 7
    UNION ALL SELECT
    'May 2016 - Feb 2021', 'Engineer II - Technical Program Manager and Engineering Lead', 'American Express International, Inc.', 'full_time',
    'Hired to build marketing pages. A year in, I was running delivery for about 15 engineers across 5 time zones - scrum master, AEM migration lead, the one presenting to directors and a VP. Still coded when the team was short-handed. When the company asked everyone back on-site mid-pandemic, I chose to relocate instead.',
    'Led delivery for a cross-functional team of approximately 15 engineers across 5 time zones.\nServed as Scrum Master, running sprints, retrospectives, and daily stand-ups across regions.\nDirected the migration of legacy applications to Adobe Experience Manager (AEM).\nBuilt reporting tools and presented performance metrics directly to directors and the VP of Technology.\nRecognized with multiple Blue Rewards.', 8
    UNION ALL SELECT
    'May 2016 - Jul 2017', 'CTO', 'WanderDeals (side venture)', 'side_venture',
    'Side project: sole technical lead on a travel-booking startup. It didn''t get the resources to keep going, but I learned a lot about building when nobody hands you a spec.',
    'Served as sole technical lead for a travel-activities booking platform.', 9
    UNION ALL SELECT
    'May 2018 - Jul 2019', 'CTO', 'GoGoBaon (side venture)', 'side_venture',
    'Another side build - a home-cook meal delivery business in Hong Kong. Built the site, ordering system, and payments myself.',
    'Built the website, ordering system, and payment integration for a home-cook meal delivery business.', 10
    UNION ALL SELECT
    'Jun 2021 - Jun 2022', 'Relocation and Professional Development', 'United States', 'gap',
    'Moved to the US and spent a year just learning - React, Node.js, figuring out what was next.',
    'Completed independent study in React and Node.js.', 11
    UNION ALL SELECT
    'Apr 2023 - Jun 2023', 'CRM Architect', 'Confidential Legal Funding Company (NDA)', 'contract',
    'CPT period during my MBA. Built a CRM from scratch - pipelines, automation, SMS integration - and co-built a directory site for attorneys and specialists.',
    'Designed and implemented a CRM build-out, including custom pipelines, modules, and workflow automation.\nIntegrated SMS messaging for direct client communication from the CRM.\nCo-developed a directory site connecting attorneys with specialists across 50+ categories.', 12
    UNION ALL SELECT
    'Oct 2024 - Jun 2026', 'MBA, Management Information Systems', 'International American University', 'education',
    'Went back to school to pair the engineering brain with a business one. Last step before betting on myself.',
    'Graduate coursework in management information systems, pairing technical expertise with business strategy.', 13
    UNION ALL SELECT
    'Jul 2026 - Present', 'Founder and Principal Consultant', 'Genri Labs LLC', 'full_time',
    'My own thing, finally. CRM and automation for a residential builder, e-commerce for another client, and my own products on the side - this site included.',
    'Architecting CRM and automation workflows for a residential construction client.\nManaging e-commerce operations for a retail client.\nBuilding independent products, including this site.', 14
) AS tmp
WHERE NOT EXISTS (SELECT 1 FROM resume_timeline);

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
SELECT * FROM (SELECT 'Front-end' AS category, 'JavaScript' AS skill_name, 1 AS sort_order UNION ALL
    SELECT 'Front-end', 'jQuery', 2 UNION ALL
    SELECT 'Front-end', 'Prototype.js', 3 UNION ALL
    SELECT 'Front-end', 'React', 4 UNION ALL
    SELECT 'Front-end', 'HTML', 5 UNION ALL
    SELECT 'Front-end', 'CSS', 6 UNION ALL
    SELECT 'Front-end', 'AJAX', 7 UNION ALL
    SELECT 'Front-end', 'JSON', 8 UNION ALL
    SELECT 'Front-end', 'XML', 9 UNION ALL
    SELECT 'Front-end', 'Bootstrap', 10 UNION ALL
    SELECT 'Back-end / languages', 'PHP', 11 UNION ALL
    SELECT 'Back-end / languages', 'Node.js', 12 UNION ALL
    SELECT 'Back-end / languages', 'Python (Flask)', 13 UNION ALL
    SELECT 'Back-end / languages', 'JSP / Java', 14 UNION ALL
    SELECT 'Back-end / languages', 'Visual C++', 15 UNION ALL
    SELECT 'Back-end / languages', 'COBOL', 16 UNION ALL
    SELECT 'Back-end / languages', 'MySQL', 17 UNION ALL
    SELECT 'CMS / e-commerce', 'WordPress', 18 UNION ALL
    SELECT 'CMS / e-commerce', 'Drupal', 19 UNION ALL
    SELECT 'CMS / e-commerce', 'Adobe Experience Manager (AEM)', 20 UNION ALL
    SELECT 'CMS / e-commerce', 'OSCommerce', 21 UNION ALL
    SELECT 'CMS / e-commerce', 'Shopify', 22 UNION ALL
    SELECT 'CMS / e-commerce', 'eBay', 23 UNION ALL
    SELECT 'CMS / e-commerce', 'Amazon Seller Central', 24 UNION ALL
    SELECT 'CRM / automation', 'HubSpot', 25 UNION ALL
    SELECT 'CRM / automation', 'Zoho CRM', 26 UNION ALL
    SELECT 'CRM / automation', 'JobTread', 27 UNION ALL
    SELECT 'CRM / automation', 'Zapier', 28 UNION ALL
    SELECT 'CRM / automation', 'n8n', 29 UNION ALL
    SELECT 'CRM / automation', 'DocuSign', 30 UNION ALL
    SELECT 'CRM / automation', 'Twilio', 31 UNION ALL
    SELECT 'Enterprise / delivery tools', 'ServiceNow', 32 UNION ALL
    SELECT 'Enterprise / delivery tools', 'Rally', 33 UNION ALL
    SELECT 'Enterprise / delivery tools', 'Jira', 34 UNION ALL
    SELECT 'Enterprise / delivery tools', 'Confluence', 35 UNION ALL
    SELECT 'Enterprise / delivery tools', 'CA Clarity', 36 UNION ALL
    SELECT 'Enterprise / delivery tools', 'Excel / VBA', 37 UNION ALL
    SELECT 'Enterprise / delivery tools', 'Microsoft 365', 38 UNION ALL
    SELECT 'Enterprise / delivery tools', 'SAP', 39 UNION ALL
    SELECT 'Enterprise / delivery tools', 'Oracle CC&B', 40 UNION ALL
    SELECT 'Version control', 'Git', 41 UNION ALL
    SELECT 'Version control', 'Tortoise SVN', 42 UNION ALL
    SELECT 'Practices', 'Agile / Scrum', 43 UNION ALL
    SELECT 'Practices', 'Technical Program Management', 44 UNION ALL
    SELECT 'Practices', 'Capacity Planning', 45 UNION ALL
    SELECT 'Practices', 'Vulnerability Remediation', 46 UNION ALL
    SELECT 'Practices', 'Cross-time-zone Leadership', 47 UNION ALL
    SELECT 'Practices', 'Requirements Gathering', 48 UNION ALL
    SELECT 'Practices', 'Onboarding and Training', 49 UNION ALL
    SELECT 'Languages', 'English', 50 UNION ALL
    SELECT 'Languages', 'Filipino', 51 UNION ALL
    SELECT 'Languages', 'Japanese (JLPT N3)', 52
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

-- Private daily check-in (/gc-admin/today). Never rendered on a public page:
-- mood, meds, and gratitude are personal. One row per local calendar day;
-- every tracker column is nullable so a morning save can be finished later.
CREATE TABLE IF NOT EXISTS daily_checkins (
    id INT AUTO_INCREMENT PRIMARY KEY,
    checkin_date DATE NOT NULL UNIQUE,
    mood TINYINT,
    energy TINYINT,
    focus TINYINT,
    sleep_hours DECIMAL(3, 1),
    took_meds TINYINT(1) NOT NULL DEFAULT 0,
    exercised TINYINT(1) NOT NULL DEFAULT 0,
    reading TEXT,
    grateful TEXT,
    top_priority VARCHAR(255),
    priority_done TINYINT(1) NOT NULL DEFAULT 0,
    scroll_minutes SMALLINT,
    win TEXT,
    notes TEXT,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- Browsers/devices that turned on check-in reminders (Web Push) from the
-- installed /gc-admin app. Single-admin site, so no user column.
CREATE TABLE IF NOT EXISTS push_subscriptions (
    id INT AUTO_INCREMENT PRIMARY KEY,
    endpoint VARCHAR(500) NOT NULL,
    p256dh VARCHAR(255) NOT NULL,
    auth VARCHAR(255) NOT NULL,
    user_agent VARCHAR(255),
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uq_push_endpoint (endpoint(191))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- Single-row state for the installable Today app, written by the app itself
-- (not admin-editable, and deliberately NOT in site_settings, whose rows are
-- passed to every public template). VAPID keys are generated on first start
-- (services/push.ensure_vapid_keys) unless VAPID_* env vars override them;
-- local_timezone is reported by the phone's browser; reminder_last_sent
-- ("YYYY-MM-DD:morning") makes each reminder go out at most once.
CREATE TABLE IF NOT EXISTS checkin_app_state (
    id TINYINT PRIMARY KEY,
    vapid_public_key VARCHAR(255),
    vapid_private_key VARCHAR(255),
    local_timezone VARCHAR(64),
    reminder_last_sent VARCHAR(32)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

INSERT IGNORE INTO checkin_app_state (id) VALUES (1);

-- Check-in v2 (2026-10-17): prayers, Bible passage, reason for the mood,
-- app ideas, period day. focus/took_meds/top_priority/priority_done and the
-- manual sleep_hours/scroll_minutes are no longer asked (sleep and phone
-- time are tracked automatically now) but stay in the table: schema.sql
-- never drops columns.
ALTER TABLE daily_checkins ADD COLUMN IF NOT EXISTS mood_reason TEXT AFTER mood;
ALTER TABLE daily_checkins ADD COLUMN IF NOT EXISTS morning_prayer TINYINT(1) NOT NULL DEFAULT 0;
ALTER TABLE daily_checkins ADD COLUMN IF NOT EXISTS night_prayer TINYINT(1) NOT NULL DEFAULT 0;
ALTER TABLE daily_checkins ADD COLUMN IF NOT EXISTS bible_passage TEXT;
ALTER TABLE daily_checkins ADD COLUMN IF NOT EXISTS app_ideas TEXT;
ALTER TABLE daily_checkins ADD COLUMN IF NOT EXISTS period_day TINYINT(1) NOT NULL DEFAULT 0;

-- Medicines to take, edited via the `medications` simple_crud resource.
-- doses_per_day (1-8) = how many checkboxes the Today page shows.
CREATE TABLE IF NOT EXISTS medications (
    id INT AUTO_INCREMENT PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    doses_per_day TINYINT NOT NULL DEFAULT 1,
    frequency ENUM('daily', 'every_other_day', 'weekly', 'as_needed') NOT NULL DEFAULT 'daily',
    start_date DATE,
    is_active TINYINT(1) NOT NULL DEFAULT 1,
    notes TEXT,
    sort_order INT NOT NULL DEFAULT 0
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- One row per ticked dose checkbox (unticking deletes it).
CREATE TABLE IF NOT EXISTS medication_doses (
    id INT AUTO_INCREMENT PRIMARY KEY,
    medication_id INT NOT NULL,
    dose_date DATE NOT NULL,
    dose_index TINYINT NOT NULL,
    taken_at DATETIME NOT NULL,
    UNIQUE KEY uq_dose (medication_id, dose_date, dose_index)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- Tracked automatically from the phone (POST /gc-admin/track/*, token auth),
-- never typed in. Kept apart from daily_checkins so a 7am sleep upload
-- doesn't count as "checked in" and silence the morning reminder.
CREATE TABLE IF NOT EXISTS sleep_logs (
    id INT AUTO_INCREMENT PRIMARY KEY,
    sleep_date DATE NOT NULL UNIQUE,
    minutes SMALLINT NOT NULL,
    updated_at DATETIME NOT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- App open/close events (e.g. Instagram) from a phone automation; minutes
-- per day are summed from these. Times are UTC (db.utc_now()).
CREATE TABLE IF NOT EXISTS app_sessions (
    id INT AUTO_INCREMENT PRIMARY KEY,
    app VARCHAR(64) NOT NULL,
    opened_at DATETIME NOT NULL,
    closed_at DATETIME,
    KEY idx_app_open (app, opened_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- Secret the phone automations send as "Authorization: Bearer <token>".
-- Generated on first start like the VAPID keys; shown on /gc-admin/me.
ALTER TABLE checkin_app_state ADD COLUMN IF NOT EXISTS ingest_token VARCHAR(64);

-- Check-in v2.1: a daily "what did you learn today?" answer. App ideas are
-- no longer a daily question; they're a standalone list (app_ideas below).
ALTER TABLE daily_checkins ADD COLUMN IF NOT EXISTS learnings TEXT AFTER reading;

-- Idea bank, edited via the `app_ideas` simple_crud resource and listed on
-- /gc-admin/me. Private: never shown on the public site.
CREATE TABLE IF NOT EXISTS app_ideas (
    id INT AUTO_INCREMENT PRIMARY KEY,
    idea VARCHAR(255) NOT NULL,
    details TEXT,
    sort_order INT NOT NULL DEFAULT 0,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- Carry over any ideas typed into the old daily question (idempotent: an
-- idea already in the list isn't copied again).
INSERT INTO app_ideas (idea, created_at)
SELECT LEFT(d.app_ideas, 255), d.checkin_date FROM daily_checkins d
WHERE d.app_ideas IS NOT NULL AND d.app_ideas <> ''
  AND NOT EXISTS (SELECT 1 FROM app_ideas a WHERE a.idea = LEFT(d.app_ideas, 255));

-- Check-in v2.2: a space to write the morning prayer, and water intake
-- (0-8 glasses). Mood/why/energy/gratitude are now asked in the evening.
ALTER TABLE daily_checkins ADD COLUMN IF NOT EXISTS morning_prayer_note TEXT AFTER morning_prayer;
ALTER TABLE daily_checkins ADD COLUMN IF NOT EXISTS water_glasses TINYINT NOT NULL DEFAULT 0;
