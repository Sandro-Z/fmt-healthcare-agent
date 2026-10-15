#!/usr/bin/env python3
"""Create publication-grade metrics, tables, and figures from FMT OOF results."""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import seaborn as sns
from scipy.stats import mannwhitneyu
from sklearn.calibration import calibration_curve
from sklearn.metrics import (
    accuracy_score,
    average_precision_score,
    balanced_accuracy_score,
    brier_score_loss,
    confusion_matrix,
    f1_score,
    matthews_corrcoef,
    precision_recall_curve,
    precision_score,
    recall_score,
    roc_auc_score,
    roc_curve,
)


SEED = 20260830
BOOTSTRAPS = 2000
COLORS = {"model": "#087E8B", "baseline": "#F05D5E", "neutral": "#4C566A"}


def safe_divide(numerator: float, denominator: float) -> float:
    return float(numerator / denominator) if denominator else math.nan


def classification_metrics(y: np.ndarray, probability: np.ndarray) -> dict[str, float]:
    prediction = (probability >= 0.5).astype(int)
    tn, fp, fn, tp = confusion_matrix(y, prediction, labels=[0, 1]).ravel()
    return {
        "n": int(len(y)),
        "prevalence": float(y.mean()),
        "accuracy": float(accuracy_score(y, prediction)),
        "balanced_accuracy": float(balanced_accuracy_score(y, prediction)) if len(np.unique(y)) == 2 else math.nan,
        "sensitivity": safe_divide(tp, tp + fn),
        "specificity": safe_divide(tn, tn + fp),
        "precision_ppv": safe_divide(tp, tp + fp),
        "negative_predictive_value": safe_divide(tn, tn + fn),
        "f1": float(f1_score(y, prediction)),
        "mcc": float(matthews_corrcoef(y, prediction)),
        "roc_auc": float(roc_auc_score(y, probability)) if len(np.unique(y)) == 2 else math.nan,
        "pr_auc": float(average_precision_score(y, probability)) if len(np.unique(y)) == 2 else math.nan,
        "brier_score": float(brier_score_loss(y, probability)),
        "tp": int(tp),
        "tn": int(tn),
        "fp": int(fp),
        "fn": int(fn),
    }


def rank_metrics(ranks: np.ndarray) -> dict[str, float]:
    return {
        "mrr": float(np.mean(1.0 / ranks)),
        "mean_rank": float(np.mean(ranks)),
        "median_rank": float(np.median(ranks)),
        "recall_at_1": float(np.mean(ranks <= 1)),
        "recall_at_3": float(np.mean(ranks <= 3)),
        "recall_at_5": float(np.mean(ranks <= 5)),
        "recall_at_10": float(np.mean(ranks <= 10)),
    }


def percentile_ci(values: list[float]) -> dict[str, float]:
    array = np.asarray([x for x in values if np.isfinite(x)], dtype=float)
    return {
        "mean": float(np.mean(array)),
        "ci95_low": float(np.quantile(array, 0.025)),
        "ci95_high": float(np.quantile(array, 0.975)),
    }


def bootstrap_metrics(frame: pd.DataFrame) -> tuple[dict[str, dict[str, float]], dict[str, dict[str, float]]]:
    rng = np.random.default_rng(SEED)
    classification_samples: dict[str, list[float]] = {}
    ranking_samples: dict[str, list[float]] = {}
    n = len(frame)
    for _ in range(BOOTSTRAPS):
        sample = frame.iloc[rng.integers(0, n, n)]
        y = sample["response_label"].eq("Res").to_numpy(int)
        if len(np.unique(y)) == 2:
            current = classification_metrics(y, sample["response_probability"].to_numpy(float))
            for key, value in current.items():
                if key not in {"n", "tp", "tn", "fp", "fn"}:
                    classification_samples.setdefault(key, []).append(float(value))
        model_rank = rank_metrics(sample["donor_rank"].to_numpy(float))
        baseline_rank = rank_metrics(sample["baseline_donor_rank"].to_numpy(float))
        for key, value in model_rank.items():
            ranking_samples.setdefault(f"model_{key}", []).append(value)
        for key, value in baseline_rank.items():
            ranking_samples.setdefault(f"baseline_{key}", []).append(value)
        ranking_samples.setdefault("mrr_difference", []).append(model_rank["mrr"] - baseline_rank["mrr"])
    return (
        {key: percentile_ci(values) for key, values in classification_samples.items()},
        {key: percentile_ci(values) for key, values in ranking_samples.items()},
    )


def setup_style() -> None:
    sns.set_theme(style="whitegrid", context="paper", font_scale=1.15)
    plt.rcParams.update(
        {
            "figure.dpi": 140,
            "savefig.dpi": 300,
            "font.family": "DejaVu Sans",
            "axes.spines.top": False,
            "axes.spines.right": False,
            "axes.titleweight": "bold",
            "axes.labelweight": "regular",
            "pdf.fonttype": 42,
            "ps.fonttype": 42,
        }
    )


def save_figure(fig: plt.Figure, output: Path, stem: str) -> None:
    for suffix in ["png", "pdf", "svg"]:
        fig.savefig(output / f"{stem}.{suffix}", bbox_inches="tight", facecolor="white")
    plt.close(fig)


def plot_roc_pr(frame: pd.DataFrame, output: Path) -> None:
    y = frame["response_label"].eq("Res").to_numpy(int)
    probability = frame["response_probability"].to_numpy(float)
    fpr, tpr, _ = roc_curve(y, probability)
    precision, recall, _ = precision_recall_curve(y, probability)
    roc_auc = roc_auc_score(y, probability)
    pr_auc = average_precision_score(y, probability)
    fig, axes = plt.subplots(1, 2, figsize=(10.2, 4.3))
    axes[0].plot(fpr, tpr, color=COLORS["model"], linewidth=2.4, label=f"Triplet model (AUC={roc_auc:.3f})")
    axes[0].plot([0, 1], [0, 1], linestyle="--", color="#9AA0A6", linewidth=1.2, label="Chance")
    axes[0].set(xlabel="False positive rate", ylabel="True positive rate", title="A  Response ROC curve")
    axes[0].legend(frameon=False, loc="lower right")
    axes[1].plot(recall, precision, color=COLORS["model"], linewidth=2.4, label=f"Triplet model (AP={pr_auc:.3f})")
    axes[1].axhline(y.mean(), linestyle="--", color="#9AA0A6", linewidth=1.2, label=f"Prevalence={y.mean():.3f}")
    axes[1].set(xlabel="Recall", ylabel="Precision", title="B  Response precision–recall curve")
    axes[1].legend(frameon=False, loc="upper right")
    fig.tight_layout()
    save_figure(fig, output, "fig1_response_roc_pr")


def plot_calibration_confusion(frame: pd.DataFrame, output: Path) -> None:
    y = frame["response_label"].eq("Res").to_numpy(int)
    probability = frame["response_probability"].to_numpy(float)
    prediction = (probability >= 0.5).astype(int)
    fraction, mean_probability = calibration_curve(y, probability, n_bins=6, strategy="quantile")
    matrix = confusion_matrix(y, prediction, labels=[0, 1])
    fig, axes = plt.subplots(1, 2, figsize=(9.4, 4.2))
    axes[0].plot([0, 1], [0, 1], linestyle="--", color="#9AA0A6", linewidth=1.2)
    axes[0].plot(mean_probability, fraction, marker="o", color=COLORS["model"], linewidth=2.2)
    axes[0].set(xlim=(0, 1), ylim=(0, 1), xlabel="Mean predicted probability", ylabel="Observed response rate", title="A  Calibration")
    sns.heatmap(matrix, annot=True, fmt="d", cmap="Blues", cbar=False, square=True, ax=axes[1], annot_kws={"fontsize": 13})
    axes[1].set_xticklabels(["NoRes", "Res"])
    axes[1].set_yticklabels(["NoRes", "Res"], rotation=0)
    axes[1].set(xlabel="Predicted", ylabel="Observed", title="B  Confusion matrix (threshold=0.5)")
    fig.tight_layout()
    save_figure(fig, output, "fig2_calibration_confusion")


def plot_ranking(frame: pd.DataFrame, output: Path) -> None:
    max_rank = int(max(frame["donor_rank"].max(), frame["baseline_donor_rank"].max()))
    k = np.arange(1, max_rank + 1)
    model = np.asarray([(frame["donor_rank"] <= value).mean() for value in k])
    baseline = np.asarray([(frame["baseline_donor_rank"] <= value).mean() for value in k])
    fig, axes = plt.subplots(1, 2, figsize=(10.2, 4.3))
    axes[0].step(k, model, where="post", linewidth=2.3, color=COLORS["model"], label="Triplet model")
    axes[0].step(k, baseline, where="post", linewidth=2.0, color=COLORS["baseline"], label="Fixed CLR-distance baseline")
    axes[0].set(xlabel="Candidate rank K", ylabel="Recall@K", title="A  Cumulative donor retrieval", xlim=(1, max_rank), ylim=(0, 1.02))
    axes[0].legend(frameon=False, loc="lower right")
    paired = frame[["donor_rank", "baseline_donor_rank"]].rename(columns={"donor_rank": "Triplet model", "baseline_donor_rank": "Fixed baseline"})
    long = paired.melt(var_name="Method", value_name="Actual donor rank")
    sns.boxplot(data=long, x="Method", y="Actual donor rank", hue="Method", palette=[COLORS["model"], COLORS["baseline"]], width=0.55, legend=False, ax=axes[1])
    rng = np.random.default_rng(SEED)
    for _, row in paired.iterrows():
        jitter = rng.normal(0, 0.018, 2)
        axes[1].plot(np.arange(2) + jitter, row.to_numpy(float), color="#9AA0A6", alpha=0.18, linewidth=0.55)
    axes[1].set(title="B  Paired actual-donor ranks", xlabel="", ylabel="Rank (lower is better)")
    fig.tight_layout()
    save_figure(fig, output, "fig3_donor_ranking")


def plot_fold_metrics(metrics: pd.DataFrame, output: Path) -> None:
    selected = {
        "response_roc_auc": "ROC-AUC",
        "response_pr_auc": "PR-AUC",
        "response_f1": "F1",
        "response_balanced_accuracy": "Balanced accuracy",
        "mrr": "MRR",
        "recall_at_1": "Recall@1",
        "recall_at_5": "Recall@5",
    }
    long = metrics[["fold", *selected]].melt(id_vars="fold", var_name="metric", value_name="value")
    long["metric"] = long["metric"].map(selected)
    fig, ax = plt.subplots(figsize=(10.4, 4.7))
    sns.boxplot(data=long, x="metric", y="value", color="#B8E0E3", width=0.5, fliersize=0, ax=ax)
    sns.stripplot(data=long, x="metric", y="value", hue="fold", palette="viridis", size=5.5, jitter=0.11, ax=ax)
    ax.set(xlabel="", ylabel="Fold metric", title="Five-fold patient-level cross-validation")
    ax.tick_params(axis="x", rotation=25)
    ax.legend(title="Fold", frameon=False, ncol=5, loc="upper center", bbox_to_anchor=(0.5, -0.25))
    fig.tight_layout()
    save_figure(fig, output, "fig4_fold_metrics")


def plot_training(history: pd.DataFrame, output: Path) -> None:
    summary = history.groupby("epoch").agg(
        triplet_mean=("triplet_loss", "mean"), triplet_sd=("triplet_loss", "std"),
        trajectory_mean=("trajectory_loss", "mean"), trajectory_sd=("trajectory_loss", "std"),
        active_mean=("active_triplets", "mean"), active_sd=("active_triplets", "std"),
    ).reset_index()
    fig, axes = plt.subplots(1, 3, figsize=(13.0, 3.9))
    specs = [
        ("triplet_mean", "triplet_sd", "Triplet loss"),
        ("trajectory_mean", "trajectory_sd", "Trajectory loss"),
        ("active_mean", "active_sd", "Active triplet fraction"),
    ]
    for ax, (mean_col, sd_col, title) in zip(axes, specs):
        x = summary["epoch"].to_numpy(float)
        mean = summary[mean_col].to_numpy(float)
        sd = summary[sd_col].fillna(0).to_numpy(float)
        ax.plot(x, mean, color=COLORS["model"], linewidth=2.0)
        ax.fill_between(x, mean - sd, mean + sd, color=COLORS["model"], alpha=0.18, linewidth=0)
        ax.set(xlabel="Epoch", ylabel=title, title=title)
    fig.suptitle("Training convergence across five folds", fontweight="bold", y=1.02)
    fig.tight_layout()
    save_figure(fig, output, "fig5_training_convergence")


def plot_engraftment(frame: pd.DataFrame, output: Path) -> dict[str, float]:
    response = frame.loc[frame["response_label"].eq("Res"), "engraftment_score"].to_numpy(float)
    no_response = frame.loc[frame["response_label"].eq("NoRes"), "engraftment_score"].to_numpy(float)
    statistic, p_value = mannwhitneyu(response, no_response, alternative="two-sided")
    rank_biserial = 2.0 * statistic / (len(response) * len(no_response)) - 1.0
    fig, ax = plt.subplots(figsize=(5.8, 4.5))
    order = ["NoRes", "Res"]
    sns.violinplot(data=frame, x="response_label", y="engraftment_score", order=order, inner=None, cut=0, palette=[COLORS["baseline"], COLORS["model"]], hue="response_label", legend=False, ax=ax)
    sns.boxplot(data=frame, x="response_label", y="engraftment_score", order=order, width=0.28, showfliers=False, boxprops={"facecolor": "white", "alpha": 0.8}, ax=ax)
    sns.stripplot(data=frame, x="response_label", y="engraftment_score", order=order, color="#30343B", alpha=0.62, size=3.6, jitter=0.16, ax=ax)
    ax.set(xlabel="Clinical response", ylabel="Engraftment score", title="Response-associated engraftment")
    ax.text(0.5, 0.98, f"Mann–Whitney p={p_value:.3g}; rank-biserial r={rank_biserial:.3f}", transform=ax.transAxes, ha="center", va="top", fontsize=9)
    fig.tight_layout()
    save_figure(fig, output, "fig6_engraftment_by_response")
    return {"mann_whitney_u": float(statistic), "p_value": float(p_value), "rank_biserial": float(rank_biserial)}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--results", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    setup_style()
    frame = pd.read_csv(args.results / "oof_predictions.tsv", sep="\t")
    folds = pd.read_csv(args.results / "fold_metrics.tsv", sep="\t")
    history = pd.read_csv(args.results / "training_history.tsv", sep="\t")
    y = frame["response_label"].eq("Res").to_numpy(int)
    probability = frame["response_probability"].to_numpy(float)
    pooled_classification = classification_metrics(y, probability)
    model_ranking = rank_metrics(frame["donor_rank"].to_numpy(float))
    baseline_ranking = rank_metrics(frame["baseline_donor_rank"].to_numpy(float))
    classification_ci, ranking_ci = bootstrap_metrics(frame)
    per_project = []
    for project, group in frame.groupby("project"):
        metrics = classification_metrics(group["response_label"].eq("Res").to_numpy(int), group["response_probability"].to_numpy(float))
        metrics["project"] = project
        metrics.update({f"donor_{key}": value for key, value in rank_metrics(group["donor_rank"].to_numpy(float)).items()})
        per_project.append(metrics)
    per_project_frame = pd.DataFrame(per_project)
    per_project_frame.to_csv(args.output / "table_per_project_metrics.tsv", sep="\t", index=False)
    plot_roc_pr(frame, args.output)
    plot_calibration_confusion(frame, args.output)
    plot_ranking(frame, args.output)
    plot_fold_metrics(folds, args.output)
    plot_training(history, args.output)
    engraftment = plot_engraftment(frame, args.output)
    paper_metrics = {
        "validation_design": "5-fold patient-level out-of-fold",
        "n_patients": len(frame),
        "classification_pooled": pooled_classification,
        "classification_patient_bootstrap_95ci": classification_ci,
        "donor_ranking_model": model_ranking,
        "donor_ranking_fixed_clr_baseline": baseline_ranking,
        "ranking_patient_bootstrap_95ci": ranking_ci,
        "engraftment_group_test": engraftment,
        "notes": [
            "All plotted response scores are out-of-fold predictions.",
            "The comparator is a fixed CLR-distance baseline, not the previously trained contrastive_model.pt.",
            "Bootstrap confidence intervals use 2,000 patient-level resamples.",
        ],
    }
    (args.output / "paper_metrics.json").write_text(json.dumps(paper_metrics, ensure_ascii=False, indent=2), encoding="utf-8")
    metric_rows = []
    for metric, point in pooled_classification.items():
        if metric in classification_ci:
            ci = classification_ci[metric]
            metric_rows.append({"task": "response", "metric": metric, "estimate": point, "ci95_low": ci["ci95_low"], "ci95_high": ci["ci95_high"]})
    for metric, point in model_ranking.items():
        ci = ranking_ci[f"model_{metric}"]
        metric_rows.append({"task": "donor_ranking", "metric": metric, "estimate": point, "ci95_low": ci["ci95_low"], "ci95_high": ci["ci95_high"]})
    pd.DataFrame(metric_rows).to_csv(args.output / "table_main_metrics.tsv", sep="\t", index=False)
    fold_roc = folds["response_roc_auc"].mean()
    fold_pr = folds["response_pr_auc"].mean()
    report = f"""# FMT triplet model: paper-level evaluation summary

## Validation design

- Dataset: {len(frame)} complete, labeled recipient–donor–post-FMT triplets.
- Validation: five-fold patient-level cross-validation; every response probability shown here is out-of-fold.
- Uncertainty: 2,000 patient-level bootstrap resamples.
- Comparator: fixed CLR-distance baseline. This is not the historical `contrastive_model.pt`.

## Response prediction

| Metric | Pooled OOF estimate | Bootstrap 95% CI |
|---|---:|---:|
| Accuracy | {pooled_classification['accuracy']:.3f} | {classification_ci['accuracy']['ci95_low']:.3f}–{classification_ci['accuracy']['ci95_high']:.3f} |
| Balanced accuracy | {pooled_classification['balanced_accuracy']:.3f} | {classification_ci['balanced_accuracy']['ci95_low']:.3f}–{classification_ci['balanced_accuracy']['ci95_high']:.3f} |
| Sensitivity | {pooled_classification['sensitivity']:.3f} | {classification_ci['sensitivity']['ci95_low']:.3f}–{classification_ci['sensitivity']['ci95_high']:.3f} |
| Specificity | {pooled_classification['specificity']:.3f} | {classification_ci['specificity']['ci95_low']:.3f}–{classification_ci['specificity']['ci95_high']:.3f} |
| F1 | {pooled_classification['f1']:.3f} | {classification_ci['f1']['ci95_low']:.3f}–{classification_ci['f1']['ci95_high']:.3f} |
| MCC | {pooled_classification['mcc']:.3f} | {classification_ci['mcc']['ci95_low']:.3f}–{classification_ci['mcc']['ci95_high']:.3f} |
| ROC-AUC | {pooled_classification['roc_auc']:.3f} | {classification_ci['roc_auc']['ci95_low']:.3f}–{classification_ci['roc_auc']['ci95_high']:.3f} |
| PR-AUC | {pooled_classification['pr_auc']:.3f} | {classification_ci['pr_auc']['ci95_low']:.3f}–{classification_ci['pr_auc']['ci95_high']:.3f} |
| Brier score | {pooled_classification['brier_score']:.3f} | {classification_ci['brier_score']['ci95_low']:.3f}–{classification_ci['brier_score']['ci95_high']:.3f} |

The arithmetic mean of the five fold-level ROC-AUC values is {fold_roc:.3f}, and the mean fold-level PR-AUC is {fold_pr:.3f}. These differ from pooled OOF ROC-AUC and PR-AUC because fold sizes and score distributions differ; pooled OOF values are used for the main ROC and PR figures.

## Donor retrieval

| Metric | Triplet model | Fixed baseline |
|---|---:|---:|
| MRR | {model_ranking['mrr']:.3f} | {baseline_ranking['mrr']:.3f} |
| Mean rank | {model_ranking['mean_rank']:.2f} | {baseline_ranking['mean_rank']:.2f} |
| Recall@1 | {model_ranking['recall_at_1']:.3f} | {baseline_ranking['recall_at_1']:.3f} |
| Recall@3 | {model_ranking['recall_at_3']:.3f} | {baseline_ranking['recall_at_3']:.3f} |
| Recall@5 | {model_ranking['recall_at_5']:.3f} | {baseline_ranking['recall_at_5']:.3f} |
| Recall@10 | {model_ranking['recall_at_10']:.3f} | {baseline_ranking['recall_at_10']:.3f} |

The paired bootstrap MRR improvement is {ranking_ci['mrr_difference']['mean']:.3f} (95% CI {ranking_ci['mrr_difference']['ci95_low']:.3f}–{ranking_ci['mrr_difference']['ci95_high']:.3f}).

## Engraftment analysis

The response-associated engraftment comparison gave Mann–Whitney p={engraftment['p_value']:.4f} and rank-biserial effect size r={engraftment['rank_biserial']:.3f}. This is suggestive but does not pass a two-sided 0.05 threshold.

## Interpretation constraints

This is a small, retrospective, multi-project internal validation. Disease, project, geography, treatment protocol, sequencing batch, and response definition may be confounded. These results support continued algorithm development but are not standalone evidence of clinical utility. External project-level validation and comparison with the historical trained contrastive model remain required.
"""
    (args.output / "PAPER_EVALUATION_REPORT.md").write_text(report, encoding="utf-8")
    print(json.dumps(paper_metrics, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
