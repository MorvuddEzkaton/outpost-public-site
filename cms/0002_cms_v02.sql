-- Additive upgrade for an existing CMS v0.1 database. Run only when 0001 v0.1 was applied.
ALTER TABLE cms_pages ADD COLUMN public_id TEXT;
ALTER TABLE cms_pages ADD COLUMN canonical_url TEXT NOT NULL DEFAULT '';
ALTER TABLE cms_pages ADD COLUMN robots TEXT NOT NULL DEFAULT 'index,follow';
UPDATE cms_pages SET public_id='page-' || id WHERE public_id IS NULL OR public_id='';
CREATE UNIQUE INDEX IF NOT EXISTS idx_cms_pages_public_id ON cms_pages(public_id);
CREATE TABLE IF NOT EXISTS cms_menus (menu_key TEXT PRIMARY KEY,items_json TEXT NOT NULL DEFAULT '[]',updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE IF NOT EXISTS cms_site_settings (setting_key TEXT PRIMARY KEY,value_json TEXT NOT NULL DEFAULT '{}',updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE IF NOT EXISTS cms_media (id INTEGER PRIMARY KEY AUTOINCREMENT,public_id TEXT NOT NULL UNIQUE,filename TEXT NOT NULL,url TEXT NOT NULL,alt TEXT NOT NULL DEFAULT '',title TEXT NOT NULL DEFAULT '',width INTEGER,height INTEGER,mime_type TEXT NOT NULL DEFAULT '',checksum TEXT NOT NULL DEFAULT '',created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE IF NOT EXISTS cms_github_sync_jobs (id INTEGER PRIMARY KEY AUTOINCREMENT,entity_type TEXT NOT NULL,entity_id TEXT NOT NULL,operation TEXT NOT NULL,payload_hash TEXT NOT NULL,status TEXT NOT NULL DEFAULT 'pending' CHECK(status IN ('pending','sending','done','failed')),attempt_count INTEGER NOT NULL DEFAULT 0,last_error TEXT,github_path TEXT NOT NULL,commit_message TEXT NOT NULL,payload_json TEXT NOT NULL,github_commit_sha TEXT,created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,completed_at TEXT);
CREATE INDEX IF NOT EXISTS idx_cms_sync_status ON cms_github_sync_jobs(status,id);
CREATE INDEX IF NOT EXISTS idx_cms_sync_dedupe ON cms_github_sync_jobs(github_path,payload_hash,status);
CREATE TABLE IF NOT EXISTS cms_meta (meta_key TEXT PRIMARY KEY,meta_value TEXT NOT NULL,updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
INSERT OR IGNORE INTO cms_menus(menu_key,items_json) VALUES ('primary','[]'),('footer','[]');
INSERT OR IGNORE INTO cms_site_settings(setting_key,value_json) VALUES ('site_identity','{"name":"OutPOSt","tagline":"Керування магазином"}'),('seo_defaults','{"titleSuffix":" — OutPOSt","description":""}');
INSERT OR REPLACE INTO cms_meta(meta_key,meta_value,updated_at) VALUES('schema_version','2',CURRENT_TIMESTAMP);
