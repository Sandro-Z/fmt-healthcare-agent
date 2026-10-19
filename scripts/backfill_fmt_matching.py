#!/usr/bin/env python3
"""Backfill missing/degraded FMT matching blocks in saved online analyses."""

from __future__ import annotations

import argparse
import json
import os
import tempfile
from pathlib import Path

from wgs_agent.pipeline.report_common import METAPHLAN_GENUS_FILE
from wgs_agent.pipeline.report_fmt_matching import run_fmt_pipeline


def _atomic_write(path: Path, data: dict) -> None:
    fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(data, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
        os.replace(temporary, path)
    except Exception:
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass
        raise


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    from wgs_fmt_platform.paths import runtime_path
    parser.add_argument("--results-dir", default=str(runtime_path("WGS_RESULTS_DIR", "results")))
    parser.add_argument("--sample", action="append", help="Only backfill this sample ID; repeatable")
    parser.add_argument("--top-k", type=int, default=10)
    parser.add_argument("--force", action="store_true", help="Recompute records that already have status=ok")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    results_dir = Path(args.results_dir).resolve()
    selected = set(args.sample or [])
    paths = sorted(results_dir.glob("*_analysis.json"))
    counts = {"updated": 0, "skipped": 0, "unavailable": 0, "errors": 0}
    for path in paths:
        sample_id = path.name[: -len("_analysis.json")]
        if selected and sample_id not in selected:
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            current = data.get("fmt_matching") if isinstance(data.get("fmt_matching"), dict) else {}
            if not args.force and current.get("status") == "ok":
                counts["skipped"] += 1
                print(f"SKIP {sample_id}: already ok")
                continue
            result = run_fmt_pipeline(
                sample_id=sample_id,
                genus_file=METAPHLAN_GENUS_FILE,
                output_dir=str(results_dir / "figures"),
                top_k=args.top_k,
                device_str="cpu",
            )
            status = result.get("status", "unavailable")
            if status != "ok":
                counts["unavailable"] += 1
                print(f"MISS {sample_id}: {result.get('message', status)}")
                continue
            data["fmt_matching"] = result
            if not args.dry_run:
                _atomic_write(path, data)
            counts["updated"] += 1
            print(f"{'WOULD_UPDATE' if args.dry_run else 'UPDATED'} {sample_id}: {len(result.get('top_k_matches', []))} matches")
        except Exception as exc:
            counts["errors"] += 1
            print(f"ERROR {sample_id}: {type(exc).__name__}: {exc}")
    print(json.dumps(counts, ensure_ascii=False))
    return 1 if counts["errors"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
