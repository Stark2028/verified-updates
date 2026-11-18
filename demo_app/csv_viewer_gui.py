"""CSV Inspector (desktop): open a CSV, filter rows, export, and summarize numbers.

A small Tkinter application distributed as a signed ZIP release. Authenticity
and integrity come from the verified-updates updater, not from this program.
Numeric summaries are enabled in later releases by the builder in
demo_app/bundle_gui.py. The headless paths (--self-test, --version, and
file + --export) mirror demo_app/csv_inspector.py.
"""

import argparse
import csv
import io
import json
import math
import subprocess
import sys
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, ttk

APP_VERSION = "1.0.0"
FEATURE_SUMMARIES = False

SAMPLE = "name,score\nalice,90\nbob,80\n"
SUMMARY_FIELDS = ("min", "max", "mean")


def load_rows(stream):
    reader = csv.DictReader(stream, strict=True)
    columns = reader.fieldnames or []
    if not columns or any(not name.strip() for name in columns) or len(set(columns)) != len(columns):
        raise ValueError("CSV must have unique, non-empty column names.")
    rows = []
    for row in reader:
        if None in row or None in row.values():
            raise ValueError(f"CSV row ending at line {reader.line_num} has the wrong number of fields.")
        rows.append(row)
    return columns, rows


def filter_rows(rows, contains: str) -> list[dict]:
    needle = contains.casefold()
    return [row for row in rows if any(needle in (value or "").casefold() for value in row.values())]


def numeric_summaries(rows, columns) -> dict:
    summaries = {}
    for column in columns:
        values, complete = [], True
        for row in rows:
            raw = (row.get(column) or "").strip()
            if not raw:
                continue
            try:
                value = float(raw)
            except ValueError:
                complete = False
                break
            if not math.isfinite(value):
                complete = False
                break
            values.append(value)
        if complete and values:
            summaries[column] = {"min": min(values), "max": max(values), "mean": math.fsum(values) / len(values)}
    return summaries


def version_info() -> int:
    print(json.dumps({"application": "CSV Inspector (desktop)", "version": APP_VERSION,
                      "numeric_summaries": FEATURE_SUMMARIES}))
    return 0


def self_test() -> int:
    columns, rows = load_rows(io.StringIO(SAMPLE))
    matched = filter_rows(rows, "alice")
    if columns != ["name", "score"] or len(matched) != 1 or matched[0]["score"] != "90":
        return 1
    if FEATURE_SUMMARIES:
        stats = numeric_summaries(matched, columns)
        if stats.get("score", {}).get("mean") != 90.0:
            return 1
    # Widget smoke: the desktop build must actually be usable on this host.
    root = tk.Tk()
    view = ttk.Treeview(root, columns=columns, height=3)
    view.destroy()
    root.destroy()
    print(json.dumps({"self_test": "passed", "version": APP_VERSION}))
    return 0


class Application:
    def __init__(self, root: tk.Tk, client_dir: Path | None, initial_file: Path | None,
                 initial_filter: str | None):
        self.root = root
        self.client_dir = client_dir
        self.source_file: Path | None = None
        self.columns: list[str] = []
        self.rows: list[dict] = []
        self.filtered: list[dict] = []

        root.title("CSV Inspector " + APP_VERSION + (" (numeric summaries)" if FEATURE_SUMMARIES else ""))
        root.geometry("820x480")

        toolbar = ttk.Frame(root, padding=(10, 8))
        toolbar.pack(fill="x")
        ttk.Button(toolbar, text="Open CSV", command=self.open_dialog).pack(side="left")
        self.filter_entry = ttk.Entry(toolbar, width=26)
        self.filter_entry.pack(side="left", padx=8)
        self.filter_entry.bind("<Return>", self.apply_filter)
        ttk.Button(toolbar, text="Filter", command=self.apply_filter).pack(side="left")
        ttk.Button(toolbar, text="Export filtered rows", command=self.export_dialog).pack(side="left")
        if client_dir is not None:
            ttk.Button(toolbar, text="Check for updates", command=self.check_updates).pack(side="right")

        table = ttk.Frame(root)
        table.pack(fill="both", expand=True)
        self.table = ttk.Treeview(table, show="headings")
        vsb = ttk.Scrollbar(table, orient="vertical", command=self.table.yview)
        hsb = ttk.Scrollbar(table, orient="horizontal", command=self.table.xview)
        self.table.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)
        self.table.grid(row=0, column=0, sticky="nsew")
        vsb.grid(row=0, column=1, sticky="ns")
        hsb.grid(row=1, column=0, sticky="ew")
        table.rowconfigure(0, weight=1)
        table.columnconfigure(0, weight=1)

        self.summaries = ttk.LabelFrame(root, text="Numeric summaries", padding=8)
        if FEATURE_SUMMARIES:
            self.summaries.pack(fill="x")

        self.status = ttk.Label(root, anchor="w", padding=(10, 4), text="Open a CSV to begin.")
        self.status.pack(fill="x")

        if initial_file is not None:
            self.load_file(initial_file)
        if initial_filter is not None:
            self.filter_entry.insert(0, initial_filter)
            self.apply_filter()

    def open_dialog(self) -> None:
        path = filedialog.askopenfilename(title="Open CSV", filetypes=[("CSV files", "*.csv"), ("All files", "*.*")])
        if path:
            self.load_file(Path(path))

    def load_file(self, path: Path) -> None:
        try:
            with path.open(encoding="utf-8-sig", newline="") as stream:
                self.columns, self.rows = load_rows(stream)
        except (OSError, ValueError, csv.Error) as exc:
            self.status.config(text=f"Could not open {path.name}: {exc}")
            return
        self.source_file = path
        self.filtered = list(self.rows)
        self.populate()
        self.status.config(text=f"{path.name}: {len(self.rows)} rows in {len(self.columns)} columns.")

    def populate(self) -> None:
        self.table.delete(*self.table.get_children())
        self.table["columns"] = self.columns
        for column in self.columns:
            self.table.heading(column, text=column)
            self.table.column(column, width=110, minwidth=60, anchor="w")
        for row in self.filtered:
            self.table.insert("", "end", values=[row.get(column, "") for column in self.columns])
        self.populate_summaries()

    def populate_summaries(self) -> None:
        for widget in self.summaries.winfo_children():
            widget.destroy()
        if not FEATURE_SUMMARIES:
            return
        stats = numeric_summaries(self.filtered, self.columns)
        if not stats:
            ttk.Label(self.summaries, text="No numeric columns in the displayed rows.").pack(anchor="w")
            return
        for column, values in stats.items():
            text = ", ".join(f"{field} {values[field]}" for field in SUMMARY_FIELDS)
            ttk.Label(self.summaries, text=f"{column}: {text}").pack(anchor="w")

    def apply_filter(self, _event=None) -> None:
        if self.source_file is None:
            self.status.config(text="Open a CSV before filtering.")
            return
        needle = self.filter_entry.get()
        self.filtered = filter_rows(self.rows, needle) if needle else list(self.rows)
        self.populate()
        self.status.config(text=f"{len(self.filtered)} of {len(self.rows)} rows match.")

    def export_dialog(self) -> None:
        if not self.filtered:
            self.status.config(text="Nothing to export.")
            return
        path = filedialog.asksaveasfilename(title="Export CSV", defaultextension=".csv")
        if path:
            self.export_to(Path(path))

    def export_to(self, path: Path) -> None:
        if self.source_file is not None and path.resolve() == self.source_file.resolve():
            self.status.config(text="Choose a different file so the source CSV is preserved.")
            return
        with path.open("w", encoding="utf-8", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=self.columns)
            writer.writeheader()
            writer.writerows(self.filtered)
        self.status.config(text=f"Exported {len(self.filtered)} rows to {path.name}.")

    def check_updates(self) -> None:
        """Call the verified updater CLI; this app has no update logic of its own."""
        self.status.config(text="Contacting the update repository...")
        self.root.update_idletasks()
        try:
            completed = subprocess.run(
                [sys.executable, "-m", "verified_updates", "client", "update", "--client", str(self.client_dir)],
                capture_output=True, text=True, timeout=90,
            )
            result = json.loads(completed.stdout)
        except (subprocess.TimeoutExpired, json.JSONDecodeError, OSError) as exc:
            self.status.config(text=f"Update check failed: {exc}")
            return
        outcome = result.get("outcome")
        if outcome == "updated":
            self.status.config(text=(f"Updated to {result.get('version')} (sequence {result.get('installed_after')}). "
                                    "Close and reopen the app to run the new version."))
        elif outcome == "up_to_date":
            self.status.config(text=f"Up to date: version {result.get('version')} is installed.")
        elif outcome == "rejected":
            self.status.config(text=f"Update rejected ({result.get('reason_code')}). The installed version remains active.")
        else:
            self.status.config(text=f"Update check failed: {result.get('detail')}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Open a CSV, filter rows, and export the result in a desktop view.")
    parser.add_argument("file", type=Path, nargs="?")
    parser.add_argument("--contains")
    parser.add_argument("--export", type=Path)
    parser.add_argument("--client-dir", type=Path)
    parser.add_argument("--version", action="store_true")
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        return self_test()
    if args.version:
        return version_info()
    if args.file is not None and args.export is not None:
        try:
            with args.file.open(encoding="utf-8-sig", newline="") as stream:
                columns, rows = load_rows(stream)
            filtered = filter_rows(rows, args.contains) if args.contains else rows
            if args.export.resolve() == args.file.resolve():
                raise ValueError("Choose a different path for the export to preserve the source CSV.")
            with args.export.open("w", encoding="utf-8", newline="") as stream:
                writer = csv.DictWriter(stream, fieldnames=columns)
                writer.writeheader()
                writer.writerows(filtered)
            result = {"application": "CSV Inspector (desktop)", "version": APP_VERSION,
                      "columns": columns, "row_count": len(filtered), "exported_to": str(args.export)}
            if FEATURE_SUMMARIES:
                result["numeric_summaries"] = numeric_summaries(filtered, columns)
            print(json.dumps(result, indent=2, allow_nan=False))
        except (OSError, ValueError, csv.Error) as exc:
            print(json.dumps({"error": str(exc)}))
            return 1
        return 0
    root = tk.Tk()
    Application(root, args.client_dir, args.file, args.contains)
    root.mainloop()
    return 0


if __name__ == "__main__":
    sys.exit(main())
