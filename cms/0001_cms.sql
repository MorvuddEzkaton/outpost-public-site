PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS cms_pages (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  public_id TEXT NOT NULL UNIQUE,
  slug TEXT NOT NULL UNIQUE,
  title TEXT NOT NULL,
  seo_title TEXT NOT NULL DEFAULT '',
  seo_description TEXT NOT NULL DEFAULT '',
  canonical_url TEXT NOT NULL DEFAULT '',
  robots TEXT NOT NULL DEFAULT 'index,follow',
  status TEXT NOT NULL DEFAULT 'draft' CHECK(status IN ('draft','published','archived','deleted')),
  content_json TEXT NOT NULL DEFAULT '[]',
  version INTEGER NOT NULL DEFAULT 1,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  published_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_cms_pages_public ON cms_pages(status,slug);

CREATE TABLE IF NOT EXISTS cms_page_revisions (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  page_id INTEGER NOT NULL REFERENCES cms_pages(id) ON DELETE CASCADE,
  page_version INTEGER NOT NULL,
  reason TEXT NOT NULL,
  snapshot_json TEXT NOT NULL,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_cms_page_revisions_page ON cms_page_revisions(page_id,id DESC);

CREATE TABLE IF NOT EXISTS cms_redirects (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  source_path TEXT NOT NULL UNIQUE,
  target_url TEXT NOT NULL,
  http_status INTEGER NOT NULL DEFAULT 301 CHECK(http_status IN (301,302,307,308)),
  active INTEGER NOT NULL DEFAULT 1 CHECK(active IN (0,1)),
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS cms_menus (menu_key TEXT PRIMARY KEY,items_json TEXT NOT NULL DEFAULT '[]',updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE IF NOT EXISTS cms_site_settings (setting_key TEXT PRIMARY KEY,value_json TEXT NOT NULL DEFAULT '{}',updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE IF NOT EXISTS cms_media (
  id INTEGER PRIMARY KEY AUTOINCREMENT, public_id TEXT NOT NULL UNIQUE, filename TEXT NOT NULL, url TEXT NOT NULL,
  alt TEXT NOT NULL DEFAULT '', title TEXT NOT NULL DEFAULT '', width INTEGER, height INTEGER,
  mime_type TEXT NOT NULL DEFAULT '', checksum TEXT NOT NULL DEFAULT '',
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP, updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS cms_github_sync_jobs (
  id INTEGER PRIMARY KEY AUTOINCREMENT, entity_type TEXT NOT NULL, entity_id TEXT NOT NULL, operation TEXT NOT NULL,
  payload_hash TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'pending' CHECK(status IN ('pending','sending','done','failed')),
  attempt_count INTEGER NOT NULL DEFAULT 0, last_error TEXT, github_path TEXT NOT NULL, commit_message TEXT NOT NULL,
  payload_json TEXT NOT NULL, github_commit_sha TEXT, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP, completed_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_cms_sync_status ON cms_github_sync_jobs(status,id);
CREATE INDEX IF NOT EXISTS idx_cms_sync_dedupe ON cms_github_sync_jobs(github_path,payload_hash,status);
CREATE TABLE IF NOT EXISTS cms_meta (meta_key TEXT PRIMARY KEY,meta_value TEXT NOT NULL,updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);

INSERT OR IGNORE INTO cms_menus(menu_key,items_json) VALUES
  ('primary','[{"label":"Головна","href":"/"},{"label":"Усі можливості","href":"/features"},{"label":"Завантажити","href":"/download"}]'),
  ('footer','[{"label":"Політика конфіденційності","href":"/privacy"},{"label":"Умови використання","href":"/terms"}]');
INSERT OR IGNORE INTO cms_site_settings(setting_key,value_json) VALUES
  ('site_identity','{"name":"OutPOSt","tagline":"Керування магазином"}'),
  ('seo_defaults','{"titleSuffix":" — OutPOSt","description":"OutPOSt — програма для керування магазином."}');
INSERT OR REPLACE INTO cms_meta(meta_key,meta_value,updated_at) VALUES('schema_version','2',CURRENT_TIMESTAMP);
