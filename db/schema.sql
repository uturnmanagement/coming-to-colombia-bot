-- Colombia Desk SQLite schema (Layer 1).
--
-- Owns: deal heartbeat state, heartbeat snapshots, specialist-report
-- placeholder. The scanner's JSON files in logs/ are NOT migrated to
-- SQLite in Layer 1 — preservation rule.

CREATE TABLE IF NOT EXISTS deals (
    deal_id              TEXT PRIMARY KEY,
    first_alert_at       TEXT NOT NULL,
    last_heartbeat_at    TEXT,
    heartbeat_count      INTEGER NOT NULL DEFAULT 0,
    status               TEXT NOT NULL DEFAULT 'active',
    last_color           TEXT,
    last_price_usd       REAL,
    last_route_signature TEXT,
    last_departure_at    TEXT,
    updated_at           TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_deals_status ON deals(status);
CREATE INDEX IF NOT EXISTS idx_deals_first_alert_at ON deals(first_alert_at);

CREATE TABLE IF NOT EXISTS heartbeat_snapshots (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    deal_id           TEXT NOT NULL,
    emitted_at        TEXT NOT NULL,
    stage             TEXT NOT NULL,
    color             TEXT,
    price_usd         REAL,
    route_signature   TEXT,
    departure_at      TEXT,
    trigger_reason    TEXT,
    FOREIGN KEY (deal_id) REFERENCES deals(deal_id)
);

CREATE INDEX IF NOT EXISTS idx_hb_deal_emitted
    ON heartbeat_snapshots(deal_id, emitted_at);

-- Placeholder for Layer 2+ specialists (Echo, India, Juliet, …).
CREATE TABLE IF NOT EXISTS specialist_reports (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    deal_id      TEXT,
    specialist   TEXT NOT NULL,
    report_at    TEXT NOT NULL,
    payload_json TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_specialist_lookup
    ON specialist_reports(specialist, deal_id, report_at);

-- Layer 4 — Lodging Price Intelligence.
-- lodging_baseline holds the rolling typical-price for one
-- (city, neighborhood, beds) tuple. lodging_history is the raw
-- observation log every provider feeds into.
CREATE TABLE IF NOT EXISTS lodging_baseline (
    id                 INTEGER PRIMARY KEY AUTOINCREMENT,
    city               TEXT    NOT NULL,
    neighborhood       TEXT,
    beds               INTEGER,
    baseline_price_usd REAL    NOT NULL,
    sample_size        INTEGER NOT NULL,
    lookback_days      INTEGER NOT NULL,
    computed_at        TEXT    NOT NULL,
    source_set         TEXT
);

CREATE INDEX IF NOT EXISTS idx_lodging_baseline_lookup
    ON lodging_baseline(city, neighborhood, beds, computed_at);

CREATE TABLE IF NOT EXISTS lodging_history (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    city            TEXT    NOT NULL,
    neighborhood    TEXT,
    beds            INTEGER,
    observed_at     TEXT    NOT NULL,
    stay_date       TEXT    NOT NULL,
    price_usd       REAL    NOT NULL,
    source          TEXT    NOT NULL,
    listing_ref     TEXT,
    raw_json        TEXT
);

CREATE INDEX IF NOT EXISTS idx_lodging_history_lookup
    ON lodging_history(city, neighborhood, beds, observed_at);
