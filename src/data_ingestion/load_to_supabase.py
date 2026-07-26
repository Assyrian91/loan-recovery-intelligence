"""
Load the synthetic CSVs in data/raw/ into the `loan_recovery` schema in
Supabase.

Uses direct psycopg2 connection on port 5432 (matching the pattern used
across the other Assyrian AI projects — the transaction pooler on 6543
is for Power BI/general use, direct 5432 for scripted ingestion).

Reads connection details from a .env file in the project root:

    DB_HOST=db.YOUR_PROJECT.supabase.co
    DB_PORT=5432
    DB_NAME=postgres
    DB_USER=postgres
    DB_PASSWORD=your_actual_password

.env is gitignored — never commit it.
"""

import os
import pandas as pd
import psycopg2
from psycopg2.extras import execute_values
from dotenv import load_dotenv

load_dotenv()  # reads variables from a .env file in the project root

DB_HOST = os.environ.get("DB_HOST")
DB_PORT = os.environ.get("DB_PORT", "5432")
DB_NAME = os.environ.get("DB_NAME", "postgres")
DB_USER = os.environ.get("DB_USER")
DB_PASSWORD = os.environ.get("DB_PASSWORD")

if not all([DB_HOST, DB_USER, DB_PASSWORD]):
    raise SystemExit(
        "Missing DB_HOST, DB_USER, or DB_PASSWORD. Make sure you have a .env "
        "file in the project root containing:\n"
        "DB_HOST=...\nDB_PORT=5432\nDB_NAME=postgres\nDB_USER=...\nDB_PASSWORD=..."
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
    df = df[columns]

    records = [tuple(row) for row in df.itertuples(index=False, name=None)]
    col_list = ", ".join(columns)
    query = f"INSERT INTO loan_recovery.{table_name} ({col_list}) VALUES %s"

    with conn.cursor() as cur:
        execute_values(cur, query, records, page_size=1000)
    conn.commit()
    print(f"  Loaded {len(records):,} rows into loan_recovery.{table_name}")


def main():
    conn = psycopg2.connect(
        host=DB_HOST, port=DB_PORT, dbname=DB_NAME,
        user=DB_USER, password=DB_PASSWORD,
    )
    try:
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