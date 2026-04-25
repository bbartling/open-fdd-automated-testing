CREATE TABLE IF NOT EXISTS csv_ingest_state (
    state_key text PRIMARY KEY,
    last_ts timestamptz,
    updated_at timestamptz NOT NULL DEFAULT now()
);
