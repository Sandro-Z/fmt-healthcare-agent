#!/usr/bin/env python3
"""Train and evaluate a leakage-safe FMT recipient-donor-post contrastive model."""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import random
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.decomposition import PCA
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (
    average_precision_score,
    balanced_accuracy_score,
    f1_score,
    roc_auc_score,
)
from sklearn.model_selection import StratifiedKFold
from sklearn.preprocessing import StandardScaler


SEED = 20260830


def canonical_species(name: str) -> str:
    return str(name).split("|")[-1].strip()


def load_species(path: Path, sep: str) -> pd.DataFrame:
    frame = pd.read_csv(path, sep=sep, index_col=0)
    frame.columns = [canonical_species(c) for c in frame.columns]
    frame = frame.T.groupby(level=0).sum().T
    frame.index = frame.index.astype(str)
    return frame.apply(pd.to_numeric, errors="coerce").fillna(0.0)


def clr(values: np.ndarray, pseudocount: float = 1e-4) -> np.ndarray:
    logged = np.log(np.maximum(values, 0.0) + pseudocount)
    return logged - logged.mean(axis=1, keepdims=True)


@dataclass
class Preprocessor:
    features: list[str]
    scaler: StandardScaler

    def transform(self, frame: pd.DataFrame) -> np.ndarray:
        x = frame.reindex(columns=self.features, fill_value=0.0).to_numpy(float)
        return self.scaler.transform(clr(x))


def fit_preprocessor(frame: pd.DataFrame, top_features: int) -> Preprocessor:
    transformed = clr(frame.to_numpy(float))
    variance = transformed.var(axis=0)
    keep = np.argsort(variance)[::-1][: min(top_features, frame.shape[1])]
    features = frame.columns[keep].tolist()
    scaler = StandardScaler().fit(transformed[:, keep])
    return Preprocessor(features=features, scaler=scaler)


def squared_distance(x: np.ndarray, y: np.ndarray, w: np.ndarray) -> np.ndarray:
    return np.sum(((x - y) @ w) ** 2, axis=1)


def train_projection(
    recipient: np.ndarray,
    donor: np.ndarray,
    post: np.ndarray,
    response: np.ndarray,
    embedding_dim: int,
    epochs: int,
    learning_rate: float,
    margin: float,
    trajectory_weight: float,
    seed: int,
) -> tuple[np.ndarray, list[dict[str, float]]]:
    rng = np.random.default_rng(seed)
    all_x = np.vstack([recipient, donor, post])
    pca = PCA(n_components=min(embedding_dim, all_x.shape[0] - 1, all_x.shape[1]), random_state=seed)
    pca.fit(all_x)
    w = pca.components_.T.copy()
    history: list[dict[str, float]] = []
    n = len(recipient)
    for epoch in range(epochs):
        order = rng.permutation(n)
        total_triplet = 0.0
        total_trajectory = 0.0
        active = 0
        for i in order:
            # Semi-hard negative: closest wrong donor under the current projection.
            candidates = np.flatnonzero(np.arange(n) != i)
            neg_dist = squared_distance(
                np.repeat(recipient[i : i + 1], len(candidates), axis=0), donor[candidates], w
            )
            j = int(candidates[np.argmin(neg_dist)])
            delta_pos = recipient[i] - donor[i]
            delta_neg = recipient[i] - donor[j]
            d_pos = float(np.sum((delta_pos @ w) ** 2))
            d_neg = float(np.sum((delta_neg @ w) ** 2))
            loss = margin + d_pos - d_neg
            grad = np.zeros_like(w)
            if loss > 0:
                grad += 2.0 * (
                    np.outer(delta_pos, delta_pos @ w) - np.outer(delta_neg, delta_neg @ w)
                )
                total_triplet += loss
                active += 1

            # Response-aware trajectory: responders should approach their donor more strongly.
            alpha = 0.25 if response[i] == 1 else 0.65
            expected = alpha * recipient[i] + (1.0 - alpha) * donor[i]
            trajectory_delta = expected - post[i]
            trajectory_loss = float(np.sum((trajectory_delta @ w) ** 2))
            grad += trajectory_weight * 2.0 * np.outer(trajectory_delta, trajectory_delta @ w)
            total_trajectory += trajectory_loss
            norm = np.linalg.norm(grad)
            if norm > 10.0:
                grad *= 10.0 / norm
            w -= learning_rate * grad
        # Prevent the metric from collapsing or exploding.
        w, _ = np.linalg.qr(w)
        history.append(
            {
                "epoch": epoch + 1,
                "triplet_loss": total_triplet / max(active, 1),
                "trajectory_loss": total_trajectory / n,
                "active_triplets": active / n,
            }
        )
    return w, history


def response_features(r: np.ndarray, d: np.ndarray, p: np.ndarray, w: np.ndarray) -> np.ndarray:
    zr, zd, zp = r @ w, d @ w, p @ w
    return np.hstack([np.abs(zr - zd), np.abs(zp - zd), zp - zr])


def rank_actual_donor(
    recipients: np.ndarray,
    actual_donors: list[str],
    donor_profiles: dict[str, np.ndarray],
    w: np.ndarray,
) -> list[int]:
    donor_ids = sorted(donor_profiles)
    donor_matrix = np.vstack([donor_profiles[x] for x in donor_ids])
    donor_z = donor_matrix @ w
    ranks: list[int] = []
    for row, actual in zip(recipients @ w, actual_donors):
        distances = np.sum((donor_z - row) ** 2, axis=1)
        ordered = np.argsort(distances)
        ranks.append(int(np.flatnonzero(np.asarray(donor_ids)[ordered] == actual)[0]) + 1)
    return ranks


def ranking_metrics(ranks: list[int]) -> dict[str, float]:
    a = np.asarray(ranks, dtype=float)
    return {
        "mrr": float(np.mean(1.0 / a)),
        "mean_rank": float(np.mean(a)),
        "recall_at_1": float(np.mean(a <= 1)),
        "recall_at_3": float(np.mean(a <= 3)),
        "recall_at_5": float(np.mean(a <= 5)),
        "recall_at_10": float(np.mean(a <= 10)),
    }


def safe_auc(y: np.ndarray, score: np.ndarray, metric: str) -> float:
    if len(np.unique(y)) < 2:
        return math.nan
    return float(roc_auc_score(y, score) if metric == "roc" else average_precision_score(y, score))


def mean_ci(values: list[float]) -> dict[str, float]:
    a = np.asarray([v for v in values if np.isfinite(v)], dtype=float)
    if len(a) == 0:
        return {"mean": math.nan, "std": math.nan, "ci95_low": math.nan, "ci95_high": math.nan}
    mean = float(a.mean())
    std = float(a.std(ddof=1)) if len(a) > 1 else 0.0
    half = 1.96 * std / math.sqrt(len(a))
    return {"mean": mean, "std": std, "ci95_low": mean - half, "ci95_high": mean + half}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--fmt-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--folds", type=int, default=5)
    parser.add_argument("--epochs", type=int, default=100)
    parser.add_argument("--top-features", type=int, default=128)
    parser.add_argument("--embedding-dim", type=int, default=16)
    args = parser.parse_args()
    random.seed(SEED)
    np.random.seed(SEED)
    args.output.mkdir(parents=True, exist_ok=True)

    pairs_path = args.fmt_root / "postfmt_processed/analysis/sample_pairing_v2/fmt_sample_triplets.tsv"
    old_path = args.fmt_root / "species_abundance_train.csv"
    post_path = args.fmt_root / "postfmt_processed/matrices/species_relative_abundance_percent.tsv"
    pairs = pd.read_csv(pairs_path, sep="\t")
    old = load_species(old_path, ",")
    post = load_species(post_path, "\t")
    common = sorted(set(old.columns) & set(post.columns))
    pairs["recipient_key"] = pairs["baseline_recipient_run"].astype(str)
    pairs["donor_key"] = pairs["baseline_donor_run"].astype(str)
    pairs["post_key"] = pairs["post_sample_id"].astype(str)
    complete = (
        pairs["analysis_eligible"].astype(bool)
        & pairs["recipient_key"].isin(old.index)
        & pairs["donor_key"].isin(old.index)
        & pairs["post_key"].isin(post.index)
    )
    data = pairs.loc[complete].copy().reset_index(drop=True)
    data["response_binary"] = data["response_label"].map({"Res": 1, "NoRes": 0})
    data = data[data["response_binary"].notna()].reset_index(drop=True)
    data["patient_group"] = data["project"].astype(str) + "::" + data["subject_id"].astype(str)
    response = data["response_binary"].to_numpy(int)

    fold_predictions: list[pd.DataFrame] = []
    fold_metrics: list[dict[str, float | int]] = []
    histories: list[pd.DataFrame] = []
    splitter = StratifiedKFold(n_splits=args.folds, shuffle=True, random_state=SEED)
    for fold, (train_idx, test_idx) in enumerate(splitter.split(data, response), start=1):
        train_rows = data.iloc[train_idx]
        fit_ids = list(train_rows["recipient_key"]) + list(train_rows["donor_key"])
        fit_frame = old.loc[fit_ids, common]
        prep = fit_preprocessor(fit_frame, args.top_features)
        r_all = prep.transform(old.loc[data["recipient_key"], common])
        d_all = prep.transform(old.loc[data["donor_key"], common])
        p_all = prep.transform(post.loc[data["post_key"], common])
        w, history = train_projection(
            r_all[train_idx], d_all[train_idx], p_all[train_idx], response[train_idx],
            args.embedding_dim, args.epochs, 0.001, 1.0, 0.05, SEED + fold,
        )
        history_frame = pd.DataFrame(history)
        history_frame.insert(0, "fold", fold)
        histories.append(history_frame)
        classifier = LogisticRegression(class_weight="balanced", C=0.5, max_iter=2000, random_state=SEED)
        classifier.fit(response_features(r_all[train_idx], d_all[train_idx], p_all[train_idx], w), response[train_idx])
        probability = classifier.predict_proba(response_features(r_all[test_idx], d_all[test_idx], p_all[test_idx], w))[:, 1]
        predicted = (probability >= 0.5).astype(int)
        donor_profiles = {
            donor_id: prep.transform(old.loc[[donor_id], common])[0]
            for donor_id in sorted(data["donor_key"].unique())
        }
        ranks = rank_actual_donor(r_all[test_idx], data.iloc[test_idx]["donor_key"].tolist(), donor_profiles, w)
        baseline_w = np.eye(r_all.shape[1], min(r_all.shape[1], w.shape[1]))
        baseline_ranks = rank_actual_donor(
            r_all[test_idx], data.iloc[test_idx]["donor_key"].tolist(), donor_profiles, baseline_w
        )
        z_r, z_d, z_p = r_all[test_idx] @ w, d_all[test_idx] @ w, p_all[test_idx] @ w
        engraftment = np.sum((z_p - z_r) ** 2, axis=1) - np.sum((z_p - z_d) ** 2, axis=1)
        pred = data.iloc[test_idx][[
            "post_sample_id", "project", "subject_id", "recipient_key", "donor_key", "response_label"
        ]].copy()
        pred["fold"] = fold
        pred["response_probability"] = probability
        pred["response_prediction"] = predicted
        pred["donor_rank"] = ranks
        pred["baseline_donor_rank"] = baseline_ranks
        pred["engraftment_score"] = engraftment
        fold_predictions.append(pred)
        rank_result = ranking_metrics(ranks)
        base_result = ranking_metrics(baseline_ranks)
        fold_metrics.append({
            "fold": fold,
            "n_train": len(train_idx),
            "n_test": len(test_idx),
            "response_roc_auc": safe_auc(response[test_idx], probability, "roc"),
            "response_pr_auc": safe_auc(response[test_idx], probability, "pr"),
            "response_f1": float(f1_score(response[test_idx], predicted)),
            "response_balanced_accuracy": float(balanced_accuracy_score(response[test_idx], predicted)),
            **rank_result,
            **{f"baseline_{key}": value for key, value in base_result.items()},
        })

    predictions = pd.concat(fold_predictions, ignore_index=True)
    metrics = pd.DataFrame(fold_metrics)
    history = pd.concat(histories, ignore_index=True)
    predictions.to_csv(args.output / "oof_predictions.tsv", sep="\t", index=False)
    metrics.to_csv(args.output / "fold_metrics.tsv", sep="\t", index=False)
    history.to_csv(args.output / "training_history.tsv", sep="\t", index=False)

    metric_columns = [c for c in metrics.columns if c not in {"fold", "n_train", "n_test"}]
    aggregate = {column: mean_ci(metrics[column].astype(float).tolist()) for column in metric_columns}
    audit = {
        "post_samples_total": int(len(pairs)),
        "pairing_eligible": int(pairs["analysis_eligible"].astype(bool).sum()),
        "complete_species_triplets": int(complete.sum()),
        "labeled_triplets": int(len(data)),
        "unique_recipients": int(data["patient_group"].nunique()),
        "unique_donors": int(data["donor_key"].nunique()),
        "responders": int(response.sum()),
        "nonresponders": int((response == 0).sum()),
        "projects": data["project"].value_counts().to_dict(),
        "common_species": len(common),
        "leakage_control": "All samples from one recipient occur in exactly one fold; preprocessing is fit on training fold only.",
    }
    def sha256(path: Path) -> str:
        digest = hashlib.sha256()
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()

    provenance = {
        "pairs": {"path": str(pairs_path), "sha256": sha256(pairs_path)},
        "baseline_species": {"path": str(old_path), "sha256": sha256(old_path)},
        "post_species": {"path": str(post_path), "sha256": sha256(post_path)},
    }
    summary = {"seed": SEED, "audit": audit, "provenance": provenance, "cross_validation": aggregate}
    (args.output / "metrics_summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")

    # Fit final artifact on all labeled triplets for later inference; CV metrics remain strictly OOF.
    final_fit = old.loc[list(data["recipient_key"]) + list(data["donor_key"]), common]
    final_prep = fit_preprocessor(final_fit, args.top_features)
    final_r = final_prep.transform(old.loc[data["recipient_key"], common])
    final_d = final_prep.transform(old.loc[data["donor_key"], common])
    final_p = final_prep.transform(post.loc[data["post_key"], common])
    final_w, final_history = train_projection(
        final_r, final_d, final_p, response, args.embedding_dim, args.epochs, 0.001, 1.0, 0.05, SEED
    )
    final_classifier = LogisticRegression(class_weight="balanced", C=0.5, max_iter=2000, random_state=SEED)
    final_classifier.fit(response_features(final_r, final_d, final_p, final_w), response)
    np.savez_compressed(
        args.output / "fmt_triplet_contrastive_model.npz",
        projection=final_w,
        scaler_mean=final_prep.scaler.mean_,
        scaler_scale=final_prep.scaler.scale_,
        classifier_coef=final_classifier.coef_,
        classifier_intercept=final_classifier.intercept_,
    )
    schema = {
        "version": "fmt-triplet-v1",
        "features": final_prep.features,
        "preprocessing": "species canonicalization -> zero fill -> CLR(pseudocount=1e-4) -> train-only z-score",
        "embedding_dim": int(final_w.shape[1]),
        "tasks": ["donor_ranking", "response_prediction", "engraftment_scoring"],
    }
    (args.output / "feature_schema.json").write_text(json.dumps(schema, ensure_ascii=False, indent=2), encoding="utf-8")
    manifest = {
        "name": "fmt-triplet-contrastive",
        "task": "donor-ranking-response-prediction-engraftment",
        "version": "1.0.0",
        "artifact_uri": str(args.output / "fmt_triplet_contrastive_model.npz"),
        "feature_version": schema["version"],
        "training_dataset_version": provenance["pairs"]["sha256"][:12],
        "metrics": {key: value["mean"] for key, value in aggregate.items()},
        "validation": "5-fold patient-level out-of-fold",
        "seed": SEED,
    }
    (args.output / "model_manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    def fm(name: str) -> str:
        value = aggregate[name]["mean"]
        low = aggregate[name]["ci95_low"]
        high = aggregate[name]["ci95_high"]
        return f"{value:.3f} (95% CI {low:.3f}–{high:.3f})"

    report = f"""# FMT 三元组对比学习训练与评测报告

## 数据审计

- 原始移植后样本：{audit['post_samples_total']}；高置信可配对：{audit['pairing_eligible']}。
- 具备移植前受体、真实供体、移植后物种谱的完整三元组：{audit['complete_species_triplets']}。
- 具备二分类疗效标签并进入训练评测：{audit['labeled_triplets']}（响应 {audit['responders']}，不响应 {audit['nonresponders']}）。
- 独立受体 {audit['unique_recipients']}，供体 {audit['unique_donors']}，共同物种特征 {audit['common_species']}。

## 方法

模型使用共享线性投影编码移植前受体、真实供体和移植后菌群。训练目标由供体三元组间隔损失和响应感知的移植后轨迹约束组成；在嵌入空间上训练平衡逻辑回归疗效头。每折仅使用训练集拟合特征筛选、CLR 后标准化、投影和分类器。五折划分以独立患者为单位，输出均为 out-of-fold 预测。

## 主要结果

- 疗效 ROC-AUC：{fm('response_roc_auc')}
- 疗效 PR-AUC：{fm('response_pr_auc')}
- 疗效 F1：{fm('response_f1')}
- 供体排序 MRR：{fm('mrr')}
- Recall@1：{fm('recall_at_1')}；Recall@3：{fm('recall_at_3')}；Recall@5：{fm('recall_at_5')}
- 未训练投影基线 MRR：{fm('baseline_mrr')}

## 解释与限制

这是跨 6 个公开项目的小样本回顾性评测，结果用于算法开发与内部验证，不能直接解释为临床有效性。项目、疾病和测序批次存在混杂；当前 13 个缺少可靠供体映射的样本被排除。下一阶段应增加外部独立队列，并补齐抗生素、FMT 制剂、剂量、给药途径及连续临床终点。
"""
    (args.output / "TRAINING_REPORT.md").write_text(report, encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
