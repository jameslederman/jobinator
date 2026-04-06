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


@app.command()
def score(
    limit: int = typer.Option(10, "--limit", "-n", help="Max jobs to score this run"),
    dry_run: bool = typer.Option(False, "--dry-run", help="Show unscored jobs without calling LLM"),
) -> None:
    """Score discovered jobs for fit using LLM."""
    from rich.table import Table

    from jobinator.budget.tracker import BudgetConfig, BudgetTracker
    from jobinator.configs.settings import get_scoring_config, get_settings
    from jobinator.db import get_engine, get_session, init_db
    from jobinator.pipelines.score import get_unscored_jobs, load_profile, run_scoring
    from jobinator.scoring.client import LLMClient
    from jobinator.scoring.scorer import JobScorer

    settings = get_settings()
    scoring_config = get_scoring_config(settings.config_dir)

    # Override batch size from CLI flag
    scoring_config = scoring_config.model_copy(update={"score_batch_size": limit})

    # Validate API key presence before any DB/LLM work (fail fast)
    has_anthropic = bool(settings.anthropic_api_key)
    has_openai = bool(settings.openai_api_key)
    if not has_anthropic and not has_openai:
        console.print(
            "[red]No API key configured.[/red] "
            "Set ANTHROPIC_API_KEY or OPENAI_API_KEY in .env file."
        )
        raise typer.Exit(code=1)

    engine = get_engine(settings.database_url)
    init_db(engine)

    with get_session(engine) as session:
        # Dry run: just show unscored jobs without calling LLM
        if dry_run:
            jobs = get_unscored_jobs(session, limit)
            if not jobs:
                console.print("[yellow]No unscored jobs found.[/yellow]")
                raise typer.Exit(code=0)
            table = Table(title=f"Unscored Jobs ({len(jobs)})")
            table.add_column("ID", style="dim", max_width=8)
            table.add_column("Title", style="cyan")
            table.add_column("Company", style="green")
            table.add_column("Source", style="yellow")
            for job in jobs:
                table.add_row(job.id[:8], job.title, job.company, job.source)
            console.print(table)
            raise typer.Exit(code=0)

        # Validate profile before starting scoring loop
        profile_data = load_profile(scoring_config.profile_path)
        if profile_data is None:
            path_display = scoring_config.profile_path or "not configured"
            console.print(
                f"[red]Profile not found:[/red] {path_display}\n"
                "Create a JSON Resume file and set [scoring] profile_path in "
                f"{settings.config_dir}/config.toml"
            )
            raise typer.Exit(code=1)

        budget_config = BudgetConfig(
            daily_limit_usd=settings.daily_budget_usd,
            per_job_limit_usd=settings.per_job_budget_usd,
            warn_threshold=settings.budget_warn_threshold,
        )
        budget_tracker = BudgetTracker(config=budget_config, session=session)
        llm_client = LLMClient(model=scoring_config.cheap_model)
        scorer = JobScorer(
            llm_client=llm_client,
            budget_tracker=budget_tracker,
            config=scoring_config,
        )

        result = run_scoring(session, budget_tracker, scorer, scoring_config)

    # Print results
    if result.errors:
        for error in result.errors:
            console.print(f"[red]{error}[/red]")

    if result.budget_stopped:
        console.print(
            f"\n[red]Budget limit reached.[/red] Daily spend: ${budget_tracker.daily_spend():.4f}"
        )

    console.print(
        f"\n[bold]Scored:[/bold] {result.scored} jobs"
        f" | [bold]Skipped:[/bold] {result.skipped}"
        f" | [bold]Errors:[/bold] {len(result.errors)}"
    )

    if result.budget_stopped:
        raise typer.Exit(code=1)


@app.command()
def apply(
    job_id: str = typer.Argument(..., help="Job ID to generate materials for"),
    force: bool = typer.Option(False, "--force", help="Override fit score threshold check"),
) -> None:
    """Generate tailored resume, cover letter, and prep brief for a job."""
    from jobinator.budget.tracker import BudgetConfig, BudgetTracker
    from jobinator.configs.settings import get_materials_config, get_scoring_config, get_settings
    from jobinator.db import get_engine, get_session, init_db
    from jobinator.generation.generator import MaterialsGenerator
    from jobinator.pipelines.apply import get_job_with_score, run_apply
    from jobinator.pipelines.score import load_profile

    settings = get_settings()
    materials_config = get_materials_config(settings.config_dir)

    # Use scoring config profile_path as fallback if materials doesn't have one
    if not materials_config.profile_path:
        scoring_config = get_scoring_config(settings.config_dir)
        if scoring_config.profile_path:
            materials_config = materials_config.model_copy(
                update={"profile_path": scoring_config.profile_path}
            )

    # Validate API key presence before any DB/LLM work (fail fast)
    has_anthropic = bool(settings.anthropic_api_key)
    has_openai = bool(settings.openai_api_key)
    if not has_anthropic and not has_openai:
        console.print(
            "[red]No API key configured.[/red] "
            "Set ANTHROPIC_API_KEY or OPENAI_API_KEY in .env file."
        )
        raise typer.Exit(code=1)

    engine = get_engine(settings.database_url)
    init_db(engine)

    with get_session(engine) as session:
        # Load job and score
        job, score = get_job_with_score(session, job_id)
        if job is None:
            console.print(f"[red]Job not found:[/red] {job_id}")
            raise typer.Exit(code=1)

        if score is None:
            console.print(f"[yellow]Warning:[/yellow] Job {job_id} has not been scored yet.")

        # Override threshold if --force
        if force:
            materials_config = materials_config.model_copy(update={"apply_threshold": 0.0})

        # Load profile
        profile_data = load_profile(materials_config.profile_path)
        if profile_data is None:
            path_display = materials_config.profile_path or "not configured"
            console.print(
                f"[red]Profile not found:[/red] {path_display}\n"
                "Create a JSON Resume file and set [materials] profile_path in "
                f"{settings.config_dir}/config.toml"
            )
            raise typer.Exit(code=1)

        budget_config = BudgetConfig(
            daily_limit_usd=settings.daily_budget_usd,
            per_job_limit_usd=settings.per_job_budget_usd,
            warn_threshold=settings.budget_warn_threshold,
        )
        budget_tracker = BudgetTracker(config=budget_config, session=session)
        generator = MaterialsGenerator(budget_tracker=budget_tracker, config=materials_config)

        console.print(f"\n[bold]Generating materials for:[/bold] {job.title} at {job.company}")
        if score:
            console.print(
                f"  Fit score: {score.fit_score:.2f} | Priority: {score.priority_score:.2f}"
            )
        console.print(f"  Model: {materials_config.strong_model}")
        console.print()

        result = run_apply(
            session=session,
            job=job,
            score=score,
            profile_data=profile_data,
            generator=generator,
            budget_tracker=budget_tracker,
            config=materials_config,
        )

    # Print results
    if result.errors:
        for error in result.errors:
            console.print(f"[red]{error}[/red]")
        raise typer.Exit(code=1)

    if result.budget_stopped:
        console.print(
            f"\n[red]Budget limit reached.[/red] Daily spend: ${budget_tracker.daily_spend():.4f}"
        )
        raise typer.Exit(code=1)

    if not result.confirmed:
        console.print("[yellow]Apply cancelled by user.[/yellow]")
        raise typer.Exit(code=0)

    if result.success:
        console.print(f"\n[green]Materials written to:[/green] {result.bundle_path}")
        console.print(f"  Total cost: ${result.total_cost_usd:.4f}")


if __name__ == "__main__":
    app()
