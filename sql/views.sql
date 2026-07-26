-- Current delinquency snapshot per loan: most recent cumulative days-late
-- figure, plus basic payment behavior stats. This is the feature source
-- for the default-risk model (step 2, feature engineering) — right now
-- "how late is this loan" only exists implicitly across many payment_history
-- rows, this view collapses it into one row per loan.

CREATE OR REPLACE VIEW loan_recovery.v_current_delinquency AS
SELECT
    l.loan_id,
    l.customer_id,
    l.status,
    l.principal,
    l.interest_rate,
    l.term_months,
    l.origination_date,
    COUNT(p.payment_id) AS total_payments_made,
    COUNT(p.payment_id) FILTER (WHERE p.days_late > 0) AS late_payment_count,
    ROUND(
        COUNT(p.payment_id) FILTER (WHERE p.days_late > 0)::NUMERIC
        / GREATEST(COUNT(p.payment_id), 1), 3
    ) AS pct_payments_late,
    ROUND(AVG(p.days_late), 1) AS avg_days_late,
    MAX(p.days_late) AS max_days_late_ever,
    -- most recent payment's days_late, as a proxy for "current" delinquency
    (
        SELECT p2.days_late
        FROM loan_recovery.payment_history p2
        WHERE p2.loan_id = l.loan_id
        ORDER BY p2.due_date DESC
        LIMIT 1
    ) AS most_recent_days_late
FROM loan_recovery.loans l
LEFT JOIN loan_recovery.payment_history p ON p.loan_id = l.loan_id
GROUP BY l.loan_id, l.customer_id, l.status, l.principal,
         l.interest_rate, l.term_months, l.origination_date;