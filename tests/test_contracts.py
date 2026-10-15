from pathlib import Path

import pytest
from pydantic import ValidationError

from wgs_fmt_platform.contracts import SampleManifest


def test_sample_manifest_accepts_safe_id() -> None:
    sample = SampleManifest(sample_id="SRR13068821", read1=Path("a.fastq.gz"))
    assert sample.sample_id == "SRR13068821"


def test_sample_manifest_rejects_shell_like_id() -> None:
    with pytest.raises(ValidationError):
        SampleManifest(sample_id="x; rm -rf /", read1=Path("a.fastq.gz"))

