from __future__ import annotations

import math


def recall_at_k(ranked: list[str], relevant: set[str], k: int) -> float:
    if not relevant:
        return 0.0
    return len(set(ranked[:k]) & relevant) / len(relevant)


def mrr(rankings: list[list[str]], relevant_sets: list[set[str]]) -> float:
    if len(rankings) != len(relevant_sets):
        raise ValueError("rankings and relevant_sets must have the same length")
    reciprocal: list[float] = []
    for ranked, relevant in zip(rankings, relevant_sets, strict=True):
        rank = next((index for index, item in enumerate(ranked, 1) if item in relevant), None)
        reciprocal.append(1 / rank if rank else 0.0)
    return sum(reciprocal) / len(reciprocal) if reciprocal else 0.0


def ndcg_at_k(ranked: list[str], relevant: set[str], k: int) -> float:
    dcg = sum(
        (1.0 / math.log2(index + 2)) if item in relevant else 0.0
        for index, item in enumerate(ranked[:k])
    )
    ideal_hits = min(len(relevant), k)
    idcg = sum(1.0 / math.log2(index + 2) for index in range(ideal_hits))
    return dcg / idcg if idcg else 0.0


def binary_metrics(
    labels: list[int],
    probabilities: list[float],
    threshold: float = 0.5,
    calibration_bins: int = 10,
) -> dict[str, float]:
    if len(labels) != len(probabilities) or not labels:
        raise ValueError("labels and probabilities must have equal non-zero length")
    if any(label not in {0, 1} for label in labels):
        raise ValueError("binary labels must be 0 or 1")
    if any(probability < 0 or probability > 1 for probability in probabilities):
        raise ValueError("probabilities must be between 0 and 1")
    predictions = [int(value >= threshold) for value in probabilities]
    tp = sum(y == 1 and p == 1 for y, p in zip(labels, predictions, strict=True))
    tn = sum(y == 0 and p == 0 for y, p in zip(labels, predictions, strict=True))
    fp = sum(y == 0 and p == 1 for y, p in zip(labels, predictions, strict=True))
    fn = sum(y == 1 and p == 0 for y, p in zip(labels, predictions, strict=True))
    precision = tp / (tp + fp) if tp + fp else 0.0
    recall = tp / (tp + fn) if tp + fn else 0.0
    specificity = tn / (tn + fp) if tn + fp else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    brier = sum((probability - label) ** 2 for label, probability in zip(labels, probabilities, strict=True)) / len(labels)

    ece = 0.0
    for index in range(calibration_bins):
        low = index / calibration_bins
        high = (index + 1) / calibration_bins
        members = [
            i
            for i, probability in enumerate(probabilities)
            if low <= probability < high or (index == calibration_bins - 1 and probability == 1)
        ]
        if members:
            confidence = sum(probabilities[i] for i in members) / len(members)
            accuracy = sum(labels[i] for i in members) / len(members)
            ece += len(members) / len(labels) * abs(confidence - accuracy)
    return {
        "accuracy": (tp + tn) / len(labels),
        "precision": precision,
        "recall": recall,
        "specificity": specificity,
        "f1": f1,
        "brier": brier,
        "ece": ece,
    }

