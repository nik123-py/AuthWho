-- Ruling R15: calibrated channel scores are per-user p-values, so a channel counts
-- as deviating only when its score is in the user's lowest tenth (0.1), not below 0.5.
UPDATE policies SET channel_low = 0.1, version = version + 1, updated_at = now()
WHERE policy_id = 'demo-analyst' AND channel_low = 0.5;
