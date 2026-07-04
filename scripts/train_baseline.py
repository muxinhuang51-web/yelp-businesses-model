#!/usr/bin/env python3
"""Train standard-library baselines for Yelp business-month popularity."""

from __future__ import annotations

import argparse
import csv
import json
import math
import random
from pathlib import Path


DEFAULT_PANEL = "data/model/business_month_panel.csv"
DEFAULT_MODEL = "models/monthly_popularity_log_linear.json"
DEFAULT_METRICS = "reports/metrics.json"
DEFAULT_IMPORTANCE = "reports/feature_importance.csv"
DEFAULT_PREDICTIONS = "reports/predictions_sample.csv"

EXCLUDE_FIELDS = {
    "business_id",
    "month",
    "target_month",
    "split",
    "target_next_month_reviews",
}


def to_float(value: str) -> float:
    try:
        if value == "":
            return 0.0
        return float(value)
    except ValueError:
        return 0.0


def read_panel(path: str):
    with open(path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        fieldnames = reader.fieldnames or []
        feature_names = [name for name in fieldnames if name not in EXCLUDE_FIELDS]
        rows = []
        for row in reader:
            x = [to_float(row[name]) for name in feature_names]
            y = to_float(row["target_next_month_reviews"])
            rows.append(
                {
                    "business_id": row["business_id"],
                    "month": row["month"],
                    "target_month": row["target_month"],
                    "split": row["split"],
                    "x": x,
                    "y": y,
                    "baseline": to_float(row["review_count_1m"]),
                }
            )
    return feature_names, rows


def fit_scaler(rows, n_features: int):
    train = [r for r in rows if r["split"] == "train"]
    means = [0.0] * n_features
    for row in train:
        for i, value in enumerate(row["x"]):
            means[i] += value
    means = [value / max(len(train), 1) for value in means]

    variances = [0.0] * n_features
    for row in train:
        for i, value in enumerate(row["x"]):
            diff = value - means[i]
            variances[i] += diff * diff
    stds = [math.sqrt(value / max(len(train), 1)) or 1.0 for value in variances]
    return means, stds


def scale(x, means, stds):
    return [(value - means[i]) / stds[i] for i, value in enumerate(x)]


def train_log_linear(rows, means, stds, epochs: int, lr: float, l2: float, seed: int):
    train = [r for r in rows if r["split"] == "train"]
    n_features = len(means)
    weights = [0.0] * n_features
    bias = 0.0
    rng = random.Random(seed)

    for epoch in range(1, epochs + 1):
        rng.shuffle(train)
        total_loss = 0.0
        for row in train:
            x = scale(row["x"], means, stds)
            y = math.log1p(row["y"])
            pred = bias + sum(w * v for w, v in zip(weights, x))
            err = pred - y
            total_loss += err * err
            bias -= lr * err
            for i, value in enumerate(x):
                weights[i] -= lr * (err * value + l2 * weights[i])
        rmse = math.sqrt(total_loss / max(len(train), 1))
        print(f"epoch={epoch} train_log_rmse={rmse:.5f}", flush=True)

    return {"weights": weights, "bias": bias}


def percentile(values, q: float) -> float:
    if not values:
        return 0.0
    values = sorted(values)
    idx = min(max(int(round((len(values) - 1) * q)), 0), len(values) - 1)
    return values[idx]


def predict(row, model, means, stds):
    x = scale(row["x"], means, stds)
    raw = model["bias"] + sum(w * v for w, v in zip(model["weights"], x))
    cap = model.get("prediction_cap", None)
    if cap is not None:
        raw = min(raw, math.log1p(cap))
    return max(math.expm1(raw), 0.0)


def metrics_for(rows, model, means, stds, split: str):
    selected = [r for r in rows if r["split"] == split]
    if not selected:
        return {}

    abs_err = []
    sq_err = []
    sq_log_err = []
    base_abs_err = []
    base_sq_err = []
    base_sq_log_err = []
    for row in selected:
        y = row["y"]
        pred = predict(row, model, means, stds)
        base = max(row["baseline"], 0.0)
        abs_err.append(abs(pred - y))
        sq_err.append((pred - y) ** 2)
        sq_log_err.append((math.log1p(pred) - math.log1p(y)) ** 2)
        base_abs_err.append(abs(base - y))
        base_sq_err.append((base - y) ** 2)
        base_sq_log_err.append((math.log1p(base) - math.log1p(y)) ** 2)

    return {
        "rows": len(selected),
        "model_mae": sum(abs_err) / len(abs_err),
        "model_rmse": math.sqrt(sum(sq_err) / len(sq_err)),
        "model_rmsle": math.sqrt(sum(sq_log_err) / len(sq_log_err)),
        "baseline_mae": sum(base_abs_err) / len(base_abs_err),
        "baseline_rmse": math.sqrt(sum(base_sq_err) / len(base_sq_err)),
        "baseline_rmsle": math.sqrt(sum(base_sq_log_err) / len(base_sq_log_err)),
    }


def write_predictions(path: str, rows, model, means, stds, limit: int):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    selected = [r for r in rows if r["split"] == "test"][:limit]
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=[
                "business_id",
                "month",
                "target_month",
                "actual",
                "prediction",
                "baseline",
            ],
        )
        writer.writeheader()
        for row in selected:
            writer.writerow(
                {
                    "business_id": row["business_id"],
                    "month": row["month"],
                    "target_month": row["target_month"],
                    "actual": row["y"],
                    "prediction": round(predict(row, model, means, stds), 4),
                    "baseline": row["baseline"],
                }
            )


def write_feature_importance(path: str, feature_names, weights, stds):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    rows = []
    for name, weight, std in zip(feature_names, weights, stds):
        rows.append({"feature": name, "weight": weight, "importance": abs(weight)})
    rows.sort(key=lambda x: x["importance"], reverse=True)
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["feature", "weight", "importance"])
        writer.writeheader()
        writer.writerows(rows)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--panel", default=DEFAULT_PANEL)
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--metrics", default=DEFAULT_METRICS)
    parser.add_argument("--importance", default=DEFAULT_IMPORTANCE)
    parser.add_argument("--predictions", default=DEFAULT_PREDICTIONS)
    parser.add_argument("--epochs", type=int, default=8)
    parser.add_argument("--lr", type=float, default=0.003)
    parser.add_argument("--l2", type=float, default=1e-5)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    print("Reading panel...", flush=True)
    feature_names, rows = read_panel(args.panel)
    print(f"rows={len(rows):,} features={len(feature_names)}", flush=True)
    print("Fitting scaler...", flush=True)
    means, stds = fit_scaler(rows, len(feature_names))
    print("Training log-linear model...", flush=True)
    model = train_log_linear(rows, means, stds, args.epochs, args.lr, args.l2, args.seed)
    train_targets = [r["y"] for r in rows if r["split"] == "train"]
    model["prediction_cap"] = max(percentile(train_targets, 0.999), 1.0)
    print(f"prediction_cap={model['prediction_cap']}", flush=True)

    all_metrics = {split: metrics_for(rows, model, means, stds, split) for split in ["train", "valid", "test"]}
    Path(args.metrics).parent.mkdir(parents=True, exist_ok=True)
    with open(args.metrics, "w", encoding="utf-8") as f:
        json.dump(all_metrics, f, ensure_ascii=False, indent=2)
    Path(args.model).parent.mkdir(parents=True, exist_ok=True)
    with open(args.model, "w", encoding="utf-8") as f:
        json.dump(
            {
                "feature_names": feature_names,
                "means": means,
                "stds": stds,
                "model": model,
                "target": "next_month_review_count",
            },
            f,
            ensure_ascii=False,
            indent=2,
        )
    write_feature_importance(args.importance, feature_names, model["weights"], stds)
    write_predictions(args.predictions, rows, model, means, stds, limit=5000)
    print(json.dumps(all_metrics, ensure_ascii=False, indent=2), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
