# FMT triplet model inference

Model directory:

```text
data/model-training/fmt-triplet-v1
```

The input table must have sample IDs in rows and species in columns. Species may use either `s__Species_name` or full MetaPhlAn taxonomy strings. Values may be percentages, fractions, or counts.

## Generate embeddings

```bash
python scripts/predict_fmt_triplet_model.py \
  --model-dir data/model-training/fmt-triplet-v1 \
  embed \
  --samples new_species.tsv \
  --unit percent \
  --output new_embeddings.tsv
```

## Rank candidate donors

```bash
python scripts/predict_fmt_triplet_model.py \
  --model-dir data/model-training/fmt-triplet-v1 \
  rank \
  --recipient recipient_species.tsv \
  --donors donor_species.tsv \
  --recipient-unit percent \
  --donor-unit percent \
  --output donor_ranking.tsv
```

## Predict response and engraftment

Recipient, donor, and post-FMT tables must have the same row count and corresponding row order.

```bash
python scripts/predict_fmt_triplet_model.py \
  --model-dir data/model-training/fmt-triplet-v1 \
  response \
  --recipient recipient_species.tsv \
  --donor donor_species.tsv \
  --post post_species.tsv \
  --recipient-unit percent \
  --donor-unit percent \
  --post-unit percent \
  --output response_prediction.tsv
```

Every command also creates an `_audit.tsv` file containing feature-name coverage, abundance coverage, missing/extra feature counts, and normalized input totals.
