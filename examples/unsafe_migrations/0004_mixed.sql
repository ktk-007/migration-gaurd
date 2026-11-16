-- Several risky operations in one file, plus one suppressed finding.
ALTER TABLE orders ADD COLUMN region TEXT NOT NULL;

CREATE INDEX idx_orders_region ON orders (region);

-- migration-guard: ignore MG007 reason="one-off reset of a cache table, approved by on-call"
DELETE FROM order_cache;
