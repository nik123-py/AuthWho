-- Decisions and policies (docs/interfaces.md section 11).
-- decisions is append-only: a trigger rejects every UPDATE, and every DELETE
-- unless the session setting authwho.retention is 'on', which only the 90-day
-- retention job sets. Decisions hold pseudonymous ids, scores, statuses and
-- feature names, never raw events.
CREATE TABLE decisions (
    decision_id        uuid PRIMARY KEY,
    session_id         uuid NOT NULL,
    user_id            uuid NOT NULL,
    app_id             text NOT NULL,
    role               text NOT NULL,
    created_at         timestamptz NOT NULL DEFAULT now(),
    trigger            text NOT NULL CHECK (trigger IN ('trust_update', 'action_request', 'step_up_result')),
    action_code        text,
    action_sensitivity text CHECK (action_sensitivity IN ('low', 'medium', 'high')),
    level              text NOT NULL CHECK (level IN ('insufficient_signal', 'high_confidence',
                           'moderate_deviation', 'strong_deviation', 'critical')),
    outcome            text NOT NULL CHECK (outcome IN ('continue', 'monitor', 'step_up', 'terminate')),
    action_allowed     boolean,
    trust              real,
    confidence         real,
    channels           jsonb NOT NULL,
    bot_flags          jsonb NOT NULL,
    window_ids         uuid[] NOT NULL,
    model_versions     jsonb NOT NULL,
    policy_version     text NOT NULL,
    explanation        text NOT NULL CHECK (length(explanation) > 0),
    step_up_result     text CHECK (step_up_result IN ('passed', 'failed'))
);

CREATE INDEX decisions_session_idx ON decisions (session_id, created_at);
CREATE INDEX decisions_created_at_idx ON decisions (created_at);

CREATE FUNCTION decisions_append_only() RETURNS trigger AS $$
BEGIN
    IF TG_OP = 'UPDATE' THEN
        RAISE EXCEPTION 'decisions are append-only';
    END IF;
    IF coalesce(current_setting('authwho.retention', true), '') <> 'on' THEN
        RAISE EXCEPTION 'decisions can only be deleted by the retention job';
    END IF;
    RETURN OLD;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER decisions_append_only
    BEFORE UPDATE OR DELETE ON decisions
    FOR EACH ROW EXECUTE FUNCTION decisions_append_only();

-- Thresholds per application and role, action sensitivities, and role
-- exemptions (proposal Section 10). Edited from the dashboard in P5.
CREATE TABLE policies (
    policy_id          text PRIMARY KEY,
    app_id             text NOT NULL,
    role               text NOT NULL,
    high               real NOT NULL CHECK (high > 0 AND high <= 100),
    strong             real NOT NULL CHECK (strong >= 0 AND strong < high),
    channel_low        real NOT NULL CHECK (channel_low > 0 AND channel_low < 1),
    action_sensitivity jsonb NOT NULL,
    exempt             boolean NOT NULL DEFAULT false,
    version            int NOT NULL DEFAULT 1,
    updated_at         timestamptz NOT NULL DEFAULT now(),
    UNIQUE (app_id, role)
);

INSERT INTO policies (policy_id, app_id, role, high, strong, channel_low, action_sensitivity)
VALUES ('demo-analyst', 'demo', 'analyst', 75, 50, 0.5, '{"add_payee": "high", "export_report": "high"}');
