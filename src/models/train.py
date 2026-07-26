"""
Train the loan default-risk model.

Uses training_features.csv (built by src/feature_engineering/build_features.py)
— loans with either a resolved outcome or >= 18 months of observed history,
see that script's docstring for why "resolved-only" would have been biased.

Model: Random Forest Classifier (same choice as the churn-pipeline project,
for consistency across the portfolio). class_weight='balanced' is used
because the target is imbalanced (~12% default rate) — without it, a naive
model could get ~88% accuracy just by always predicting "no default," which
would be useless. Balanced class weights make the model actually learn to
distinguish the minority class, at some cost to raw accuracy — which is
why accuracy alone is not reported as the headline metric below; AUC,
precision, and recall matter more for an imbalanced target like this.

Tracked with MLflow, same as churn-pipeline and hotel-intelligence.
"""

import pandas as pd
import numpy as np
import mlflow
import mlflow.sklearn
import joblib
import os

from sklearn.model_selection import train_test_split
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import (
    accuracy_score, precision_score, recall_score, f1_score,
    roc_auc_score, confusion_matrix, classification_report
)

DATA_PATH = "data/processed/training_features.csv"
MODEL_OUTPUT_PATH = "models/loan_default_model.joblib"

NUMERIC_FEATURES = [
    "principal", "interest_rate", "term_months",
    "total_payments_made", "late_payment_count", "pct_payments_late",
    "avg_days_late", "max_days_late_ever", "most_recent_days_late",
    "income", "age", "credit_score", "loan_age_months",
]
CATEGORICAL_FEATURES = ["employment_status"]
TARGET = "is_default"


def load_and_prepare():
    df = pd.read_csv(DATA_PATH)

    X = df[NUMERIC_FEATURES + CATEGORICAL_FEATURES].copy()
    X = pd.get_dummies(X, columns=CATEGORICAL_FEATURES, drop_first=True)
    y = df[TARGET]

    return X, y


def main():
    print("Loading training data...")
    X, y = load_and_prepare()
    print(f"  {len(X):,} rows, {X.shape[1]} features, {y.mean():.3f} default rate")

    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.2, random_state=42, stratify=y
    )

    mlflow.set_tracking_uri("sqlite:///mlflow.db")
    mlflow.set_experiment("loan-default-risk")

    with mlflow.start_run():
        params = {
            "n_estimators": 200,
            "max_depth": 8,
            "min_samples_leaf": 10,
            "class_weight": "balanced",
            "random_state": 42,
        }
        mlflow.log_params(params)

        print("\nTraining Random Forest Classifier...")
        model = RandomForestClassifier(**params)
        model.fit(X_train, y_train)

        y_pred = model.predict(X_test)
        y_proba = model.predict_proba(X_test)[:, 1]

        metrics = {
            "accuracy": accuracy_score(y_test, y_pred),
            "precision": precision_score(y_test, y_pred),
            "recall": recall_score(y_test, y_pred),
            "f1": f1_score(y_test, y_pred),
            "auc": roc_auc_score(y_test, y_proba),
        }
        mlflow.log_metrics(metrics)

        print("\n--- Evaluation (on held-out 20% test set) ---")
        for name, value in metrics.items():
            print(f"  {name.capitalize():<10}: {value:.4f}")

        print("\nConfusion Matrix (rows=actual, cols=predicted, [0=no default, 1=default]):")
        print(confusion_matrix(y_test, y_pred))

        print("\nFull classification report:")
        print(classification_report(y_test, y_pred, target_names=["No Default", "Default"]))

        print("\nTop 10 most important features:")
        importances = pd.Series(model.feature_importances_, index=X.columns)
        print(importances.sort_values(ascending=False).head(10).round(4))

        os.makedirs("models", exist_ok=True)
        joblib.dump(model, MODEL_OUTPUT_PATH)
        mlflow.log_artifact(MODEL_OUTPUT_PATH)
        print(f"\nModel saved to {MODEL_OUTPUT_PATH}")

        # Save the exact feature column order/names for the API to reuse later
        feature_columns_path = "models/feature_columns.txt"
        with open(feature_columns_path, "w") as f:
            f.write("\n".join(X.columns))
        mlflow.log_artifact(feature_columns_path)
        print(f"Feature column order saved to {feature_columns_path}")


if __name__ == "__main__":
    main()