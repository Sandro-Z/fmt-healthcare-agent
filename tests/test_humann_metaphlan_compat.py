import os
import subprocess

import pytest

from wgs_fmt_platform.paths import PROJECT_ROOT


SHIM = PROJECT_ROOT / "runtime/scripts/postfmt_pipeline/humann_compat/metaphlan"


@pytest.mark.parametrize("database_line", [
    "No complete MetaPhlAn Bowtie2 database found",
    "Installed databases: mpa_vJun23_CHOCOPhlAnSGB_202307",
])
def test_version_probe_returns_only_version_line(tmp_path, database_line):
    real = tmp_path / "metaphlan"
    real.write_text(
        "#!/usr/bin/env bash\n"
        "printf '%s\\n' 'MetaPhlAn version 4.2.4 (21 Oct 2025)' "
        f"'{database_line}'\n"
    )
    real.chmod(0o755)
    result = subprocess.run(
        ["bash", str(SHIM), "--version"], capture_output=True, text=True,
        env={**os.environ, "WGS_HUMANN_METAPHLAN_BIN": str(real)},
    )
    assert result.returncode == 0
    assert result.stdout == "MetaPhlAn version 4.2.4 (21 Oct 2025)\n"
    assert result.stderr == ""


def test_analysis_arguments_are_forwarded_without_changes(tmp_path):
    real = tmp_path / "metaphlan"
    real.write_text('#!/usr/bin/env bash\nprintf "%s\\n" "$@"\n')
    real.chmod(0o755)
    arguments = ["read file.fastq", "--db_dir", "database directory", "-x", "vJun23"]
    result = subprocess.run(
        ["bash", str(SHIM), *arguments], capture_output=True, text=True,
        env={**os.environ, "WGS_HUMANN_METAPHLAN_BIN": str(real)},
    )
    assert result.returncode == 0
    assert result.stdout.splitlines() == arguments


def test_version_probe_preserves_real_failure(tmp_path):
    real = tmp_path / "metaphlan"
    real.write_text('#!/usr/bin/env bash\nprintf "missing dependency\\n" >&2\nexit 7\n')
    real.chmod(0o755)
    result = subprocess.run(
        ["bash", str(SHIM), "--version"], capture_output=True, text=True,
        env={**os.environ, "WGS_HUMANN_METAPHLAN_BIN": str(real)},
    )
    assert result.returncode == 7
    assert "missing dependency" in result.stderr
