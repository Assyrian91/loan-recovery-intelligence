-- Default rate by credit score band. Confirms the synthetic data has a
-- realistic, monotonic relationship between credit score and default risk
-- for the model to learn from.
--
-- Verified result (2026-07-26):
--   300-579 (Subprime): 18.4% default rate (636 loans)
--   580-669 (Fair):      8.6% default rate (1,570 loans)
--   670-739 (Good):      4.5% default rate (1,454 loans)
--   740-850 (Prime):     1.6% default rate (1,340 loans)

SELECT
    CASE
        WHEN c.credit_score < 580 THEN '300-579 (Subprime)'
        WHEN c.credit_score < 670 THEN '580-669 (Fair)'
        WHEN c.credit_score < 740 THEN '670-739 (Good)'
        ELSE '740-850 (Prime)'
    END AS credit_score_band,
    COUNT(*) AS total_loans,
    COUNT(*) FILTER (WHERE l.status = 'defaulted') AS defaulted_loans,
    ROUND(
        COUNT(*) FILTER (WHERE l.status = 'defaulted')::NUMERIC / COUNT(*), 3
    ) AS default_rate
FROM loan_recovery.loans l
JOIN loan_recovery.customers c ON l.customer_id = c.customer_id
GROUP BY credit_score_band
ORDER BY MIN(c.credit_score);
