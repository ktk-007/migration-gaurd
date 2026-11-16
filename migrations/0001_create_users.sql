-- Baseline schema for the demo. New migrations in pull requests are checked
-- by .github/workflows/migration-check.yml.
CREATE TABLE users (
    id         BIGSERIAL PRIMARY KEY,
    email      TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE payments (
    id          BIGSERIAL PRIMARY KEY,
    user_id     BIGINT NOT NULL REFERENCES users (id),
    amount      NUMERIC(12, 2) NOT NULL,
    card_number TEXT
);
