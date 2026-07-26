"""
Load the synthetic CSVs in data/raw/ into the `loan_recovery` schema in
Supabase.

Uses direct psycopg2 connection on port 5432 (matching the pattern used
across the other Assyrian AI projects — the transaction pooler on 6543
is for Power BI/general use, direct 5432 for scripted ingestion).

Set your connection string as an environment variable before running:

    setx SUPABASE_DB_URL "postgresql://postgres:[PASSWORD]@[HOST]:5432/postgres"

then restart your terminal so it picks up the variable, or just set it
for the current session:

    $env:SUPABASE_DB_URL = "postgresql://postgres:[PASSWORD]@[HOST]:5432/postgres"
"""

import os
import pandas as pd
import psycopg2
from psycopg2.extras import execute_values

DB_URL = os.environ.get("SUPABASE_DB_URL")
if not DB_URL:
    raise SystemExit(
        "SUPABASE_DB_URL environment variable not set. "
        "See the docstring at the top of this file for how to set it."
    )

DATA_DIR = "data/raw"

TABLES = [
    {
        "name": "customers",
        "csv": "customers.csv",
        "columns": ["customer_id", "income", "employment_status", "age", "city", "state", "credit_score"],
    },
    {
        "name": "loans",
        "csv": "loans.csv",
        "columns": ["loan_id", "customer_id", "principal", "interest_rate", "term_months", "origination_date", "status"],
    },
    {
        "name": "payment_history",
        "csv": "payment_history.csv",
        "columns": ["payment_id", "loan_id", "due_date", "amount_due", "amount_paid", "days_late"],
    },
    {
        "name": "collection_actions",
        "csv": "collection_actions.csv",
        "columns": ["action_id", "loan_id", "action_date", "action_type", "cost", "outcome"],
    },
]


def load_table(conn, table_name: str, csv_path: str, columns: list):
    df = pd.read_csv(csv_path)
    df = df[columns]  # enforce column order matches table definition

    records = [tuple(row) for row in df.itertuples(index=False, name=None)]
    col_list = ", ".join(columns)
    query = f"INSERT INTO loan_recovery.{table_name} ({col_list}) VALUES %s"

    with conn.cursor() as cur:
        execute_values(cur, query, records, page_size=1000)
    conn.commit()
    print(f"  Loaded {len(records):,} rows into loan_recovery.{table_name}")


def main():
    conn = psycopg2.connect(DB_URL)
    try:
        # Truncate first (in FK-safe order) so this script is safely re-runnable
        with conn.cursor() as cur:
            cur.execute("""
                TRUNCATE TABLE
                    loan_recovery.collection_actions,
                    loan_recovery.payment_history,
                    loan_recovery.loans,
                    loan_recovery.customers
                RESTART IDENTITY CASCADE;
            """)
        conn.commit()
        print("Cleared existing rows (safe re-run).\n")

        for table in TABLES:
            csv_path = os.path.join(DATA_DIR, table["csv"])
            print(f"Loading {csv_path} -> loan_recovery.{table['name']} ...")
            load_table(conn, table["name"], csv_path, table["columns"])

        print("\nDone. All tables loaded into the loan_recovery schema.")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
