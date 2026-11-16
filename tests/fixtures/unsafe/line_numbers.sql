-- Hand-checked fixture: statements start on lines 5, 9 and 12.
-- A DROP TABLE mentioned in a comment must not count.

/* block comment */
CREATE TABLE ok (id int);

-- next statement is risky

ALTER TABLE users
    DROP COLUMN email;

TRUNCATE sessions;
