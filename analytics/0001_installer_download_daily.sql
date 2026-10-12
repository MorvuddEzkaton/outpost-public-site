CREATE TABLE IF NOT EXISTS installer_download_daily (
  day_utc TEXT NOT NULL,
  version TEXT NOT NULL,
  request_count INTEGER NOT NULL DEFAULT 0 CHECK (request_count >= 0),
  first_seen_at TEXT NOT NULL,
  last_seen_at TEXT NOT NULL,
  PRIMARY KEY (day_utc, version)
);

CREATE INDEX IF NOT EXISTS idx_installer_download_daily_day
  ON installer_download_daily(day_utc);

CREATE TABLE IF NOT EXISTS installer_download_metadata (
  key TEXT PRIMARY KEY,
  value TEXT NOT NULL,
  updated_at TEXT NOT NULL
);
