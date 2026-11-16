-- Safe migration. The dangerous words below are in comments and strings only.
-- DROP TABLE users;
CREATE TABLE plans (id bigint PRIMARY KEY, name text NOT NULL);
ALTER TABLE users ADD COLUMN plan_id bigint;
CREATE INDEX CONCURRENTLY idx_users_plan ON users (plan_id);
INSERT INTO plans (id, name) VALUES (1, 'TRUNCATE is not run here');
