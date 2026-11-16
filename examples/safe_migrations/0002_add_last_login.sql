-- Demo PR 1 (passes): a nullable column is safe to add on a live table.
ALTER TABLE users ADD COLUMN last_login TIMESTAMPTZ;
