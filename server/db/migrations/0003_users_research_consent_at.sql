-- When the current research consent was given. Set when research_consent
-- changes from false to true, cleared when it becomes false. The research
-- export only exports batches received at or after this time.
ALTER TABLE users ADD COLUMN research_consent_at timestamptz;

-- Existing consents count from now, so nothing captured earlier is exported.
UPDATE users SET research_consent_at = now() WHERE research_consent;

ALTER TABLE users ADD CONSTRAINT users_research_consent_at_check
    CHECK (research_consent = (research_consent_at IS NOT NULL));
