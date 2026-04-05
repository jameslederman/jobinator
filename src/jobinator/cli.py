from typing import Optional

import typer
from rich.console import Console

app = typer.Typer(
    name="jobinator",
    help="Local-first, agent-driven job search and application optimization system.",
    add_completion=True,
)
console = Console()


@app.callback()
def main() -> None:
    """Jobinator: discover high-fit jobs and generate tailored application materials."""


@app.command()
def discover(
    source: Optional[str] = typer.Option(
        None,
        "--source",
        help="Run a single source adapter (greenhouse, lever, hn_hiring, wellfound)",
    ),
    dry_run: bool = typer.Option(
        False,
        "--dry-run",
        help="Fetch and normalize but do not persist to database",
    ),
) -> None:
    """Discover new jobs from all configured sources."""
    from rich.table import Table

    from jobinator.configs.settings import get_discovery_config, get_settings
    from jobinator.db import get_engine, get_session, init_db
    from jobinator.pipelines.discover import fire_health_alerts, load_source_health, run_discovery

    settings = get_settings()
    config = get_discovery_config()

    # Validate --source flag if provided
    valid_sources = {"greenhouse", "lever", "hn_hiring", "wellfound"}
    if source and source not in valid_sources:
        console.print(
            f"[red]Unknown source '{source}'. Valid: {', '.join(sorted(valid_sources))}[/red]"
        )
        raise typer.Exit(code=1)

    engine = get_engine(settings.database_url)
    init_db(engine)

    with get_session(engine) as session:
        result = run_discovery(session, config, settings.config_dir, source_filter=source)

    # Print Rich summary table
    table = Table(title="Discovery Results")
    table.add_column("Source", style="cyan")
    table.add_column("New", style="green", justify="right")
    table.add_column("Duplicates", style="yellow", justify="right")
    table.add_column("Status", style="white")

    for src_result in result.sources:
        status = (
            f"[red]ERROR: {src_result.error}[/red]" if src_result.error else "[green]OK[/green]"
        )
        table.add_row(
            src_result.source_id,
            str(src_result.new_jobs),
            str(src_result.duplicate_jobs),
            status,
        )

    console.print(table)
    console.print(
        f"\nTotal new: {result.total_new} | "
        f"Total duplicates: {result.total_duplicates} | "
        f"Stale marked: {result.stale_marked}"
    )

    # Fire health alerts after summary
    health = load_source_health(settings.config_dir)
    fire_health_alerts(health, console)


if __name__ == "__main__":
    app()
