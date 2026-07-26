-- loan-recovery-intelligence schema
-- Lives in the loan_recovery schema of the shared Supabase database
-- (free tier only allows 2 database projects, so this reuses an existing
-- project's database under its own schema rather than a new project).

DROP SCHEMA IF EXISTS loan_recovery CASCADE;
CREATE SCHEMA loan_recovery;

CREATE TABLE loan_recovery.customers (
    customer_id     SERIAL PRIMARY KEY,
    income          NUMERIC(12,2) NOT NULL,
    employment_status TEXT NOT NULL,
    age             INT NOT NULL,
    city            TEXT NOT NULL,
    state           TEXT NOT NULL,
    credit_score    INT NOT NULL
);

CREATE TABLE loan_recovery.loans (
    loan_id         SERIAL PRIMARY KEY,
    customer_id     INT NOT NULL REFERENCES loan_recovery.customers(customer_id),
    principal       NUMERIC(12,2) NOT NULL,
    interest_rate   NUMERIC(5,4) NOT NULL,
    term_months     INT NOT NULL,
    origination_date DATE NOT NULL,
    status          TEXT NOT NULL DEFAULT 'active'  -- active, paid_off, defaulted
);

CREATE TABLE loan_recovery.payment_history (
    payment_id      SERIAL PRIMARY KEY,
    loan_id         INT NOT NULL REFERENCES loan_recovery.loans(loan_id),
    due_date        DATE NOT NULL,
    amount_due      NUMERIC(12,2) NOT NULL,
    amount_paid     NUMERIC(12,2) NOT NULL DEFAULT 0,
    days_late       INT NOT NULL DEFAULT 0
);

CREATE TABLE loan_recovery.collection_actions (
    action_id       SERIAL PRIMARY KEY,
    loan_id         INT NOT NULL REFERENCES loan_recovery.loans(loan_id),
    action_date     DATE NOT NULL,
    action_type     TEXT NOT NULL,   -- reminder_email, phone_call, payment_plan, legal_notice
    cost            NUMERIC(10,2) NOT NULL,
    outcome         TEXT NOT NULL    -- paid_in_full, partial_payment, promised_to_pay, no_response
);
