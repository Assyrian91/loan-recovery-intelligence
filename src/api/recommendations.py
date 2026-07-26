"""
Action recommendation engine for loan default risk.

HOW THIS DIFFERS FROM THE CHURN-PIPELINE RECOMMENDATION ENGINE
-----------------------------------------------------------------
The churn project's recommendation engine used ASSUMED success rates per
action tier (documented honestly as such, but still guesses). This engine
uses the ACTUAL historical success rate per action type, computed directly
from loan_recovery.collection_actions.outcome — see
sql/queries/action_success_rates.sql, verified against the live database:

    payment_plan     43.0%  (819 actions)
    phone_call        39.2% (2,611 actions)
    reminder_email    29.5% (3,298 actions)
    legal_notice       23.9% (465 actions)

These are hardcoded as constants below rather than queried live on every
request, for simplicity — but they ARE the real, verified numbers from the
database, not a guess. In production this file would ideally recompute
them periodically (e.g. a scheduled job re-running action_success_rates.sql
and updating these constants), since success rates would drift as customer
behavior and collection tactics change over time. That refresh mechanism
is not built here — a documented, reasonable scope limit for a portfolio
project, same spirit as the churn project's own honesty about limitations.

METHODOLOGY
------------
Rather than assigning one fixed action per risk tier (churn's approach),
this engine computes the expected value of ALL FOUR action types for a
given loan, and recommends whichever has the highest expected net value:

    expected_value(action) = success_rate[action] * value_at_risk
                              - cost[action]

Where value_at_risk approximates the expected dollar loss if nothing is
done: probability_of_default * estimated_outstanding_balance * an assumed
loss-given-default fraction (not every default loses 100% of the balance —
some is typically recovered through other means even without a specific
collection action; 60% is a documented assumption, not a fitted value).

KNOWN SIMPLIFICATION: this does not model collection sequencing (e.g. "try
reminder_email before escalating to legal_notice"). It recommends whichever
single action has the best expected value as if any action were available
immediately, regardless of prior contact history. A production system
would likely add a sequencing/cooldown layer on top of this.
"""

from dataclasses import dataclass, field
from typing import List

# Verified against the database — see sql/queries/action_success_rates.sql
ACTION_SUCCESS_RATE = {
    "reminder_email": 0.295,
    "phone_call": 0.392,
    "payment_plan": 0.430,
    "legal_notice": 0.239,
}

# Matches the cost structure used in data generation (src/data_generation/generate_data.py)
ACTION_COST = {
    "reminder_email": 2.0,
    "phone_call": 15.0,
    "payment_plan": 40.0,
    "legal_notice": 150.0,
}

# Assumption: not every default results in a total loss of the outstanding
# balance — other recovery channels (asset seizure, write-off settlements,
# etc.) typically recover some portion even without this specific action.
LOSS_GIVEN_DEFAULT = 0.60

RISK_THRESHOLDS = {"High": 0.50, "Medium": 0.20}


@dataclass
class ActionOption:
    action_type: str
    success_rate: float
    cost: float
    expected_value: float


@dataclass
class LoanRecommendation:
    risk_tier: str
    probability_of_default: float
    estimated_outstanding_balance: float
    estimated_value_at_risk: float
    recommended_action: ActionOption
    all_options: List[ActionOption] = field(default_factory=list)
    assumptions_note: str = (
        "Action success rates are real, verified from logged collection_actions "
        "history (see sql/queries/action_success_rates.sql). Loss-given-default "
        "(60%) and outstanding balance (straight-line approximation) are "
        "documented assumptions, not fitted values."
    )


def _risk_tier(probability: float) -> str:
    if probability >= RISK_THRESHOLDS["High"]:
        return "High"
    if probability >= RISK_THRESHOLDS["Medium"]:
        return "Medium"
    return "Low"


def _estimate_outstanding_balance(principal: float, term_months: int, loan_age_months: float) -> float:
    """
    Straight-line approximation: assumes the loan balance declines linearly
    over its term. Real amortization schedules are front-loaded with
    interest (balance declines slower early on), so this slightly
    understates the true outstanding balance for loans in their first half
    of term — a documented simplification, not a precise amortization
    calculation.
    """
    remaining_months = max(0, term_months - loan_age_months)
    fraction_remaining = remaining_months / term_months if term_months > 0 else 0
    return round(principal * fraction_remaining, 2)


def recommend_action(
    probability_of_default: float,
    principal: float,
    term_months: int,
    loan_age_months: float,
) -> LoanRecommendation:
    """
    Compute the expected value of every available collection action for
    this loan, and recommend whichever has the highest expected net value.
    """
    tier = _risk_tier(probability_of_default)

    outstanding_balance = _estimate_outstanding_balance(principal, term_months, loan_age_months)
    value_at_risk = round(
        probability_of_default * outstanding_balance * LOSS_GIVEN_DEFAULT, 2
    )

    options = []
    for action_type, success_rate in ACTION_SUCCESS_RATE.items():
        cost = ACTION_COST[action_type]
        expected_value = round(success_rate * value_at_risk - cost, 2)
        options.append(ActionOption(
            action_type=action_type,
            success_rate=success_rate,
            cost=cost,
            expected_value=expected_value,
        ))

    options.sort(key=lambda o: o.expected_value, reverse=True)
    best = options[0]

    return LoanRecommendation(
        risk_tier=tier,
        probability_of_default=round(probability_of_default, 4),
        estimated_outstanding_balance=outstanding_balance,
        estimated_value_at_risk=value_at_risk,
        recommended_action=best,
        all_options=options,
    )