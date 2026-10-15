#!/usr/bin/env python3
"""Standalone inference CLI for the FMT triplet contrastive model.

Modes:
  embed    Convert an arbitrary species abundance table to model embeddings.
  rank     Rank candidate donors for one or more recipient samples.
  response Predict response probability and engraftment for aligned triplets.
"""
from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd


def read_table(path: Path) -> pd.DataFrame:
    suffix = path.suffix.lower()
    if suffix in {".xlsx", ".xls"}:
        frame = pd.read_excel(path, index_col=0)
    else:
        separator = "\t" if suffix in {".tsv", ".txt"} else ","
        frame = pd.read_csv(path, sep=separator, index_col=0)
    if frame.empty:
        raise ValueError(f"empty abundance table: {path}")
    frame.index = frame.index.astype(str)
    return frame


def canonical_species(name: str) -> str:
    return str(name).split("|")[-1].strip()


@dataclass
class AlignedBatch:
    sample_ids: list[str]
    standardized: np.ndarray
    embedding: np.ndarray
    audit: pd.DataFrame


class FMTTripletPredictor:
    def __init__(self, model_dir: Path) -> None:
        self.model_dir = model_dir.resolve()
        schema_path = self.model_dir / "feature_schema.json"
        artifact_path = self.model_dir / "fmt_triplet_contrastive_model.npz"
        self.schema = json.loads(schema_path.read_text(encoding="utf-8"))
        artifact = np.load(artifact_path)
        self.features = list(self.schema["features"])
        self.projection = artifact["projection"]
        self.scaler_mean = artifact["scaler_mean"]
        self.scaler_scale = artifact["scaler_scale"]
        self.classifier_coef = artifact["classifier_coef"]
        self.classifier_intercept = artifact["classifier_intercept"]
        expected = len(self.features)
        if self.projection.shape[0] != expected:
            raise ValueError("feature schema and projection dimensions do not match")
        if len(self.scaler_mean) != expected or len(self.scaler_scale) != expected:
            raise ValueError("feature schema and scaler dimensions do not match")

    @staticmethod
    def _to_percent(frame: pd.DataFrame, unit: str) -> pd.DataFrame:
        numeric = frame.apply(pd.to_numeric, errors="coerce").fillna(0.0)
        if (numeric < 0).any().any():
            raise ValueError("abundance values must be non-negative")
        totals = numeric.sum(axis=1)
        if (totals <= 0).any():
            bad = totals[totals <= 0].index.tolist()
            raise ValueError(f"zero-sum samples are not valid: {bad}")
        if unit == "count":
            return numeric.div(totals, axis=0) * 100.0
        if unit == "fraction":
            return numeric * 100.0
        if unit == "percent":
            return numeric
        if unit != "auto":
            raise ValueError("unit must be auto, percent, fraction, or count")
        median_total = float(totals.median())
        if 0.8 <= median_total <= 1.2:
            return numeric * 100.0
        if 80.0 <= median_total <= 120.0:
            return numeric
        return numeric.div(totals, axis=0) * 100.0

    def align(self, frame: pd.DataFrame, unit: str = "auto") -> AlignedBatch:
        canonical = frame.copy()
        canonical.columns = [canonical_species(column) for column in canonical.columns]
        canonical = canonical.T.groupby(level=0).sum().T
        percent = self._to_percent(canonical, unit)
        present = set(percent.columns)
        required = set(self.features)
        aligned = percent.reindex(columns=self.features, fill_value=0.0)
        abundance_coverage = aligned.sum(axis=1) / percent.sum(axis=1)
        logged = np.log(np.maximum(aligned.to_numpy(float), 0.0) + 1e-4)
        clr_values = logged - logged.mean(axis=1, keepdims=True)
        scale = np.where(self.scaler_scale == 0, 1.0, self.scaler_scale)
        standardized = (clr_values - self.scaler_mean) / scale
        embedding = standardized @ self.projection
        audit = pd.DataFrame(
            {
                "sample_id": percent.index.astype(str),
                "input_feature_count": percent.shape[1],
                "required_feature_count": len(self.features),
                "present_required_count": len(required & present),
                "feature_name_coverage": len(required & present) / len(required),
                "abundance_coverage": abundance_coverage.to_numpy(float),
                "extra_feature_count": len(present - required),
                "missing_feature_count": len(required - present),
                "input_total_percent": percent.sum(axis=1).to_numpy(float),
            }
        )
        return AlignedBatch(percent.index.astype(str).tolist(), standardized, embedding, audit)

    def embed(self, frame: pd.DataFrame, unit: str = "auto") -> AlignedBatch:
        return self.align(frame, unit)

    def rank(
        self,
        recipient: pd.DataFrame,
        donors: pd.DataFrame,
        recipient_unit: str = "auto",
        donor_unit: str = "auto",
    ) -> tuple[pd.DataFrame, pd.DataFrame]:
        recipient_batch = self.align(recipient, recipient_unit)
        donor_batch = self.align(donors, donor_unit)
        rows: list[dict[str, object]] = []
        for recipient_id, recipient_z in zip(recipient_batch.sample_ids, recipient_batch.embedding):
            distances = np.sum((donor_batch.embedding - recipient_z) ** 2, axis=1)
            order = np.argsort(distances)
            for rank, index in enumerate(order, start=1):
                rows.append(
                    {
                        "recipient_id": recipient_id,
                        "donor_id": donor_batch.sample_ids[int(index)],
                        "rank": rank,
                        "embedding_distance": float(distances[int(index)]),
                    }
                )
        audit = pd.concat(
            [
                recipient_batch.audit.assign(role="recipient"),
                donor_batch.audit.assign(role="donor"),
            ],
            ignore_index=True,
        )
        return pd.DataFrame(rows), audit

    def response(
        self,
        recipient: pd.DataFrame,
        donor: pd.DataFrame,
        post: pd.DataFrame,
        recipient_unit: str = "auto",
        donor_unit: str = "auto",
        post_unit: str = "auto",
    ) -> tuple[pd.DataFrame, pd.DataFrame]:
        batches = [
            self.align(recipient, recipient_unit),
            self.align(donor, donor_unit),
            self.align(post, post_unit),
        ]
        counts = {len(batch.sample_ids) for batch in batches}
        if len(counts) != 1:
            raise ValueError("recipient, donor, and post tables must have the same row count")
        zr, zd, zp = [batch.embedding for batch in batches]
        response_x = np.hstack([np.abs(zr - zd), np.abs(zp - zd), zp - zr])
        logits = response_x @ self.classifier_coef.T + self.classifier_intercept
        probability = 1.0 / (1.0 + np.exp(-np.clip(logits[:, 0], -40.0, 40.0)))
        engraftment = np.sum((zp - zr) ** 2, axis=1) - np.sum((zp - zd) ** 2, axis=1)
        result = pd.DataFrame(
            {
                "recipient_id": batches[0].sample_ids,
                "donor_id": batches[1].sample_ids,
                "post_id": batches[2].sample_ids,
                "response_probability": probability,
                "response_prediction": np.where(probability >= 0.5, "Res", "NoRes"),
                "engraftment_score": engraftment,
                "post_to_recipient_distance": np.sum((zp - zr) ** 2, axis=1),
                "post_to_donor_distance": np.sum((zp - zd) ** 2, axis=1),
            }
        )
        audit = pd.concat(
            [
                batches[0].audit.assign(role="recipient"),
                batches[1].audit.assign(role="donor"),
                batches[2].audit.assign(role="post"),
            ],
            ignore_index=True,
        )
        return result, audit


def save_batch(batch: AlignedBatch, output: Path) -> None:
    columns = [f"embedding_{index + 1:02d}" for index in range(batch.embedding.shape[1])]
    pd.DataFrame(batch.embedding, index=batch.sample_ids, columns=columns).to_csv(
        output, sep="\t", index_label="sample_id"
    )
    batch.audit.to_csv(output.with_name(output.stem + "_audit.tsv"), sep="\t", index=False)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model-dir", type=Path, required=True)
    subparsers = parser.add_subparsers(dest="mode", required=True)

    embed = subparsers.add_parser("embed")
    embed.add_argument("--samples", type=Path, required=True)
    embed.add_argument("--unit", choices=["auto", "percent", "fraction", "count"], default="auto")
    embed.add_argument("--output", type=Path, required=True)

    rank = subparsers.add_parser("rank")
    rank.add_argument("--recipient", type=Path, required=True)
    rank.add_argument("--donors", type=Path, required=True)
    rank.add_argument("--recipient-unit", default="auto", choices=["auto", "percent", "fraction", "count"])
    rank.add_argument("--donor-unit", default="auto", choices=["auto", "percent", "fraction", "count"])
    rank.add_argument("--output", type=Path, required=True)

    response = subparsers.add_parser("response")
    response.add_argument("--recipient", type=Path, required=True)
    response.add_argument("--donor", type=Path, required=True)
    response.add_argument("--post", type=Path, required=True)
    response.add_argument("--recipient-unit", default="auto", choices=["auto", "percent", "fraction", "count"])
    response.add_argument("--donor-unit", default="auto", choices=["auto", "percent", "fraction", "count"])
    response.add_argument("--post-unit", default="auto", choices=["auto", "percent", "fraction", "count"])
    response.add_argument("--output", type=Path, required=True)

    args = parser.parse_args()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    predictor = FMTTripletPredictor(args.model_dir)
    if args.mode == "embed":
        save_batch(predictor.embed(read_table(args.samples), args.unit), args.output)
        return
    if args.mode == "rank":
        result, audit = predictor.rank(
            read_table(args.recipient), read_table(args.donors), args.recipient_unit, args.donor_unit
        )
    else:
        result, audit = predictor.response(
            read_table(args.recipient), read_table(args.donor), read_table(args.post),
            args.recipient_unit, args.donor_unit, args.post_unit,
        )
    result.to_csv(args.output, sep="\t", index=False)
    audit.to_csv(args.output.with_name(args.output.stem + "_audit.tsv"), sep="\t", index=False)


if __name__ == "__main__":
    main()
