#!/usr/bin/env python3
"""Build a biological-sample processing manifest from the downloaded FMT runs."""

from __future__ import annotations

import argparse
import csv
import json
import re
from collections import defaultdict
from pathlib import Path


def safe_id(value: str) -> str:
    value = re.sub(r"[^A-Za-z0-9._-]+", "-", value.strip())
    return value.strip("-._") or "unknown"


def locate_run(raw_root: Path, run: str) -> dict:
    single = sorted(raw_root.rglob(f"{run}.fastq.gz"))
    r1 = sorted(raw_root.rglob(f"{run}_1.fastq.gz"))
    r2 = sorted(raw_root.rglob(f"{run}_2.fastq.gz"))
    if single and not (r1 or r2):
        if len(single) != 1:
            raise ValueError(f"{run}: expected one single-end file, found {len(single)}")
        files = [single[0]]
        return {
            "run_accession": run,
            "layout": "single",
            "single": str(single[0]),
            "bytes": sum(path.stat().st_size for path in files),
        }
    if not single and len(r1) == 1 and len(r2) == 1:
        files = [r1[0], r2[0]]
        return {
            "run_accession": run,
            "layout": "paired",
            "r1": str(r1[0]),
            "r2": str(r2[0]),
            "bytes": sum(path.stat().st_size for path in files),
        }
    raise ValueError(
        f"{run}: invalid FASTQ layout single={len(single)} r1={len(r1)} r2={len(r2)}"
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--raw-root", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    args = parser.parse_args()

    with args.manifest.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle, delimiter="\t"))
    if not rows:
        raise SystemExit("Input manifest is empty")

    grouped: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for row in rows:
        project = row.get("queried_project", "").strip() or "unknown_project"
        biological_sample = row.get("sample_accession", "").strip()
        if not biological_sample:
            biological_sample = "__".join(
                [
                    row.get("subject_id", "unknown_subject").strip(),
                    row.get("timepoint", "unknown_timepoint").strip(),
                    row.get("timepoint_value", "unknown_value").strip(),
                ]
            )
        grouped[(project, biological_sample)].append(row)

    groups_dir = args.output_dir / "groups"
    groups_dir.mkdir(parents=True, exist_ok=True)
    records = []
    errors = []

    for (project, biological_sample), group_rows in sorted(grouped.items()):
        sample_id = f"{safe_id(project)}__{safe_id(biological_sample)}"
        try:
            runs = [
                locate_run(args.raw_root, row["run_accession"].strip())
                for row in group_rows
            ]
        except (KeyError, ValueError) as exc:
            errors.append(f"{sample_id}\t{exc}")
            continue

        first = group_rows[0]
        layouts = sorted({run["layout"] for run in runs})
        record = {
            "sample_id": sample_id,
            "project": project,
            "sample_accession": biological_sample,
            "subject_id": first.get("subject_id", ""),
            "timepoint": first.get("timepoint", ""),
            "timepoint_value": first.get("timepoint_value", ""),
            "timepoint_class": first.get("timepoint_class", ""),
            "numeric_time": first.get("numeric_time", ""),
            "disease": first.get("disease", ""),
            "host_status": first.get("host_status", ""),
            "study_title": first.get("study_title", ""),
            "layouts": layouts,
            "run_count": len(runs),
            "total_bytes": sum(run["bytes"] for run in runs),
            "runs": runs,
        }
        group_file = groups_dir / f"{sample_id}.json"
        group_file.write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")
        record["group_file"] = str(group_file)
        records.append(record)

    args.output_dir.mkdir(parents=True, exist_ok=True)
    index_path = args.output_dir / "processing_manifest.tsv"
    columns = [
        "sample_id",
        "project",
        "sample_accession",
        "subject_id",
        "timepoint",
        "timepoint_value",
        "timepoint_class",
        "numeric_time",
        "layouts",
        "run_count",
        "total_bytes",
        "group_file",
    ]
    with index_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns, delimiter="\t", extrasaction="ignore")
        writer.writeheader()
        for record in records:
            output = dict(record)
            output["layouts"] = ",".join(record["layouts"])
            writer.writerow(output)

    metadata_path = args.output_dir / "sample_metadata.tsv"
    metadata_columns = [
        "sample_id",
        "project",
        "sample_accession",
        "subject_id",
        "timepoint",
        "timepoint_value",
        "timepoint_class",
        "numeric_time",
        "disease",
        "host_status",
        "study_title",
    ]
    with metadata_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle, fieldnames=metadata_columns, delimiter="\t", extrasaction="ignore"
        )
        writer.writeheader()
        writer.writerows(records)

    if errors:
        error_path = args.output_dir / "manifest_errors.tsv"
        error_path.write_text("sample_id\terror\n" + "\n".join(errors) + "\n", encoding="utf-8")
        raise SystemExit(f"Manifest validation failed for {len(errors)} groups; see {error_path}")

    print(f"groups={len(records)} runs={sum(r['run_count'] for r in records)}")
    print(index_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
