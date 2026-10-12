-- Telegram release subscription storage for the public OutPOSt bot.
-- Privacy boundary: store only the Telegram chat ID and release-delivery state.
-- Runtime also uses CREATE TABLE IF NOT EXISTS so deployment does not depend on a manual migration step.

CREATE TABLE IF NOT EXISTS telegram_update_subscribers (
    chat_id TEXT PRIMARY KEY,
    subscribed_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    last_notified_version TEXT NOT NULL
);
