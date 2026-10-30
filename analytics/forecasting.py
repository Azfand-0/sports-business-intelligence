"""Attendance and revenue forecasting.

Trains and compares a Linear Regression baseline against a Random Forest
on game-level features to predict two targets that front-office staff
plan around every week: expected Attendance and expected Revenue for an
upcoming fixture.

With only 46 home games across two seasons, this is a small-data problem
by ML standards. That actually matches a club's real planning cadence
(one model refresh per game week), but it means the R^2 figures below
should be read as directional, not as a production forecast.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestRegressor
from sklearn.linear_model import LinearRegression
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import OneHotEncoder
from sklearn.compose import ColumnTransformer
from sklearn.pipeline import Pipeline

from analytics.db_utils import read_table
from config.config import resolve_path, load_config
from etl.logging_utils import get_logger

logger = get_logger(__name__)
CFG = load_config()

NUMERIC_FEATURES = ["Temperature", "OpponentRanking", "WinStreak", "Month"]
CATEGORICAL_FEATURES = ["DayOfWeek", "Weather", "Competition"]
BOOLEAN_FEATURES = ["PromotionNight", "IsWeekend", "IsHoliday", "IsRivalGame"]
FEATURE_COLUMNS = NUMERIC_FEATURES + CATEGORICAL_FEATURES + BOOLEAN_FEATURES


def _load_home_games_with_revenue() -> pd.DataFrame:
    games = read_table("games")
    ticket_sales = read_table("ticket_sales")

    home = games[games["HomeAway"] == "Home"].copy()
    game_revenue = ticket_sales.groupby("GameID")["Revenue"].sum().rename("GameRevenue")
    home = home.merge(game_revenue, on="GameID", how="left")
    home["GameRevenue"] = home["GameRevenue"].fillna(0.0)

    for col in BOOLEAN_FEATURES:
        home[col] = home[col].astype(int)
    return home


def _build_pipeline(model) -> Pipeline:
    preprocessor = ColumnTransformer(
        transformers=[
            ("num", "passthrough", NUMERIC_FEATURES + BOOLEAN_FEATURES),
            ("cat", OneHotEncoder(handle_unknown="ignore"), CATEGORICAL_FEATURES),
        ]
    )
    return Pipeline(steps=[("preprocess", preprocessor), ("model", model)])


def _evaluate(y_true: np.ndarray, y_pred: np.ndarray) -> dict[str, float]:
    return {
        "MAE": round(mean_absolute_error(y_true, y_pred), 2),
        "RMSE": round(float(np.sqrt(mean_squared_error(y_true, y_pred))), 2),
        "R2": round(r2_score(y_true, y_pred), 3),
    }


def _feature_importance(pipeline: Pipeline, model_name: str) -> pd.DataFrame:
    """Extract a feature -> importance/coefficient table from a fitted pipeline."""
    ohe: OneHotEncoder = pipeline.named_steps["preprocess"].named_transformers_["cat"]
    cat_names = list(ohe.get_feature_names_out(CATEGORICAL_FEATURES))
    feature_names = NUMERIC_FEATURES + BOOLEAN_FEATURES + cat_names

    model = pipeline.named_steps["model"]
    if hasattr(model, "feature_importances_"):
        values = model.feature_importances_
    else:
        values = np.abs(model.coef_)
    return pd.DataFrame({"Feature": feature_names, "Importance": values, "Model": model_name}).sort_values(
        "Importance", ascending=False
    )


def train_and_compare(target_col: str, games: pd.DataFrame) -> dict:
    """Train Linear Regression and Random Forest for one target and compare them."""
    X = games[FEATURE_COLUMNS]
    y = games[target_col]

    X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.25, random_state=42)

    results = {}
    importances = []
    for name, model in [
        ("Linear Regression", LinearRegression()),
        ("Random Forest", RandomForestRegressor(n_estimators=300, max_depth=5, random_state=42)),
    ]:
        pipeline = _build_pipeline(model)
        pipeline.fit(X_train, y_train)
        preds = pipeline.predict(X_test)
        results[name] = _evaluate(y_test.to_numpy(), preds)
        importances.append(_feature_importance(pipeline, name))

    return {
        "target": target_col,
        "metrics": results,
        "feature_importance": pd.concat(importances, ignore_index=True),
        "n_train": len(X_train),
        "n_test": len(X_test),
    }


def run_forecasting(persist: bool = True) -> dict[str, dict]:
    """Run attendance and revenue forecasting and optionally write a report."""
    logger.info("Loading home game data for forecasting")
    home_games = _load_home_games_with_revenue()

    attendance_result = train_and_compare("Attendance", home_games)
    revenue_result = train_and_compare("GameRevenue", home_games)

    logger.info("Attendance model metrics: %s", attendance_result["metrics"])
    logger.info("Revenue model metrics: %s", revenue_result["metrics"])

    if persist:
        _write_report(attendance_result, revenue_result)

    return {"attendance": attendance_result, "revenue": revenue_result}


def _write_report(attendance_result: dict, revenue_result: dict) -> None:
    reports_dir = resolve_path(CFG["paths"]["reports_dir"])
    reports_dir.mkdir(parents=True, exist_ok=True)

    lines = ["# Forecasting Model Report", ""]
    lines.append(
        f"Trained on {attendance_result['n_train']} games, evaluated on "
        f"{attendance_result['n_test']} held-out games (small-sample caveat applies)."
    )
    for label, result in [("Attendance", attendance_result), ("Revenue", revenue_result)]:
        lines.append(f"\n## {label} Forecast")
        lines.append("| Model | MAE | RMSE | R2 |")
        lines.append("|---|---|---|---|")
        for model_name, metrics in result["metrics"].items():
            lines.append(f"| {model_name} | {metrics['MAE']} | {metrics['RMSE']} | {metrics['R2']} |")
        lines.append(f"\n### Top Feature Importance ({label})")
        top_features = (
            result["feature_importance"]
            .sort_values("Importance", ascending=False)
            .groupby("Model")
            .head(5)
        )
        lines.append(top_features.to_markdown(index=False))

    (reports_dir / "forecasting_report.md").write_text("\n".join(lines), encoding="utf-8")
    logger.info("Forecasting report written to %s", reports_dir / "forecasting_report.md")


if __name__ == "__main__":
    run_forecasting()
