-- Sample banking star schema for testing the semantic layer pipeline.
--
--   dim_date ─┐
--   dim_customer ─┤
--   dim_branch ───┼── fact_transaction   (grain: one row per transaction)
--   dim_product ──┘
--
-- Runs automatically the first time the "warehouse" container starts.
-- Safe to re-run by hand (e.g. from DBeaver): it drops and rebuilds schema "mart".
-- Data is random but repeatable (fixed seed), so numbers stay the same between runs.

DROP SCHEMA IF EXISTS mart CASCADE;
CREATE SCHEMA mart;

-- ------------------------------------------------------------------ dimensions
CREATE TABLE mart.dim_date (
    date_key     integer PRIMARY KEY,          -- yyyymmdd
    full_date    date    NOT NULL UNIQUE,
    year         integer NOT NULL,
    quarter      integer NOT NULL,
    month        integer NOT NULL,
    month_name   text    NOT NULL,
    day_name     text    NOT NULL,
    is_weekend   boolean NOT NULL              -- Egypt: Friday + Saturday
);

INSERT INTO mart.dim_date
SELECT to_char(d, 'YYYYMMDD')::int,
       d,
       extract(year    FROM d)::int,
       extract(quarter FROM d)::int,
       extract(month   FROM d)::int,
       trim(to_char(d, 'Month')),
       trim(to_char(d, 'Day')),
       extract(isodow  FROM d) IN (5, 6)
FROM generate_series(date '2025-01-01', date '2026-12-31', interval '1 day') AS g(d);

CREATE TABLE mart.dim_customer (
    customer_key  integer PRIMARY KEY,
    customer_id   text    NOT NULL UNIQUE,     -- business key
    customer_name text    NOT NULL,
    segment       text    NOT NULL,            -- Retail / SME / Corporate
    governorate   text    NOT NULL,
    join_date     date    NOT NULL
);

CREATE TABLE mart.dim_branch (
    branch_key   integer PRIMARY KEY,
    branch_code  text    NOT NULL UNIQUE,
    branch_name  text    NOT NULL,
    city         text    NOT NULL,
    region       text    NOT NULL
);

INSERT INTO mart.dim_branch VALUES
    (1, 'BR001', 'Head Office',     'Cairo',       'Greater Cairo'),
    (2, 'BR002', 'Nasr City',       'Cairo',       'Greater Cairo'),
    (3, 'BR003', 'Dokki',           'Giza',        'Greater Cairo'),
    (4, 'BR004', 'Smouha',          'Alexandria',  'Alexandria'),
    (5, 'BR005', 'Ismailia Main',   'Ismailia',    'Canal'),
    (6, 'BR006', 'Port Said Main',  'Port Said',   'Canal'),
    (7, 'BR007', 'Suez Main',       'Suez',        'Canal'),
    (8, 'BR008', 'Mansoura',        'Mansoura',    'Delta');

CREATE TABLE mart.dim_product (
    product_key   integer PRIMARY KEY,
    product_code  text    NOT NULL UNIQUE,
    product_name  text    NOT NULL,
    category      text    NOT NULL             -- Account / Card / Loan
);

INSERT INTO mart.dim_product VALUES
    (1, 'CUR', 'Current Account',     'Account'),
    (2, 'SAV', 'Savings Account',     'Account'),
    (3, 'TD',  'Time Deposit',        'Account'),
    (4, 'DEB', 'Debit Card',          'Card'),
    (5, 'CRD', 'Credit Card',         'Card'),
    (6, 'PL',  'Personal Loan',       'Loan'),
    (7, 'ML',  'Mortgage Loan',       'Loan'),
    (8, 'SME', 'SME Working Capital', 'Loan');

-- ------------------------------------------------------------------ fact
CREATE TABLE mart.fact_transaction (
    transaction_id   bigint        PRIMARY KEY,
    date_key         integer       NOT NULL REFERENCES mart.dim_date (date_key),
    customer_key     integer       NOT NULL REFERENCES mart.dim_customer (customer_key),
    branch_key       integer       NOT NULL REFERENCES mart.dim_branch (branch_key),
    product_key      integer       NOT NULL REFERENCES mart.dim_product (product_key),
    channel          text          NOT NULL,   -- Branch / ATM / Mobile / Internet
    transaction_type text          NOT NULL,   -- Deposit / Withdrawal / Transfer / Payment
    amount           numeric(18,2) NOT NULL,   -- EGP
    fee_amount       numeric(18,2) NOT NULL,   -- EGP
    is_reversed      boolean       NOT NULL
);

-- Fixed seed: every run produces the same customers and transactions.
SELECT setseed(0.42);

INSERT INTO mart.dim_customer
SELECT g,
       'C' || lpad(g::text, 5, '0'),
       CASE WHEN g % 20 = 0 THEN 'Company ' || g
            ELSE (ARRAY['Ahmed','Mona','Omar','Sara','Youssef','Nour','Karim','Hana','Mostafa','Laila'])[1 + floor(random() * 10)::int]
                 || ' ' ||
                 (ARRAY['Hassan','Ibrahim','Mahmoud','Farouk','Saleh','Nasser','Adel','Kamal'])[1 + floor(random() * 8)::int]
       END,
       CASE WHEN g % 20 = 0 THEN 'Corporate' WHEN g % 5 = 0 THEN 'SME' ELSE 'Retail' END,
       (ARRAY['Cairo','Giza','Alexandria','Ismailia','Port Said','Suez','Dakahlia','Sharqia'])[1 + floor(random() * 8)::int],
       date '2015-01-01' + floor(random() * 3650)::int
FROM generate_series(1, 200) AS g;

INSERT INTO mart.fact_transaction
WITH base AS (
    SELECT g                                                AS transaction_id,
           date '2025-01-01' + floor(random() * 638)::int  AS txn_date,   -- up to 2026-09-30
           1 + floor(random() * 200)::int                   AS customer_key,
           1 + floor(random() * 8)::int                     AS branch_key,
           1 + floor(random() * 8)::int                     AS product_key,
           (ARRAY['Branch','ATM','Mobile','Internet'])[1 + floor(random() * 4)::int]            AS channel,
           (ARRAY['Deposit','Withdrawal','Transfer','Payment'])[1 + floor(random() * 4)::int]   AS transaction_type,
           random() AS r_amount,
           random() AS r_reversed
    FROM generate_series(1, 20000) AS g
)
SELECT b.transaction_id,
       to_char(b.txn_date, 'YYYYMMDD')::int,
       b.customer_key,
       b.branch_key,
       b.product_key,
       b.channel,
       b.transaction_type,
       round((50 + b.r_amount * b.r_amount * 20000
              * CASE c.segment WHEN 'Corporate' THEN 20 WHEN 'SME' THEN 4 ELSE 1 END)::numeric, 2),
       CASE b.channel WHEN 'Branch' THEN 15 WHEN 'ATM' THEN 5 ELSE 0 END,
       b.r_reversed < 0.02
FROM base b
JOIN mart.dim_customer c USING (customer_key);

CREATE INDEX ON mart.fact_transaction (date_key);
CREATE INDEX ON mart.fact_transaction (customer_key);
ANALYZE;
