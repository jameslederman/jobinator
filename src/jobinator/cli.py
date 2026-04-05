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


if __name__ == "__main__":
    app()
