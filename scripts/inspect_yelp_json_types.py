#!/usr/bin/env python3
"""
Profile field types in the Yelp JSON dataset.

The Yelp academic JSON files are JSON Lines: one JSON object per line. This
script streams the gzip-compressed tar archive, samples rows from each JSON
table, and writes schema/type reports for modelling preparation.
"""

from __future__ import annotations

import argparse
import collections
import csv
import json
import math
import os
import re
import statistics
import tarfile
from pathlib import Path
from typing import Any


DEFAULT_ARCHIVE = "data/yelp_json_raw/yelp_dataset.tar"
DEFAULT_OUT_DIR = "data/yelp_json_profile"
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
DATETIME_RE = re.compile(r"^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}$")


def table_name(member_name: str) -> str:
    name = os.path.basename(member_name)
    return name.removeprefix("yelp_academic_dataset_").removesuffix(".json")


def value_type(value: Any) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "bool"
    if isinstance(value, int) and not isinstance(value, bool):
        return "int"
    if isinstance(value, float):
        return "float"
    if isinstance(value, str):
        if DATE_RE.match(value):
            return "date_string"
        if DATETIME_RE.match(value):
            return "datetime_string"
        return "string"
    if isinstance(value, list):
        return "list"
    if isinstance(value, dict):
        return "object"
    return type(value).__name__


def compact_example(value: Any, limit: int = 120) -> str:
    if isinstance(value, (dict, list)):
        text = json.dumps(value, ensure_ascii=False)
    else:
        text = "" if value is None else str(value)
    text = text.replace("\n", "\\n")
    return text[:limit]


def make_field_stat() -> dict:
    return {
        "present": 0,
        "null": 0,
        "types": collections.Counter(),
        "examples": {},
        "numeric_values": [],
        "string_lengths": [],
        "list_lengths": [],
        "nested_keys": collections.Counter(),
    }


def update_field_stat(stat: dict, value: Any) -> None:
    typ = value_type(value)
    stat["present"] += 1
    stat["types"][typ] += 1
    if typ == "null":
        stat["null"] += 1
    stat["examples"].setdefault(typ, compact_example(value))

    if isinstance(value, (int, float)) and not isinstance(value, bool):
        if math.isfinite(float(value)):
            stat["numeric_values"].append(value)
    elif isinstance(value, str):
        stat["string_lengths"].append(len(value))
    elif isinstance(value, list):
        stat["list_lengths"].append(len(value))
    elif isinstance(value, dict):
        stat["nested_keys"].update(value.keys())


def summarize_numbers(values: list[int | float]) -> dict:
    if not values:
        return {}
    return {
        "min": min(values),
        "max": max(values),
        "mean": round(statistics.mean(values), 4),
        "median": round(statistics.median(values), 4),
    }


def profile_json_member(member_file, sample_lines: int, count_all: bool) -> dict:
    rows_seen = 0
    rows_profiled = 0
    parse_errors = 0
    field_stats: dict[str, dict] = collections.defaultdict(make_field_stat)
    all_fields = collections.Counter()

    for raw_line in member_file:
        rows_seen += 1
        if rows_profiled >= sample_lines and not count_all:
            # Continue draining the member so the tar stream can reach later files.
            continue

        line = raw_line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            parse_errors += 1
            continue

        if rows_profiled < sample_lines:
            rows_profiled += 1
            all_fields.update(obj.keys())
            for key, value in obj.items():
                update_field_stat(field_stats[key], value)

    return {
        "rows_seen": rows_seen,
        "rows_profiled": rows_profiled,
        "parse_errors": parse_errors,
        "fields": all_fields,
        "field_stats": field_stats,
    }


def profile_archive(archive: str, sample_lines: int, count_all: bool) -> dict:
    profiles = {}
    with tarfile.open(archive, "r|*") as tar:
        for member in tar:
            if not member.isfile() or not member.name.endswith(".json"):
                continue
            f = tar.extractfile(member)
            if f is None:
                continue
            name = table_name(member.name)
            print(f"Profiling {name}...", flush=True)
            with f:
                profiles[name] = {
                    "member_name": member.name,
                    "size_bytes": member.size,
                    **profile_json_member(f, sample_lines, count_all),
                }
    return profiles


def write_reports(profiles: dict, out_dir: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)

    schema_json = {}
    table_rows = []
    field_rows = []
    nested_rows = []

    for name, profile in profiles.items():
        field_names = sorted(profile["field_stats"].keys())
        table_rows.append(
            {
                "table": name,
                "member_name": profile["member_name"],
                "size_bytes": profile["size_bytes"],
                "rows_seen": "" if profile["rows_seen"] is None else profile["rows_seen"],
                "rows_profiled": profile["rows_profiled"],
                "parse_errors": profile["parse_errors"],
                "field_count": len(field_names),
                "fields": "|".join(field_names),
            }
        )

        schema_json[name] = {
            "member_name": profile["member_name"],
            "size_bytes": profile["size_bytes"],
            "rows_seen": profile["rows_seen"],
            "rows_profiled": profile["rows_profiled"],
            "parse_errors": profile["parse_errors"],
            "fields": {},
        }

        for field, stat in sorted(profile["field_stats"].items()):
            types = dict(stat["types"].most_common())
            examples = stat["examples"]
            numeric_summary = summarize_numbers(stat["numeric_values"])
            string_summary = summarize_numbers(stat["string_lengths"])
            list_summary = summarize_numbers(stat["list_lengths"])
            nested_keys = dict(stat["nested_keys"].most_common())

            field_rows.append(
                {
                    "table": name,
                    "field": field,
                    "present_in_sample": stat["present"],
                    "null_in_sample": stat["null"],
                    "types": json.dumps(types, ensure_ascii=False),
                    "example": next(iter(examples.values()), ""),
                    "numeric_summary": json.dumps(numeric_summary, ensure_ascii=False),
                    "string_length_summary": json.dumps(string_summary, ensure_ascii=False),
                    "list_length_summary": json.dumps(list_summary, ensure_ascii=False),
                    "nested_key_count": len(nested_keys),
                }
            )

            for nested_key, count in nested_keys.items():
                nested_rows.append(
                    {
                        "table": name,
                        "field": field,
                        "nested_key": nested_key,
                        "present_in_sample": count,
                    }
                )

            schema_json[name]["fields"][field] = {
                "present_in_sample": stat["present"],
                "null_in_sample": stat["null"],
                "types": types,
                "examples": examples,
                "numeric_summary": numeric_summary,
                "string_length_summary": string_summary,
                "list_length_summary": list_summary,
                "nested_keys": nested_keys,
            }

    with (out_dir / "schema_summary.json").open("w", encoding="utf-8") as f:
        json.dump(schema_json, f, ensure_ascii=False, indent=2)

    def dump_csv(filename: str, rows: list[dict], fieldnames: list[str]) -> None:
        with (out_dir / filename).open("w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(rows)

    dump_csv(
        "table_summary.csv",
        table_rows,
        ["table", "member_name", "size_bytes", "rows_seen", "rows_profiled", "parse_errors", "field_count", "fields"],
    )
    dump_csv(
        "field_types.csv",
        field_rows,
        [
            "table",
            "field",
            "present_in_sample",
            "null_in_sample",
            "types",
            "example",
            "numeric_summary",
            "string_length_summary",
            "list_length_summary",
            "nested_key_count",
        ],
    )
    dump_csv(
        "nested_keys.csv",
        nested_rows,
        ["table", "field", "nested_key", "present_in_sample"],
    )


def print_field_types(profiles: dict) -> None:
    print("\nField Types")
    for table, profile in profiles.items():
        print(f"\n[{table}]")
        for field, stat in sorted(profile["field_stats"].items()):
            types = dict(stat["types"].most_common())
            example = next(iter(stat["examples"].values()), "")
            nested_keys = list(dict(stat["nested_keys"].most_common()).keys())
            line = (
                f"- {field}: types={types}, "
                f"present={stat['present']}, null={stat['null']}, "
                f"example={example}"
            )
            if nested_keys:
                line += f", nested_keys={nested_keys[:12]}"
            print(line)


def main() -> int:
    parser = argparse.ArgumentParser(description="Inspect Yelp JSON Lines field types.")
    parser.add_argument("archive", nargs="?", default=DEFAULT_ARCHIVE, help="Path to yelp_dataset.tar")
    parser.add_argument("--out-dir", default=DEFAULT_OUT_DIR)
    parser.add_argument("--sample-lines", type=int, default=1000, help="Rows to profile per JSON table")
    parser.add_argument("--count-all", action="store_true", help="Also count every row in each JSON file")
    parser.add_argument("--print-fields", action="store_true", help="Print all sampled field types to stdout")
    args = parser.parse_args()

    profiles = profile_archive(args.archive, args.sample_lines, args.count_all)
    write_reports(profiles, Path(args.out_dir))
    if args.print_fields:
        print_field_types(profiles)
    print(f"wrote reports to {args.out_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
