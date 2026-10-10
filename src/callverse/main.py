"""CallVerse CLI entrypoint."""

import typer

app = typer.Typer(
    name="callverse",
    help="CallVerse: Digital twin of an e-commerce customer-contact center.",
    no_args_is_help=True,
)


@app.command("generate-data")
def generate_data() -> None:
    """Generate synthetic customer contact center dataset."""
    typer.echo("not implemented yet")


@app.command("simulate")
def simulate() -> None:
    """Run discrete-event queue simulation."""
    typer.echo("not implemented yet")


@app.command("compare")
def compare() -> None:
    """Compare baseline and twin simulation scenarios."""
    typer.echo("not implemented yet")


@app.command("train-forecast")
def train_forecast() -> None:
    """Train call arrival and demand forecasting models."""
    typer.echo("not implemented yet")


@app.command("train-rl")
def train_rl() -> None:
    """Train workforce routing and scheduling reinforcement learning policy."""
    typer.echo("not implemented yet")


@app.command("experiments")
def experiments() -> None:
    """Run evaluation and experimentation pipeline."""
    typer.echo("not implemented yet")


if __name__ == "__main__":
    app()
