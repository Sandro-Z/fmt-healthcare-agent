#!/usr/bin/env python3
"""Build auditable pre-FMT / donor / post-FMT sample triplets.

Metadata determines pairing. Microbiome similarity must only validate a pair;
it must never be used to invent donor identities.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd


def _text(value: object) -> str:
    return "" if pd.isna(value) else str(value).strip()


def _days(timepoint: object, value: object, numeric: object) -> float | None:
    raw = pd.to_numeric(value, errors="coerce")
    if pd.isna(raw):
        raw = pd.to_numeric(numeric, errors="coerce")
    if pd.isna(raw):
        return None
    name = _text(timepoint).lower()
    factor = 1.0
    if "week" in name:
        factor = 7.0
    elif "month" in name:
        factor = 30.4375
    elif "year" in name:
        factor = 365.25
    return round(float(raw) * factor, 4)


def build_pairs(manifest_path: Path, match_path: Path) -> pd.DataFrame:
    manifest = pd.read_csv(manifest_path, sep="\t", dtype=str)
    required = {"queried_project", "sample_accession", "subject_id", "timepoint", "baseline_run"}
    missing = required - set(manifest.columns)
    if missing:
        raise ValueError(f"manifest missing columns: {sorted(missing)}")

    # Several sequencing runs may belong to one biological post-FMT sample.
    rows: list[dict[str, object]] = []
    for (project, accession), group in manifest.groupby(["queried_project", "sample_accession"], dropna=False, sort=True):
        baselines = sorted({_text(v) for v in group["baseline_run"] if _text(v)})
        subjects = sorted({_text(v) for v in group["subject_id"] if _text(v)})
        timepoints = sorted({_text(v) for v in group["timepoint"] if _text(v)})
        conflicts: list[str] = []
        if len(baselines) > 1:
            conflicts.append("multiple_baseline_runs")
        if len(subjects) > 1:
            conflicts.append("multiple_subject_ids")
        if len(timepoints) > 1:
            conflicts.append("multiple_timepoints")
        first = group.iloc[0]
        rows.append({
            "post_sample_id": f"{_text(project)}__{_text(accession)}",
            "project": _text(project),
            "post_sample_accession": _text(accession),
            "subject_id": subjects[0] if len(subjects) == 1 else "",
            "timepoint": timepoints[0] if len(timepoints) == 1 else _text(first.get("timepoint")),
            "timepoint_value": _text(first.get("timepoint_value")),
            "numeric_time": _text(first.get("numeric_time")),
            "post_run_accessions": ",".join(sorted({_text(v) for v in group["run_accession"] if _text(v)})),
            "baseline_recipient_run": baselines[0] if len(baselines) == 1 else "",
            "source_pairing_confidence": _text(first.get("pairing_confidence")),
            "metadata_conflicts": ",".join(conflicts),
        })
    post = pd.DataFrame(rows)

    match = pd.read_excel(match_path, dtype=str)
    match = match.loc[:, ~match.columns.astype(str).str.startswith("Unnamed")].copy()
    for column in ("sample_id", "group", "donor", "label", "disease", "sex", "age", "bmi", "batch", "location"):
        if column not in match:
            match[column] = ""
        match[column] = match[column].map(_text)
    recipient = match[match["group"].str.lower().eq("recipient")].drop_duplicates("sample_id", keep=False)
    recipient = recipient.rename(columns={
        "sample_id": "baseline_recipient_run", "donor": "baseline_donor_run",
        "label": "response_label", "batch": "baseline_project",
    })
    keep = ["baseline_recipient_run", "baseline_donor_run", "response_label", "disease", "sex", "age", "bmi", "baseline_project", "location"]
    paired = post.merge(recipient[keep], on="baseline_recipient_run", how="left", validate="many_to_one")
    known_samples = set(match["sample_id"])
    paired["post_time_days"] = paired.apply(lambda r: _days(r["timepoint"], r["timepoint_value"], r["numeric_time"]), axis=1)

    def assess(row: pd.Series) -> pd.Series:
        reasons: list[str] = []
        score = 0
        if row["metadata_conflicts"]:
            reasons.append(row["metadata_conflicts"])
        if row["subject_id"]:
            score += 10
        else:
            reasons.append("missing_subject_id")
        if row["baseline_recipient_run"]:
            score += 30
        else:
            reasons.append("missing_baseline_recipient")
        if _text(row.get("baseline_donor_run")):
            score += 30
            if row["baseline_donor_run"] in known_samples:
                score += 10
            else:
                reasons.append("donor_not_present_in_match_table")
        else:
            reasons.append("missing_donor_mapping")
        if row["baseline_project"] and row["baseline_project"] == row["project"]:
            score += 10
        elif row["baseline_project"]:
            reasons.append("project_mismatch")
        if row["post_time_days"] is not None and not pd.isna(row["post_time_days"]):
            score += 10
        else:
            reasons.append("time_not_numeric")
        usable = not row["metadata_conflicts"] and bool(_text(row.get("baseline_recipient_run"))) and bool(_text(row.get("baseline_donor_run")))
        confidence = "high" if usable and score >= 90 else "medium" if usable and score >= 70 else "unpaired"
        return pd.Series({"pair_score": score, "pair_confidence": confidence, "analysis_eligible": usable, "exclusion_reasons": ";".join(reasons)})

    return pd.concat([paired, paired.apply(assess, axis=1)], axis=1)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--match", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    pairs = build_pairs(args.manifest, args.match)
    pairs.to_csv(args.output_dir / "fmt_sample_triplets.tsv", sep="\t", index=False)
    eligible = pairs[pairs["analysis_eligible"]].copy()
    eligible.to_csv(args.output_dir / "fmt_analysis_ready_pairs.tsv", sep="\t", index=False)
    summary = {
        "post_sample_count": int(len(pairs)),
        "analysis_eligible_count": int(pairs["analysis_eligible"].sum()),
        "unpaired_count": int((~pairs["analysis_eligible"]).sum()),
        "confidence_counts": {str(k): int(v) for k, v in pairs["pair_confidence"].value_counts().items()},
        "project_counts": {str(k): int(v) for k, v in pairs.groupby("project")["post_sample_id"].count().items()},
        "eligible_project_counts": {str(k): int(v) for k, v in eligible.groupby("project")["post_sample_id"].count().items()},
        "unique_recipients": int(eligible["baseline_recipient_run"].nunique()),
        "unique_donors": int(eligible["baseline_donor_run"].nunique()),
    }
    (args.output_dir / "pairing_summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
