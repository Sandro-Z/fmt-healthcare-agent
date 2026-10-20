#!/usr/bin/env python3
"""Run biological-sample FMT profiling with bounded sample-level parallelism."""

from __future__ import annotations

import argparse
import csv
import os
import subprocess
import sys
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--processing-manifest", required=True, type=Path)
    parser.add_argument("--worker", required=True, type=Path)
    parser.add_argument("--threads-per-sample", type=int, default=8)
    parser.add_argument("--parallel-samples", type=int, default=2)
    parser.add_argument("--limit", type=int)
    parser.add_argument("--sample", action="append", default=[])
    parser.add_argument("--status-file", required=True, type=Path)
    args = parser.parse_args()

    if args.threads_per_sample < 1 or args.parallel_samples < 1:
        raise SystemExit("Thread and parallel counts must be positive")

    with args.processing_manifest.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle, delimiter="\t"))
    if args.sample:
        wanted = set(args.sample)
        rows = [row for row in rows if row["sample_id"] in wanted]
        missing = wanted - {row["sample_id"] for row in rows}
        if missing:
            raise SystemExit(f"Unknown sample IDs: {sorted(missing)}")

    rows.sort(key=lambda row: int(row["total_bytes"]))
    if args.limit is not None:
        rows = rows[: args.limit]
    if not rows:
        raise SystemExit("No samples selected")

    args.status_file.parent.mkdir(parents=True, exist_ok=True)
    states: dict[str, dict[str, str]] = {}
    status_lock = threading.Lock()

    def write_status() -> None:
        tmp = args.status_file.with_suffix(args.status_file.suffix + ".tmp")
        columns = ["sample_id", "state", "updated_at", "return_code", "group_file"]
        with tmp.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=columns, delimiter="\t")
            writer.writeheader()
            for sample_id in sorted(states):
                writer.writerow(states[sample_id])
        tmp.replace(args.status_file)

    def run_one(row: dict[str, str]) -> tuple[str, int]:
        sample_id = row["sample_id"]
        with status_lock:
            states[sample_id] = {
                "sample_id": sample_id,
                "state": "running",
                "updated_at": utc_now(),
                "return_code": "",
                "group_file": row["group_file"],
            }
            write_status()
        command = [
            "bash",
            str(args.worker),
            "--group-json",
            row["group_file"],
            "--threads",
            str(args.threads_per_sample),
        ]
        completed = subprocess.run(command, check=False)
        state = "complete" if completed.returncode == 0 else "failed"
        with status_lock:
            states[sample_id] = {
                "sample_id": sample_id,
                "state": state,
                "updated_at": utc_now(),
                "return_code": str(completed.returncode),
                "group_file": row["group_file"],
            }
            write_status()
        return sample_id, completed.returncode

    print(
        f"Selected {len(rows)} biological samples; "
        f"parallel={args.parallel_samples}, threads/sample={args.threads_per_sample}",
        flush=True,
    )
    failed = []
    with ThreadPoolExecutor(max_workers=args.parallel_samples) as pool:
        futures = {pool.submit(run_one, row): row for row in rows}
        for future in as_completed(futures):
            sample_id, return_code = future.result()
            print(f"{sample_id}\treturn_code={return_code}", flush=True)
            if return_code != 0:
                failed.append(sample_id)

    if failed:
        print(f"Failed samples ({len(failed)}): {','.join(sorted(failed))}", file=sys.stderr)
        return 1
    print(f"Completed {len(rows)} biological samples")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
