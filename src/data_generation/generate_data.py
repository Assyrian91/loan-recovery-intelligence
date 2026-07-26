"""
Synthetic data generator for loan-recovery-intelligence.

WHY SYNTHETIC AND WHY THIS STRUCTURE
-------------------------------------
The old Smart-Loan-recovery project used a flat, single-snapshot CSV
(one row per customer, one Risk_Flag). That's enough to train a classifier
but gives a SQL layer nothing real to do, and gives a recommendation engine
no outcome history to learn from.

This generator instead produces a small relational database:
  customers -> loans -> payment_history (many rows per loan, over time)
                      -> collection_actions (triggered by delinquency, with
                         a logged outcome per attempt)

The key design choice: each customer has a hidden "risk propensity" that
correlates with credit_score, income, and employment_status. That latent
variable drives both (a) how likely they are to pay late / default, and
(b) how likely a given collection action is to actually work on them.
This is what makes the later "historical success rate by action type"
calculation meaningful — it's not hardcoded, it emerges from simulated
behavior, the same way it would from real collections data.

Realism notes / limitations (documented honestly, same practice as the
churn project):
  - Distributions (income, credit score, delinquency rates) are informed
    approximations for an Australian retail lending context, not fitted to
    a real bank's book.
  - Correlations (credit score -> default risk, action type -> success
    rate) are deliberately built in so the downstream model and
    recommendation engine have real signal to find — but the exact
    strength of these correlations is a design choice, not measured.
"""

import numpy as np
import pandas as pd
from datetime import date, timedelta

RNG = np.random.default_rng(seed=42)

N_CUSTOMERS = 5000
TODAY = date(2026, 7, 26)

CITIES_STATES = [
    ("Melbourne", "VIC"), ("Geelong", "VIC"), ("Ballarat", "VIC"),
    ("Sydney", "NSW"), ("Newcastle", "NSW"), ("Wollongong", "NSW"),
    ("Brisbane", "QLD"), ("Gold Coast", "QLD"),
    ("Perth", "WA"), ("Adelaide", "SA"), ("Hobart", "TAS"),
]

EMPLOYMENT_STATUSES = ["Full-time", "Part-time", "Self-employed", "Unemployed", "Retired"]
EMPLOYMENT_WEIGHTS = [0.55, 0.18, 0.15, 0.05, 0.07]

ACTION_TYPES = ["reminder_email", "phone_call", "payment_plan", "legal_notice"]
ACTION_COST = {"reminder_email": 2.0, "phone_call": 15.0, "payment_plan": 40.0, "legal_notice": 150.0}

# Base success probability per action type, BEFORE adjusting for the
# customer's individual risk propensity. Deliberately not uniform, so
# "historical success rate by action type" is a real, discoverable pattern.
ACTION_BASE_SUCCESS = {
    "reminder_email": 0.35,
    "phone_call": 0.50,
    "payment_plan": 0.60,
    "legal_notice": 0.30,   # high pressure, but often signals a relationship already broken down
}

OUTCOME_LABELS = ["paid_in_full", "partial_payment", "promised_to_pay", "no_response"]


def generate_customers(n=N_CUSTOMERS) -> pd.DataFrame:
    ages = RNG.integers(21, 70, size=n)
    income = np.round(RNG.normal(75000, 28000, size=n).clip(25000, 250000), 2)
    employment = RNG.choice(EMPLOYMENT_STATUSES, size=n, p=EMPLOYMENT_WEIGHTS)
    city_state = RNG.choice(len(CITIES_STATES), size=n)
    credit_score = RNG.normal(680, 90, size=n).clip(300, 850).astype(int)

    # Lower credit score, unemployment, and low income all push risk propensity up.
    # This latent variable (0 = very safe, 1 = very risky) is NOT stored in the
    # table (a real bank wouldn't have "true risk" as a column either) — it only
    # drives the simulation of payments and collection outcomes below.
    risk_propensity = (
        (850 - credit_score) / 550 * 0.5
        + (employment == "Unemployed").astype(float) * 0.3
        + (75000 - income).clip(min=0) / 75000 * 0.2
    )
    risk_propensity = np.clip(risk_propensity + RNG.normal(0, 0.08, size=n), 0.02, 0.95)

    df = pd.DataFrame({
        "customer_id": np.arange(1, n + 1),
        "income": income,
        "employment_status": employment,
        "age": ages,
        "city": [CITIES_STATES[i][0] for i in city_state],
        "state": [CITIES_STATES[i][1] for i in city_state],
        "credit_score": credit_score,
    })
    return df, risk_propensity


def generate_loans(customers: pd.DataFrame) -> pd.DataFrame:
    n = len(customers)
    term_months = RNG.choice([12, 24, 36, 48, 60], size=n, p=[0.15, 0.25, 0.30, 0.20, 0.10])

    # Risk-based pricing: lower credit score -> higher interest rate
    base_rate = 0.06
    risk_premium = (850 - customers["credit_score"]) / 550 * 0.12
    interest_rate = np.round((base_rate + risk_premium + RNG.normal(0, 0.005, size=n)).clip(0.045, 0.22), 4)

    principal = np.round((customers["income"] * RNG.uniform(0.08, 0.35, size=n)).clip(2000, 45000), 2)

    days_back = RNG.integers(30, 1095, size=n)  # originated within the last ~3 years
    origination_date = [TODAY - timedelta(days=int(d)) for d in days_back]

    df = pd.DataFrame({
        "loan_id": np.arange(1, n + 1),
        "customer_id": customers["customer_id"],
        "principal": principal,
        "interest_rate": interest_rate,
        "term_months": term_months,
        "origination_date": origination_date,
        "status": "active",  # updated to paid_off / defaulted after payment simulation
    })
    return df


def simulate_payments_and_actions(loans: pd.DataFrame, risk_propensity: np.ndarray):
    """
    Walk each loan month-by-month from origination to today (or term end),
    simulating whether each installment is paid on time, late, or missed.
    Delinquency triggers collection_actions once cumulative days_late crosses
    thresholds. Each action's outcome is drawn from a probability that depends
    on both the action type's base effectiveness AND this customer's risk
    propensity — a risky customer is harder to collect from regardless of
    which action is used, but some actions are still more effective than
    others on average. That combination is what the recommendation engine
    will later have to discover from this data.
    """
    payment_rows = []
    action_rows = []
    loan_status = []
    payment_id = 1
    action_id = 1

    for _, loan in loans.iterrows():
        cust_idx = loan["customer_id"] - 1
        propensity = risk_propensity[cust_idx]

        monthly_payment = round(
            (loan["principal"] * (1 + loan["interest_rate"])) / loan["term_months"], 2
        )

        n_installments_elapsed = min(
            loan["term_months"],
            max(0, (TODAY - loan["origination_date"]).days // 30)
        )

        cumulative_days_late = 0
        defaulted = False
        last_action_thresholds_fired = set()

        for i in range(int(n_installments_elapsed)):
            due_date = loan["origination_date"] + timedelta(days=30 * (i + 1))
            if due_date > TODAY:
                break

            # Probability of paying late this month scales with risk propensity
            late_prob = 0.03 + (propensity ** 1.2) * 1.3
            is_late = RNG.random() < late_prob

            if is_late:
                days_late = int(RNG.gamma(shape=1.5, scale=6 + propensity * 12))
                days_late = min(days_late, 120)
            else:
                days_late = 0

            # Missed payment entirely (more likely for high propensity + already late)
            miss_prob = 0.01 + (propensity ** 1.2) * 0.35 + (cumulative_days_late > 60) * 0.18
            missed = RNG.random() < miss_prob

            amount_due = monthly_payment
            amount_paid = 0.0 if missed else round(monthly_payment * RNG.uniform(0.9, 1.0), 2)

            payment_rows.append({
                "payment_id": payment_id,
                "loan_id": loan["loan_id"],
                "due_date": due_date,
                "amount_due": amount_due,
                "amount_paid": amount_paid,
                "days_late": days_late if not missed else max(days_late, 30),
            })
            payment_id += 1

            if missed:
                cumulative_days_late = max(0, cumulative_days_late + 30)
            elif is_late:
                cumulative_days_late = max(0, cumulative_days_late + days_late - 5)
            else:
                cumulative_days_late = max(0, cumulative_days_late - 10)

            # Trigger collection actions at escalating thresholds
            thresholds = [(15, "reminder_email"), (30, "phone_call"),
                          (60, "payment_plan"), (90, "legal_notice")]
            for threshold, action_type in thresholds:
                key = (loan["loan_id"], threshold)
                if cumulative_days_late >= threshold and key not in last_action_thresholds_fired:
                    last_action_thresholds_fired.add(key)

                    success_prob = ACTION_BASE_SUCCESS[action_type] * (1 - propensity * 0.7)
                    outcome_roll = RNG.random()
                    if outcome_roll < success_prob * 0.5:
                        outcome = "paid_in_full"
                        cumulative_days_late = max(0, cumulative_days_late - 45)
                    elif outcome_roll < success_prob:
                        outcome = "partial_payment"
                        cumulative_days_late = max(0, cumulative_days_late - 15)
                    elif outcome_roll < success_prob + 0.2:
                        outcome = "promised_to_pay"
                    else:
                        outcome = "no_response"

                    action_rows.append({
                        "action_id": action_id,
                        "loan_id": loan["loan_id"],
                        "action_date": due_date,
                        "action_type": action_type,
                        "cost": ACTION_COST[action_type],
                        "outcome": outcome,
                    })
                    action_id += 1

            if cumulative_days_late >= 110:
                defaulted = True
                break

        if defaulted:
            loan_status.append("defaulted")
        elif n_installments_elapsed >= loan["term_months"]:
            loan_status.append("paid_off")
        else:
            loan_status.append("active")

    payments_df = pd.DataFrame(payment_rows)
    actions_df = pd.DataFrame(action_rows)
    return payments_df, actions_df, loan_status


def main():
    print("Generating customers...")
    customers, risk_propensity = generate_customers()

    print("Generating loans...")
    loans = generate_loans(customers)

    print("Simulating payment history and collection actions (this walks every loan month-by-month, takes a moment)...")
    payments, actions, loan_status = simulate_payments_and_actions(loans, risk_propensity)
    loans["status"] = loan_status

    out_dir = "data/raw"
    customers.to_csv(f"{out_dir}/customers.csv", index=False)
    loans.to_csv(f"{out_dir}/loans.csv", index=False)
    payments.to_csv(f"{out_dir}/payment_history.csv", index=False)
    actions.to_csv(f"{out_dir}/collection_actions.csv", index=False)

    print("\n--- Summary ---")
    print(f"Customers: {len(customers):,}")
    print(f"Loans: {len(loans):,}  |  Status breakdown:\n{loans['status'].value_counts()}")
    print(f"Payment records: {len(payments):,}")
    print(f"Collection actions: {len(actions):,}")
    if len(actions) > 0:
        print("\nSuccess rate by action type (paid_in_full + partial_payment):")
        success_mask = actions["outcome"].isin(["paid_in_full", "partial_payment"])
        print(actions.assign(success=success_mask).groupby("action_type")["success"].mean().round(3))
    print(f"\nSaved to {out_dir}/")


if __name__ == "__main__":
    main()
