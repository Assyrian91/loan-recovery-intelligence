"""
Feature engineering for the loan default-risk model.

Pulls loan_recovery.v_current_delinquency (built in sql/views.sql) joined
with customer attributes, and produces a clean feature table.

IMPORTANT METHODOLOGY NOTE — read before training a model on this output
--------------------------------------------------------------------------
This script produces TWO outputs, not one, and they're used differently:

1. `all_loans_features.csv` — every loan, including still-`active` ones.
   Used for SCORING (i.e. what the live API will call to get a risk score
   for a real, currently-open loan).

2. `training_features.csv` — loans with either a resolved outcome
   (`paid_off`/`defaulted`) OR at least 18 months of observed history,
   with a binary `is_default` target.

Why not just "resolved" loans: a loan can only reach `paid_off` after
surviving its ENTIRE term, but can default at ANY point. Training only on
resolved loans therefore systematically excludes long-term loans that are
still healthy (they're stuck in "active" until term end), while every
default gets counted whenever it happens — inflating the apparent default
rate in the training set. This is a known issue in real credit-risk
"vintage" analysis (survivorship bias), not specific to synthetic data.

Fix used here: a loan counts as a legitimate negative (non-default)
example once it's been observed for >= 18 months, even if still
technically active — that's real evidence of good behavior, we don't
need to wait for full term completion to trust it.
"""

import os
import pandas as pd
import psycopg2
from dotenv import load_dotenv
from datetime import date

load_dotenv()

DB_HOST = os.environ.get("DB_HOST")
DB_PORT = os.environ.get("DB_PORT", "5432")
DB_NAME = os.environ.get("DB_NAME", "postgres")
DB_USER = os.environ.get("DB_USER")
DB_PASSWORD = os.environ.get("DB_PASSWORD")

if not all([DB_HOST, DB_USER, DB_PASSWORD]):
    raise SystemExit(
        "Missing DB_HOST, DB_USER, or DB_PASSWORD. Check your .env file."
    )

QUERY = """
SELECT
    v.loan_id,
    v.customer_id,
    v.status,
    v.principal,
    v.interest_rate,
    v.term_months,
    v.origination_date,
    v.total_payments_made,
    v.late_payment_count,
    v.pct_payments_late,
    v.avg_days_late,
    v.max_days_late_ever,
    v.most_recent_days_late,
    c.income,
    c.employment_status,
    c.age,
    c.credit_score
FROM loan_recovery.v_current_delinquency v
JOIN loan_recovery.customers c ON v.customer_id = c.customer_id;
"""


def fetch_raw_features() -> pd.DataFrame:
    conn = psycopg2.connect(
        host=DB_HOST, port=DB_PORT, dbname=DB_NAME,
        user=DB_USER, password=DB_PASSWORD,
    )
    try:
        df = pd.read_sql(QUERY, conn)
    finally:
        conn.close()
    return df


def add_derived_features(df: pd.DataFrame) -> pd.DataFrame:
    today = pd.Timestamp(date.today())
    df["origination_date"] = pd.to_datetime(df["origination_date"])
    df["loan_age_months"] = ((today - df["origination_date"]).dt.days / 30).round(1)

    # Missing values only occur for total_payments_made == 0 (brand new loan,
    # no payment history yet) — fill with 0, not the mean, since "no history
    # yet" is meaningfully different from "average behavior."
    fill_zero_cols = ["late_payment_count", "pct_payments_late", "avg_days_late",
                       "max_days_late_ever", "most_recent_days_late"]
    df[fill_zero_cols] = df[fill_zero_cols].fillna(0)

    return df


def main():
    print("Querying loan_recovery.v_current_delinquency + customers ...")
    df = fetch_raw_features()
    print(f"  Retrieved {len(df):,} loans")

    df = add_derived_features(df)

    os.makedirs("data/processed", exist_ok=True)

    # Output 1: every loan, for scoring
    df.to_csv("data/processed/all_loans_features.csv", index=False)
    print(f"Saved all_loans_features.csv ({len(df):,} rows, includes active loans)")

    # Output 2: training population.
    #
    # NOT just "resolved" loans (paid_off/defaulted) — a loan can only reach
    # paid_off after surviving its ENTIRE term, but can default at ANY point.
    # Requiring full resolution therefore systematically excludes long-term
    # loans that are still healthy (they're stuck in "active" until term end),
    # while every default gets counted whenever it happens. That inflates the
    # apparent default rate in the training set (survivorship bias — a known
    # issue in real credit risk "vintage" analysis, not specific to this
    # synthetic data).
    #
    # Fix: include a loan as a legitimate NEGATIVE (non-default) example once
    # it's been observed long enough to show risk (>= 18 months old), even if
    # still technically active — 20 months of clean payment history is real
    # evidence, we don't need to wait for full term completion to trust it.
    # Defaults are included regardless of age, since a default is conclusive
    # whenever it happens.
    MATURITY_THRESHOLD_MONTHS = 18
    training_mask = (
        (df["status"] == "defaulted")
        | (df["status"] == "paid_off")
        | (df["loan_age_months"] >= MATURITY_THRESHOLD_MONTHS)
    )
    resolved = df[training_mask].copy()
    resolved["is_default"] = (resolved["status"] == "defaulted").astype(int)
    resolved.to_csv("data/processed/training_features.csv", index=False)

    print(f"Saved training_features.csv ({len(resolved):,} loans: resolved + mature active)")
    print(f"  Default rate in training set: {resolved['is_default'].mean():.3f}")
    print(f"  ({resolved['is_default'].sum():,} defaulted / {len(resolved):,} total)")

    excluded = len(df) - len(resolved)
    print(f"\nExcluded {excluded:,} loans under {MATURITY_THRESHOLD_MONTHS} months old with unresolved status "
          f"(not enough time observed to trust as a negative example, and not yet defaulted).")


if __name__ == "__main__":
    main()