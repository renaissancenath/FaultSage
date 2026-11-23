-- 0002_billing_event_time.sql (safe, additive): remember the newest billing event applied to
-- each org so a late or replayed webhook can never undo a newer one (D-025).
ALTER TABLE orgs ADD COLUMN billing_updated_at TEXT;
