#!/usr/bin/env python3
"""Plot a publication-grade 2D t-SNE view of fitted FMT triplet embeddings."""

from __future__ import annotations

import argparse
import importlib.util
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
import numpy as np
import pandas as pd
from sklearn.manifold import TSNE


def _load_predictor(script: Path):
    spec = importlib.util.spec_from_file_location("fmt_triplet_predictor", script)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Cannot import predictor: {script}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module.FMTTripletPredictor


def _read_abundance(path: Path, separator: str) -> pd.DataFrame:
    frame = pd.read_csv(path, sep=separator, index_col=0)
    frame.index = frame.index.astype(str)
    return frame


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fmt-root", type=Path, required=True)
    parser.add_argument("--model-dir", type=Path, required=True)
    parser.add_argument("--predictor", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True, help="PNG output path")
    parser.add_argument("--seed", type=int, default=20260831)
    parser.add_argument("--pair-only", action="store_true", help="Plot only donors and pre-FMT recipients")
    args = parser.parse_args()

    triplets = pd.read_csv(
        args.fmt_root / "postfmt_processed/analysis/sample_pairing_v2/fmt_sample_triplets.tsv",
        sep="\t",
    )
    baseline = _read_abundance(args.fmt_root / "species_abundance_train.csv", ",")
    post = _read_abundance(
        args.fmt_root / "postfmt_processed/matrices/species_relative_abundance_percent.tsv", "\t"
    )
    triplets = triplets.assign(
        recipient_id=triplets["baseline_recipient_run"].astype(str),
        donor_id=triplets["baseline_donor_run"].astype(str),
        post_id=triplets["post_sample_id"].astype(str),
    )
    valid = triplets[
        triplets["analysis_eligible"].astype(bool)
        & triplets["recipient_id"].isin(baseline.index)
        & triplets["donor_id"].isin(baseline.index)
        & triplets["post_id"].isin(post.index)
    ].copy()
    if valid.empty:
        raise RuntimeError("No complete FMT triplets were found")

    recipient_ids = valid["recipient_id"].drop_duplicates().tolist()
    donor_ids = valid["donor_id"].drop_duplicates().tolist()
    post_ids = [] if args.pair_only else valid["post_id"].drop_duplicates().tolist()
    Predictor = _load_predictor(args.predictor)
    predictor = Predictor(args.model_dir)
    recipient_embedding = predictor.align(baseline.loc[recipient_ids], "percent").embedding
    donor_embedding = predictor.align(baseline.loc[donor_ids], "percent").embedding
    embedding_parts = [recipient_embedding, donor_embedding]
    if post_ids:
        embedding_parts.append(predictor.align(post.loc[post_ids], "percent").embedding)
    embeddings = np.vstack(embedding_parts)
    perplexity = min(25.0, max(5.0, (len(embeddings) - 1) / 3.0))
    coordinates = TSNE(
        n_components=2,
        perplexity=perplexity,
        init="pca",
        learning_rate="auto",
        max_iter=2000,
        random_state=args.seed,
    ).fit_transform(embeddings)

    n_recipient = len(recipient_ids)
    n_donor = len(donor_ids)
    recipient_xy = dict(zip(recipient_ids, coordinates[:n_recipient]))
    donor_xy = dict(zip(donor_ids, coordinates[n_recipient:n_recipient + n_donor]))
    post_xy = dict(zip(post_ids, coordinates[n_recipient + n_donor:]))

    plt.rcParams.update({
        "font.family": "DejaVu Sans",
        "font.size": 12,
        "axes.titlesize": 18,
        "axes.labelsize": 14,
        "xtick.labelsize": 11,
        "ytick.labelsize": 11,
        "legend.fontsize": 12,
        "pdf.fonttype": 42,
        "ps.fonttype": 42,
    })
    fig, ax = plt.subplots(figsize=(12.8, 10.2))
    for row in valid.itertuples(index=False):
        rxy = recipient_xy[row.recipient_id]
        dxy = donor_xy[row.donor_id]
        ax.plot([rxy[0], dxy[0]], [rxy[1], dxy[1]], color="#586474", linestyle="--", linewidth=1.75, alpha=0.58, zorder=1)
        if not args.pair_only:
            pxy = post_xy[row.post_id]
            ax.plot([rxy[0], pxy[0]], [rxy[1], pxy[1]], color="#94A3B8", linestyle=":", linewidth=1.15, alpha=0.34, zorder=1)

    recipient_array = np.vstack([recipient_xy[sample_id] for sample_id in recipient_ids])
    donor_array = np.vstack([donor_xy[sample_id] for sample_id in donor_ids])
    ax.scatter(donor_array[:, 0], donor_array[:, 1], s=185, marker="o", c="#2878B5", edgecolors="white", linewidths=1.5, alpha=0.97, label=f"Donor (n={len(donor_ids)})", zorder=3)
    ax.scatter(recipient_array[:, 0], recipient_array[:, 1], s=225, marker="X", c="#F28E2B", edgecolors="white", linewidths=1.35, alpha=0.98, label=f"Pre-FMT recipient (n={len(recipient_ids)})", zorder=4)
    if post_ids:
        post_array = np.vstack([post_xy[sample_id] for sample_id in post_ids])
        ax.scatter(post_array[:, 0], post_array[:, 1], s=165, marker="s", c="#42A65A", edgecolors="white", linewidths=1.3, alpha=0.93, label=f"Post-FMT sample (n={len(post_ids)})", zorder=3)

    legend_handles, legend_labels = ax.get_legend_handles_labels()
    legend_handles.append(Line2D([0], [0], color="#586474", linestyle="--", linewidth=2.0))
    legend_labels.append("Donor–recipient pair")
    if not args.pair_only:
        legend_handles.append(Line2D([0], [0], color="#94A3B8", linestyle=":", linewidth=1.4))
        legend_labels.append("Recipient–post trajectory")
    ax.legend(legend_handles, legend_labels, loc="best", frameon=True, framealpha=0.96, borderpad=0.8)
    title = "t-SNE Projection of Donor–Recipient Embeddings" if args.pair_only else "t-SNE Projection of FMT Triplet Embeddings"
    subtitle = "Bold dashed lines indicate observed donor–recipient pairs" if args.pair_only else "Large markers show donors, pre-FMT recipients, and post-FMT samples"
    ax.set_title(f"{title}\n{subtitle}", pad=15)
    ax.set_xlabel("t-SNE Dimension 1")
    ax.set_ylabel("t-SNE Dimension 2")
    ax.grid(color="#D7DCE2", linewidth=0.65, alpha=0.55)
    ax.set_axisbelow(True)
    for spine in ax.spines.values():
        spine.set_linewidth(1.0)
        spine.set_color("#4B5563")
    fig.tight_layout()

    args.output.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(args.output, dpi=360, bbox_inches="tight", facecolor="white")
    fig.savefig(args.output.with_suffix(".pdf"), bbox_inches="tight", facecolor="white")
    fig.savefig(args.output.with_suffix(".svg"), bbox_inches="tight", facecolor="white")
    plt.close(fig)
    print(f"triplets={len(valid)} recipients={len(recipient_ids)} donors={len(donor_ids)} post={len(post_ids)}")
    print(args.output)


if __name__ == "__main__":
    main()
