-- Users known to AuthWho (docs/interfaces.md section 12).
-- user_id is a pseudonymous UUID; no usernames, emails or passwords.
CREATE TABLE users (
    user_id          uuid PRIMARY KEY,
    app_id           text NOT NULL,
    role             text NOT NULL,
    consent_version  text NOT NULL,
    consent_at       timestamptz NOT NULL,
    research_consent boolean NOT NULL DEFAULT false,
    opt_outs         text[] NOT NULL DEFAULT '{}'
        CHECK (opt_outs <@ ARRAY['keystroke', 'pointer', 'interaction']::text[]),
    exempt           boolean NOT NULL DEFAULT false,
    pointer_device   text NOT NULL DEFAULT 'unknown'
        CHECK (pointer_device IN ('mouse', 'touchpad', 'unknown')),
    created_at       timestamptz NOT NULL DEFAULT now()
);
