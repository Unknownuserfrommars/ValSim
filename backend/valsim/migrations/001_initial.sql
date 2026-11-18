CREATE TABLE snapshots (
    id TEXT PRIMARY KEY,
    event_id TEXT NOT NULL,
    input_hash TEXT NOT NULL UNIQUE,
    received_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    payload TEXT NOT NULL
);

CREATE INDEX snapshots_event_revision ON snapshots(event_id, received_at DESC);

CREATE TABLE simulations (
    id TEXT PRIMARY KEY,
    snapshot_id TEXT NOT NULL REFERENCES snapshots(id),
    model_version TEXT NOT NULL,
    config TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('queued', 'running', 'complete', 'failed')),
    progress INTEGER NOT NULL DEFAULT 0,
    result TEXT,
    error TEXT
);
