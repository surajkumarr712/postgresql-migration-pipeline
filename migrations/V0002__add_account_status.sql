ALTER TABLE customer_accounts
    ADD COLUMN status TEXT NOT NULL DEFAULT 'active'
    CHECK (status IN ('active', 'suspended', 'closed'));

CREATE INDEX customer_accounts_status_idx ON customer_accounts (status);
