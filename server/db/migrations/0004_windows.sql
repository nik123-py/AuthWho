-- Window feature vectors (docs/interfaces.md section 8).
-- features_enc is AES-256-GCM over the JSON values array with AUTHWHO_DATA_KEY,
-- using the window_id bytes as associated data. Rows older than 30 days are
-- deleted by server.db.retention; a user's rows are deleted on withdrawal.
CREATE TABLE windows (
    window_id         uuid PRIMARY KEY,
    session_id        uuid NOT NULL,
    stream_id         uuid NOT NULL,
    user_id           uuid NOT NULL,
    channel           text NOT NULL CHECK (channel IN ('keystroke', 'pointer', 'interaction')),
    pointer_device    text NOT NULL CHECK (pointer_device IN ('mouse', 'touchpad', 'unknown')),
    schema            text NOT NULL,
    start_t           double precision NOT NULL,
    end_t             double precision NOT NULL,
    n_actions         int NOT NULL CHECK (n_actions > 0),
    quality           real NOT NULL CHECK (quality >= 0 AND quality <= 1),
    features_enc      bytea NOT NULL,
    extractor_version text NOT NULL,
    created_at        timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX windows_user_channel_idx ON windows (user_id, channel, pointer_device);
CREATE INDEX windows_session_idx ON windows (session_id);
CREATE INDEX windows_created_at_idx ON windows (created_at);
