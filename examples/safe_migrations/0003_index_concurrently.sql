-- Safe: CONCURRENTLY does not block writes while the index builds.
CREATE INDEX CONCURRENTLY idx_users_last_login ON users (last_login);
