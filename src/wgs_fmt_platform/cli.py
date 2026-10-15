import json
from pathlib import Path

import typer

from wgs_fmt_platform.config import get_settings
from wgs_fmt_platform.contracts import SampleManifest
from wgs_fmt_platform.metagenome.adapters import MProjectAdapter

app = typer.Typer(no_args_is_help=True)


@app.callback()
def main() -> None:
    """WGS-FMT platform administration commands."""


@app.command("mproject-plan")
def mproject_plan(
    sample: str = typer.Option(...),
    read1: Path = typer.Option(...),
    read2: Path | None = typer.Option(None),
) -> None:
    """Print argv without running mProject."""
    settings = get_settings()
    adapter = MProjectAdapter(
        settings.mproject_bin,
        settings.mproject_database,
        settings.workspace,
    )
    manifest = SampleManifest(sample_id=sample, read1=read1, read2=read2)
    typer.echo(json.dumps(adapter.plan_run(manifest), ensure_ascii=False, indent=2))
