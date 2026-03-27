"""CLI interface for cherry-bomb (placeholder)."""

import typer

app = typer.Typer(name="cherry-bomb", help="SRE AI Agent")


@app.command()
def ask(message: str = typer.Argument(..., help="Message to send to the agent")) -> None:
    """Send a message to the agent."""
    typer.echo(f"TODO: {message}")


def main() -> None:
    """CLI entrypoint."""
    app()
