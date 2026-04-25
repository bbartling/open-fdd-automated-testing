CREATE TABLE IF NOT EXISTS fdd_backfill_state (
    state_key text PRIMARY KEY,
    last_window_end timestamptz,
    cfg_start text,
    cfg_end text,
    updated_at timestamptz NOT NULL DEFAULT now()
);
