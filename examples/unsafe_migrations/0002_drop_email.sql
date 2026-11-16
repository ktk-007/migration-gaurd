-- Demo PR 2 (fails, HIGH): running app versions may still read this column.
ALTER TABLE users DROP COLUMN email;
