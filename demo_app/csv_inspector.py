"""A small useful CLI application; distributed as an authenticated ZIP bundle."""

import argparse
import csv
import io
import json
import math
from pathlib import Path
import sys

APP_VERSION = "1.0.0"
FEATURE_SUMMARIES = False


def inspect_csv(stream, contains: str | None = None):
    reader = csv.DictReader(stream, strict=True)
    columns = reader.fieldnames or []
    if not columns or any(not name.strip() for name in columns) or len(set(columns)) != len(columns):
        raise ValueError("CSV must have unique, non-empty column names.")
    needle = contains.casefold() if contains is not None else None
    rows = []
    for row in reader:
        if None in row or None in row.values():
            raise ValueError(f"CSV row ending at line {reader.line_num} has the wrong number of fields.")
        if needle is None or any(needle in value.casefold() for value in row.values()):
            rows.append(row)
    result = {"application": "CSV Inspector", "version": APP_VERSION, "columns": columns, "row_count": len(rows)}
    if FEATURE_SUMMARIES:
        summaries = {}
        for column in reader.fieldnames or []:
            try:
                values = [float(row[column]) for row in rows if row.get(column) not in (None, "")]
            except (TypeError, ValueError):
                continue
            if values and all(math.isfinite(value) for value in values):
                low, high = min(values), max(values)
                try:
                    mean = math.fsum(values) / len(values)
                except OverflowError:
                    mean = math.fsum(value / len(values) for value in values)
                summaries[column] = {"min": low, "max": high, "mean": mean}
        result["numeric_summaries"] = summaries
    return result, rows


def main() -> int:
    parser = argparse.ArgumentParser(description="Inspect a CSV, filter rows and export matching records.")
    parser.add_argument("file", type=Path, nargs="?")
    parser.add_argument("--contains")
    parser.add_argument("--export", type=Path)
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        result, rows = inspect_csv(io.StringIO("name,score\nalice,90\nbob,80\n"), "alice")
        if result["row_count"] != 1 or rows[0]["name"] != "alice":
            return 1
        if FEATURE_SUMMARIES and result["numeric_summaries"]["score"]["mean"] != 90:
            return 1
        print(json.dumps({"self_test": "passed", "version": APP_VERSION}))
        return 0
    if args.file is None:
        parser.error("provide a CSV file or --self-test")
    try:
        with args.file.open(encoding="utf-8-sig", newline="") as stream:
            result, rows = inspect_csv(stream, args.contains)
        if args.export:
            if args.export.exists() and args.export.samefile(args.file):
                raise ValueError("Choose a different path for the export to preserve the input CSV.")
            with args.export.open("w", encoding="utf-8", newline="") as stream:
                writer = csv.DictWriter(stream, fieldnames=result["columns"])
                writer.writeheader()
                writer.writerows(rows)
            result["exported_to"] = str(args.export)
    except (OSError, ValueError, csv.Error) as exc:
        parser.error(str(exc))
    print(json.dumps(result, indent=2, allow_nan=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())

