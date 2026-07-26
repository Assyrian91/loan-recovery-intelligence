-- Historical success rate per collection action type, computed directly
-- from logged outcomes. This replaces the "assumed success rate" limitation
-- from the churn-pipeline project's recommendation engine — here the number
-- comes from real (synthetic but simulated-realistic) intervention history.
--
-- Verified result (2026-07-26):
--   payment_plan    43.0% (819 actions)
--   phone_call      39.2% (2,611 actions)
--   reminder_email  29.5% (3,298 actions)
--   legal_notice    23.9% (465 actions)

SELECT
    action_type,
    COUNT(*) AS total_actions,
    ROUND(
        COUNT(*) FILTER (WHERE outcome IN ('paid_in_full', 'partial_payment'))::NUMERIC
        / COUNT(*), 3
    ) AS success_rate
FROM loan_recovery.collection_actions
GROUP BY action_type
ORDER BY success_rate DESC;
