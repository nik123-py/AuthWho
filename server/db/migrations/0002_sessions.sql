-- Application sessions (docs/interfaces.md section 12). No behavioural data.
-- Rows older than 90 days are deleted by server.db.retention.
-- user_id has no foreign key on purpose: deleting a user ends their sessions
-- but the pseudonymous session rows expire on the 90-day schedule, like decisions.
CREATE TABLE sessions (
    session_id uuid PRIMARY KEY,
    user_id    uuid NOT NULL,
    app_id     text NOT NULL,
    role       text NOT NULL,
    status     text NOT NULL DEFAULT 'active'
        CHECK (status IN ('active', 'step_up_required', 'terminated')),
    created_at timestamptz NOT NULL DEFAULT now(),
    ended_at   timestamptz
);

CREATE INDEX sessions_user_id_idx ON sessions (user_id);
CREATE INDEX sessions_created_at_idx ON sessions (created_at);
