-- Profile templates and trust timeline (docs/interfaces.md section 9).
-- template_enc is AES-256-GCM over the JSON template (ml/profile.py) with
-- AUTHWHO_DATA_KEY and the profile_id bytes as associated data; never a pickle.
-- One active template per user, channel and device key: the device type for
-- the pointer channel, 'any' for keystroke and interaction. A template is kept
-- until re-enrollment (a new version replaces it) or account deletion.
CREATE TABLE profiles (
    profile_id    uuid PRIMARY KEY,
    user_id       uuid NOT NULL,
    channel       text NOT NULL CHECK (channel IN ('keystroke', 'pointer', 'interaction')),
    device_key    text NOT NULL CHECK (device_key IN ('any', 'mouse', 'touchpad', 'unknown')),
    version       int NOT NULL CHECK (version > 0),
    model_kind    text NOT NULL,
    template_enc  bytea NOT NULL,
    n_windows     int NOT NULL CHECK (n_windows > 0),
    created_at    timestamptz NOT NULL DEFAULT now(),
    UNIQUE (user_id, channel, device_key)
);

-- One row per trust update. Holds scores, statuses and feature names with
-- their deviations, never raw events. Deleted after 30 days, like the windows
-- it derives from (ruling R7), and on withdrawal.
CREATE TABLE trust_points (
    id          bigserial PRIMARY KEY,
    session_id  uuid NOT NULL,
    user_id     uuid NOT NULL,
    seq         int NOT NULL,
    at          timestamptz NOT NULL,
    state       text NOT NULL CHECK (state IN ('scored', 'insufficient_signal')),
    trust       real,
    confidence  real,
    payload     jsonb NOT NULL,
    created_at  timestamptz NOT NULL DEFAULT now(),
    CHECK ((state = 'scored') = (trust IS NOT NULL))
);

CREATE INDEX trust_points_session_idx ON trust_points (session_id, seq);
CREATE INDEX trust_points_user_idx ON trust_points (user_id);
CREATE INDEX trust_points_created_at_idx ON trust_points (created_at);
