# Loan Recovery Intelligence
### By Khoshaba Odesho

**Status: 🚧 In progress.** This replaces the earlier `Smart-Loan-recovery` notebook-only
project with a full pipeline matching the stack used across the rest of this portfolio
(FastAPI + Streamlit + Docker + Supabase), plus a real SQL layer and a collection-action
recommendation engine backed by logged historical outcomes rather than assumed constants.

## Project Structure

```
loan-recovery-intelligence/
├── assets/                      # branding
├── configs/
│   └── config.yaml
├── data/
│   ├── raw/                     # generated synthetic CSVs (gitignored)
│   └── processed/               # gitignored
├── sql/
│   ├── schema.sql               # Supabase table definitions (loan_recovery schema)
│   ├── views.sql                # views the app queries
│   └── queries/                 # analysis SQL
├── src/
│   ├── data_generation/         # synthetic relational dataset generator
│   ├── data_ingestion/          # load CSVs → Supabase
│   ├── feature_engineering/     # aggregate payment_history into model features
│   ├── models/                  # train default-risk model (MLflow)
│   ├── api/                     # FastAPI service + Streamlit dashboard
│   └── utils/
├── tests/
├── scripts/
├── models/                      # gitignored
├── .github/workflows/
├── Dockerfile
└── requirements.txt
```

## Build Log

- [x] Supabase schema created (`loan_recovery` schema, 4 tables — see `sql/schema.sql`)
- [x] Synthetic relational dataset generated (5,000 customers/loans, ~82K payment
      records, ~7K collection actions) — see `src/data_generation/generate_data.py`
- [x] Data loaded into Supabase — see `src/data_ingestion/load_to_supabase.py`
- [ ] SQL analysis layer (cohort default rates, delinquency trends, action success rates)
- [ ] Feature engineering from payment history
- [ ] Default-risk model (MLflow tracked)
- [ ] FastAPI service + costed recommendation engine
- [ ] Streamlit dashboard
- [ ] Docker + Hugging Face Spaces deployment
- [ ] Full README with live links, methodology, and worked examples

*(Full marketing README with live links, architecture diagram, and methodology
will replace this once the pipeline is built — same as the other projects.)*
