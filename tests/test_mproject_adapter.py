from pathlib import Path

from wgs_fmt_platform.contracts import SampleManifest
from wgs_fmt_platform.metagenome.adapters import MProjectAdapter


def test_mproject_plan_uses_argv_not_shell(tmp_path: Path) -> None:
    adapter = MProjectAdapter("mProject", tmp_path / "db", tmp_path / "work")
    sample = SampleManifest(
        sample_id="S001",
        read1=Path("S001_1.fastq.gz"),
        read2=Path("S001_2.fastq.gz"),
    )
    args = adapter.plan_run(sample)
    assert args[:3] == ["mProject", "run", "--database"]
    assert args[-4:] == ["-1", "S001_1.fastq.gz", "-2", "S001_2.fastq.gz"]

