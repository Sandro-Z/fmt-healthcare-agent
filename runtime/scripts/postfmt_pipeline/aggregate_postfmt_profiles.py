#!/usr/bin/env python3
"""Aggregate MetaPhlAn, HUMAnN, and fastp outputs without truncating sample IDs."""

from __future__ import annotations

import argparse
import csv
import json
from collections import defaultdict
from pathlib import Path


def read_metaphlan(path: Path) -> tuple[dict[str, float], dict[str, str]]:
    abundance = {}
    taxids = {}
    with path.open(encoding="utf-8", errors="ignore") as handle:
        for line in handle:
            if not line.strip() or line.startswith("#"):
                continue
            parts = line.rstrip("\n").split("\t")
            if len(parts) < 3:
                continue
            clade, taxid, value = parts[:3]
            if "|s__" not in clade or "|t__" in clade:
                continue
            try:
                abundance[clade] = float(value)
            except ValueError:
                continue
            taxids[clade] = taxid
    return abundance, taxids


def read_humann(path: Path, stratified: bool) -> dict[str, float]:
    values = {}
    with path.open(encoding="utf-8", errors="ignore") as handle:
        for line in handle:
            if not line.strip() or line.startswith("#"):
                continue
            parts = line.rstrip("\n").split("\t")
            if len(parts) < 2:
                continue
            feature = parts[0]
            if ("|" in feature) != stratified:
                continue
            try:
                values[feature] = float(parts[1])
            except ValueError:
                continue
    return values


def write_matrix(path: Path, data: dict[str, dict[str, float]]) -> None:
    samples = sorted(data)
    features = sorted({feature for values in data.values() for feature in values})
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle, delimiter="\t", lineterminator="\n")
        writer.writerow(["sample_id", *features])
        for sample in samples:
            values = data[sample]
            writer.writerow([sample, *(f"{values.get(feature, 0.0):.12g}" for feature in features)])


def fastp_summary(qc_root: Path, sample_ids: list[str]) -> list[dict[str, str | int | float]]:
    output = []
    for sample_id in sample_ids:
        before_reads = after_reads = before_bases = after_bases = 0
        q30_bases = total_after_bases = 0
        run_count = 0
        for path in sorted((qc_root / sample_id).glob("*_fastp.json")):
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            summary = payload.get("summary", {})
            before = summary.get("before_filtering", {})
            after = summary.get("after_filtering", {})
            before_reads += int(before.get("total_reads", 0))
            after_reads += int(after.get("total_reads", 0))
            before_bases += int(before.get("total_bases", 0))
            after_bases += int(after.get("total_bases", 0))
            q30_bases += int(round(float(after.get("q30_rate", 0)) * int(after.get("total_bases", 0))))
            total_after_bases += int(after.get("total_bases", 0))
            run_count += 1
        output.append(
            {
                "sample_id": sample_id,
                "fastp_runs": run_count,
                "before_reads": before_reads,
                "after_reads": after_reads,
                "read_retention": after_reads / before_reads if before_reads else 0.0,
                "before_bases": before_bases,
                "after_bases": after_bases,
                "q30_rate_after": q30_bases / total_after_bases if total_after_bases else 0.0,
            }
        )
    return output


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--processed-root", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    args = parser.parse_args()

    metaphlan_dir = args.processed_root / "profiles" / "metaphlan"
    humann_dir = args.processed_root / "profiles" / "humann"
    args.output_dir.mkdir(parents=True, exist_ok=True)

    species = {}
    taxid_union = {}
    for path in sorted(metaphlan_dir.glob("*_profile.tsv")):
        sample_id = path.name[: -len("_profile.tsv")]
        values, taxids = read_metaphlan(path)
        species[sample_id] = values
        taxid_union.update({key: value for key, value in taxids.items() if value})
    if not species:
        raise SystemExit(f"No MetaPhlAn profiles found in {metaphlan_dir}")

    pathway_unstratified = {}
    pathway_stratified = {}
    genefamily_unstratified = {}
    for sample_id in sorted(species):
        pathway_file = humann_dir / f"{sample_id}_pathabundance_relab.tsv"
        gene_file = humann_dir / f"{sample_id}_genefamilies_relab.tsv"
        if pathway_file.is_file():
            pathway_unstratified[sample_id] = read_humann(pathway_file, stratified=False)
            pathway_stratified[sample_id] = read_humann(pathway_file, stratified=True)
        if gene_file.is_file():
            genefamily_unstratified[sample_id] = read_humann(gene_file, stratified=False)

    write_matrix(args.output_dir / "species_relative_abundance_percent.tsv", species)
    if pathway_unstratified:
        write_matrix(
            args.output_dir / "pathway_relative_abundance_unstratified.tsv",
            pathway_unstratified,
        )
        write_matrix(
            args.output_dir / "pathway_relative_abundance_stratified.tsv",
            pathway_stratified,
        )
    if genefamily_unstratified:
        write_matrix(
            args.output_dir / "genefamily_relative_abundance_unstratified.tsv",
            genefamily_unstratified,
        )

    with (args.output_dir / "species_taxid_map.tsv").open(
        "w", newline="", encoding="utf-8"
    ) as handle:
        writer = csv.writer(handle, delimiter="\t", lineterminator="\n")
        writer.writerow(["clade_name", "ncbi_tax_id"])
        writer.writerows(sorted(taxid_union.items()))

    qc_rows = fastp_summary(args.processed_root / "qc", sorted(species))
    with (args.output_dir / "fastp_sample_qc.tsv").open(
        "w", newline="", encoding="utf-8"
    ) as handle:
        columns = list(qc_rows[0])
        writer = csv.DictWriter(handle, fieldnames=columns, delimiter="\t", lineterminator="\n")
        writer.writeheader()
        writer.writerows(qc_rows)

    summary = {
        "metaphlan_samples": len(species),
        "humann_pathway_samples": len(pathway_unstratified),
        "humann_genefamily_samples": len(genefamily_unstratified),
        "species_features": len({feature for values in species.values() for feature in values}),
        "pathway_unstratified_features": len(
            {feature for values in pathway_unstratified.values() for feature in values}
        ),
    }
    (args.output_dir / "aggregation_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(summary, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
