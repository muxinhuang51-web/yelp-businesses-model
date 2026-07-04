#!/usr/bin/env python3
"""Build a business-month panel for Yelp monthly popularity prediction.

The output row is a business-month state at month t, and the label is the
business's new review count at month t+1.
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import json
import math
import os
import tarfile
from collections import defaultdict
from pathlib import Path


DEFAULT_ARCHIVE = "data/yelp_json_raw/yelp_dataset.tar"
DEFAULT_OUT = "data/model/business_month_panel.csv"
DEFAULT_SUMMARY = "data/model/panel_summary.json"
REVIEW_MEMBER = "yelp_academic_dataset_review.json"
USER_MEMBER = "yelp_academic_dataset_user.json"
BUSINESS_MEMBER = "yelp_academic_dataset_business.json"
LAST_COMPLETE_MONTH = "2021-12"


BUSINESS_FIELDS = [
    "business_stars",
    "business_review_count_log",
    "business_is_open",
    "business_category_count",
    "business_latitude",
    "business_longitude",
    "business_open_days",
    "business_has_attributes",
]

PANEL_FIELDS = [
    "business_id",
    "month",
    "target_month",
    "split",
    "target_next_month_reviews",
    "review_count_1m",
    "review_count_3m",
    "avg_stars_1m",
    "avg_text_len_1m",
    "feedback_count_1m_log",
    "avg_user_monthly_review_rate",
    "avg_user_positive_rating_tendency",
    "avg_user_account_age_days",
    "elite_user_ratio",
    "avg_user_rating_volatility",
    "avg_user_low_text_high_rating_ratio",
    "avg_user_popular_business_visit_ratio",
    "avg_user_friend_count_log",
    "avg_user_avg_review_text_length",
    "avg_user_feedback_per_review",
    *BUSINESS_FIELDS,
]


def parse_date(value: str) -> dt.datetime:
    return dt.datetime.strptime(value, "%Y-%m-%d %H:%M:%S")


def month_key(value: str) -> str:
    return value[:7]


def next_month(value: str) -> str:
    year, month = map(int, value.split("-"))
    month += 1
    if month == 13:
        year += 1
        month = 1
    return f"{year:04d}-{month:02d}"


def month_start(value: str) -> dt.date:
    year, month = map(int, value.split("-"))
    return dt.date(year, month, 1)


def safe_float(value, default: float = 0.0) -> float:
    try:
        if value is None:
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def safe_int(value, default: int = 0) -> int:
    try:
        if value is None:
            return default
        return int(value)
    except (TypeError, ValueError):
        return default


def iter_member_lines(archive: str, member_name: str):
    with tarfile.open(archive, "r|*") as tar:
        for member in tar:
            if member.name != member_name:
                continue
            f = tar.extractfile(member)
            if f is None:
                return
            with f:
                for raw in f:
                    if raw.strip():
                        yield raw
            return
    raise FileNotFoundError(member_name)


def count_csv_list(value: str | None) -> int:
    if not value or value == "None":
        return 0
    return len([part for part in value.split(",") if part.strip()])


def count_elite_years(value: str | None) -> int:
    if not value:
        return 0
    return len([part for part in value.split(",") if part.strip()])


def read_business_features(archive: str) -> dict[str, dict[str, float]]:
    features: dict[str, dict[str, float]] = {}
    for raw in iter_member_lines(archive, BUSINESS_MEMBER):
        obj = json.loads(raw)
        categories = obj.get("categories") or ""
        hours = obj.get("hours") or {}
        attrs = obj.get("attributes") or {}
        features[obj["business_id"]] = {
            "business_stars": safe_float(obj.get("stars")),
            "business_review_count_log": math.log1p(safe_int(obj.get("review_count"))),
            "business_is_open": safe_int(obj.get("is_open")),
            "business_category_count": count_csv_list(categories),
            "business_latitude": safe_float(obj.get("latitude")),
            "business_longitude": safe_float(obj.get("longitude")),
            "business_open_days": len(hours) if isinstance(hours, dict) else 0,
            "business_has_attributes": 1 if isinstance(attrs, dict) and attrs else 0,
        }
    return features


def read_user_features(archive: str, cutoff_date: dt.date) -> dict[str, dict[str, float]]:
    features: dict[str, dict[str, float]] = {}
    compliment_fields = [
        "compliment_hot",
        "compliment_more",
        "compliment_profile",
        "compliment_cute",
        "compliment_list",
        "compliment_note",
        "compliment_plain",
        "compliment_cool",
        "compliment_funny",
        "compliment_writer",
        "compliment_photos",
    ]

    for raw in iter_member_lines(archive, USER_MEMBER):
        obj = json.loads(raw)
        review_count = max(safe_int(obj.get("review_count")), 0)
        yelping_since = parse_date(obj["yelping_since"]).date()
        account_age_months = max((cutoff_date - yelping_since).days / 30.4375, 1.0)
        feedback_total = safe_int(obj.get("useful")) + safe_int(obj.get("funny")) + safe_int(obj.get("cool"))
        compliment_total = sum(safe_int(obj.get(name)) for name in compliment_fields)
        features[obj["user_id"]] = {
            "monthly_review_rate": review_count / account_age_months,
            "positive_rating_tendency": safe_float(obj.get("average_stars")),
            "account_start_ordinal": float(yelping_since.toordinal()),
            "elite_year_count": float(count_elite_years(obj.get("elite"))),
            "friend_count_log": math.log1p(count_csv_list(obj.get("friends"))),
            "feedback_per_review": feedback_total / max(review_count, 1),
            "compliment_total_log": math.log1p(compliment_total),
            # Placeholders for review-history features that are recomputed below
            # when available at panel build time.
            "rating_volatility": 0.0,
            "low_text_high_rating_ratio": 0.0,
            "popular_business_visit_ratio": 0.0,
            "avg_review_text_length": 0.0,
        }
    return features


def update_user_review_history(
    archive: str,
    user_features: dict[str, dict[str, float]],
    business_features: dict[str, dict[str, float]],
    last_complete_month: str,
    max_reviews: int | None,
) -> None:
    review_counts = sorted(
        (feat.get("business_review_count_log", 0.0) for feat in business_features.values())
    )
    if review_counts:
        popular_threshold = review_counts[int(len(review_counts) * 0.8)]
    else:
        popular_threshold = 0.0

    # count, star_sum, star_sq_sum, low_text_high_rating, popular_business_visit,
    # text_len_sum
    stats = defaultdict(lambda: [0.0] * 6)
    processed = 0
    for raw in iter_member_lines(archive, REVIEW_MEMBER):
        obj = json.loads(raw)
        m = month_key(obj["date"])
        if m > last_complete_month:
            continue
        uid = obj["user_id"]
        if uid not in user_features:
            continue
        stars = safe_float(obj.get("stars"))
        text_len = len(obj.get("text") or "")
        biz = business_features.get(obj["business_id"], {})
        stat = stats[uid]
        stat[0] += 1.0
        stat[1] += stars
        stat[2] += stars * stars
        stat[3] += 1.0 if text_len < 50 and stars >= 4.0 else 0.0
        stat[4] += 1.0 if biz.get("business_review_count_log", 0.0) >= popular_threshold else 0.0
        stat[5] += text_len
        processed += 1
        if max_reviews is not None and processed >= max_reviews:
            break
        if processed and processed % 1_000_000 == 0:
            print(f"  review history rows: {processed:,}", flush=True)

    for uid, stat in stats.items():
        n = max(stat[0], 1.0)
        mean = stat[1] / n
        variance = max(stat[2] / n - mean * mean, 0.0)
        user_features[uid]["rating_volatility"] = math.sqrt(variance)
        user_features[uid]["low_text_high_rating_ratio"] = stat[3] / n
        user_features[uid]["popular_business_visit_ratio"] = stat[4] / n
        user_features[uid]["avg_review_text_length"] = stat[5] / n


def make_agg() -> list[float]:
    # count, stars, text_len, feedback, user_monthly_rate, user_avg_stars,
    # user_account_age, elite_user, user_rating_vol, low_text_high_rating,
    # popular_visit, friend_count_log, avg_review_text_len, feedback_per_review
    return [0.0] * 14


def add_review_to_agg(agg: list[float], obj: dict, user_feat: dict[str, float], review_month: str) -> None:
    count = 1.0
    text = obj.get("text") or ""
    stars = safe_float(obj.get("stars"))
    feedback = safe_int(obj.get("useful")) + safe_int(obj.get("funny")) + safe_int(obj.get("cool"))
    account_age_days = max(month_start(review_month).toordinal() - user_feat.get("account_start_ordinal", 0.0), 0.0)

    agg[0] += count
    agg[1] += stars
    agg[2] += len(text)
    agg[3] += feedback
    agg[4] += user_feat.get("monthly_review_rate", 0.0)
    agg[5] += user_feat.get("positive_rating_tendency", 0.0)
    agg[6] += account_age_days
    agg[7] += 1.0 if user_feat.get("elite_year_count", 0.0) > 0 else 0.0
    agg[8] += user_feat.get("rating_volatility", 0.0)
    agg[9] += user_feat.get("low_text_high_rating_ratio", 0.0)
    agg[10] += user_feat.get("popular_business_visit_ratio", 0.0)
    agg[11] += user_feat.get("friend_count_log", 0.0)
    agg[12] += user_feat.get("avg_review_text_length", 0.0)
    agg[13] += user_feat.get("feedback_per_review", 0.0)


def split_for_target_month(target_month: str) -> str:
    if target_month <= "2020-12":
        return "train"
    if target_month <= "2021-06":
        return "valid"
    return "test"


def build_panel(
    archive: str,
    output_path: str,
    summary_path: str,
    max_reviews: int | None,
    last_complete_month: str,
) -> None:
    out_path = Path(output_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    cutoff = month_start(last_complete_month)
    print("Reading business features...", flush=True)
    business_features = read_business_features(archive)
    print(f"  businesses: {len(business_features)}", flush=True)

    print("Reading user features...", flush=True)
    user_features = read_user_features(archive, cutoff)
    print(f"  users: {len(user_features)}", flush=True)

    print("Computing user review-history features...", flush=True)
    update_user_review_history(archive, user_features, business_features, last_complete_month, max_reviews)

    print("Aggregating reviews by business-month...", flush=True)
    monthly = defaultdict(make_agg)
    processed = 0
    skipped_future = 0
    for raw in iter_member_lines(archive, REVIEW_MEMBER):
        obj = json.loads(raw)
        m = month_key(obj["date"])
        if m > last_complete_month:
            skipped_future += 1
            continue
        user_feat = user_features.get(obj["user_id"])
        if user_feat is None:
            continue
        add_review_to_agg(monthly[(obj["business_id"], m)], obj, user_feat, m)
        processed += 1
        if max_reviews is not None and processed >= max_reviews:
            break
        if processed and processed % 1_000_000 == 0:
            print(f"  processed reviews: {processed:,}", flush=True)

    print(f"  processed reviews: {processed:,}", flush=True)
    print(f"  skipped reviews after {last_complete_month}: {skipped_future:,}", flush=True)
    print(f"  business-month states: {len(monthly):,}", flush=True)

    print("Writing panel...", flush=True)
    rows = 0
    split_counts = defaultdict(int)
    with out_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=PANEL_FIELDS)
        writer.writeheader()
        for (business_id, month), agg in sorted(monthly.items()):
            target_month = next_month(month)
            if target_month > last_complete_month:
                continue
            target_agg = monthly.get((business_id, target_month))
            target = int(target_agg[0]) if target_agg else 0
            n = max(agg[0], 1.0)
            prev_2 = monthly.get((business_id, previous_month(month)), make_agg())[0]
            prev_3 = monthly.get((business_id, previous_month(previous_month(month))), make_agg())[0]
            biz = business_features.get(business_id, {})
            split = split_for_target_month(target_month)
            row = {
                "business_id": business_id,
                "month": month,
                "target_month": target_month,
                "split": split,
                "target_next_month_reviews": target,
                "review_count_1m": int(agg[0]),
                "review_count_3m": int(agg[0] + prev_2 + prev_3),
                "avg_stars_1m": agg[1] / n,
                "avg_text_len_1m": agg[2] / n,
                "feedback_count_1m_log": math.log1p(max(agg[3], 0.0)),
                "avg_user_monthly_review_rate": agg[4] / n,
                "avg_user_positive_rating_tendency": agg[5] / n,
                "avg_user_account_age_days": agg[6] / n,
                "elite_user_ratio": agg[7] / n,
                "avg_user_rating_volatility": agg[8] / n,
                "avg_user_low_text_high_rating_ratio": agg[9] / n,
                "avg_user_popular_business_visit_ratio": agg[10] / n,
                "avg_user_friend_count_log": agg[11] / n,
                "avg_user_avg_review_text_length": agg[12] / n,
                "avg_user_feedback_per_review": agg[13] / n,
            }
            for field in BUSINESS_FIELDS:
                row[field] = biz.get(field, 0.0)
            writer.writerow(row)
            rows += 1
            split_counts[split] += 1

    summary = {
        "output": output_path,
        "rows": rows,
        "split_counts": dict(split_counts),
        "review_rows_processed": processed,
        "business_month_states": len(monthly),
        "last_complete_month": last_complete_month,
    }
    Path(summary_path).parent.mkdir(parents=True, exist_ok=True)
    with open(summary_path, "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)
    print(json.dumps(summary, ensure_ascii=False, indent=2), flush=True)


def previous_month(value: str) -> str:
    year, month = map(int, value.split("-"))
    month -= 1
    if month == 0:
        year -= 1
        month = 12
    return f"{year:04d}-{month:02d}"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--archive", default=DEFAULT_ARCHIVE)
    parser.add_argument("--output", default=DEFAULT_OUT)
    parser.add_argument("--summary", default=DEFAULT_SUMMARY)
    parser.add_argument("--max-reviews", type=int, default=None)
    parser.add_argument("--last-complete-month", default=LAST_COMPLETE_MONTH)
    args = parser.parse_args()

    build_panel(args.archive, args.output, args.summary, args.max_reviews, args.last_complete_month)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
