CREATE TABLE IF NOT EXISTS signals (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at      TEXT    NOT NULL,
    asset           TEXT    NOT NULL,
    direction       TEXT    NOT NULL,
    expiry_minutes  INTEGER NOT NULL,
    confidence_pct  REAL    NOT NULL,
    position_usd    REAL    NOT NULL,
    reasons_json    TEXT,
    reports_json    TEXT,
    outcome         TEXT,
    pnl_pct         REAL    DEFAULT 0,
    closed_at       TEXT
);
CREATE INDEX IF NOT EXISTS idx_signals_created ON signals(created_at);
CREATE INDEX IF NOT EXISTS idx_signals_asset   ON signals(asset);
