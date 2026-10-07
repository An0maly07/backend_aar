"""Custom ``flask`` commands."""
import click
from flask import Flask, current_app

from app.extensions import db


def register_cli(app: Flask) -> None:
    @app.cli.command("train-risk-model")
    @click.option("--samples", default=6000, show_default=True, help="Synthetic samples to generate.")
    @click.option("--seed", default=42, show_default=True, help="Random seed (reproducible training).")
    def train_risk_model(samples: int, seed: int):
        """Train the AI risk model on synthetic sensor data and save it."""
        from app.services.risk.train import train_and_save

        path = current_app.config["RISK_MODEL_PATH"]
        meta = train_and_save(path, n_samples=samples, seed=seed)
        click.echo(f"Saved {meta['version']} to {path}")
        for name, value in meta["metrics"].items():
            click.echo(f"  {name:>12}: {value}")
        click.echo("Restart the server to load the new model.")

    @app.cli.command("escalate-expired")
    def escalate_expired():
        """Escalate unanswered Medium-risk checks once (for cron instead of the sweeper thread)."""
        from app.services.risk.assessment import sweep_expired_assessments

        click.echo(f"Escalated {sweep_expired_assessments()} risk check(s).")

    @app.cli.command("init-db")
    def init_db():
        """Create tables directly (quick start without migrations)."""
        db.create_all()
        click.echo("Database tables created.")
