"""Alembic environment configuration for Jobinator database migrations."""

import os
import sys
from logging.config import fileConfig

from sqlalchemy import engine_from_config, pool
from sqlmodel import SQLModel

from alembic import context

# Add src/ to the Python path so jobinator package is importable
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

# Import all models to register them with SQLModel.metadata
# noqa: F401 — these imports are side-effect imports to register table metadata
from jobinator.models import budget, job  # noqa: F401

# This is the Alembic Config object, which provides
# access to the values within the .ini file in use.
config = context.config

# Interpret the config file for Python logging.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Use SQLModel.metadata as the target for autogenerate support
target_metadata = SQLModel.metadata


def get_url() -> str:
    """Resolve database URL from environment variable or settings."""
    # Allow DATABASE_URL env var to override settings (used in tests)
    env_url = os.environ.get("DATABASE_URL")
    if env_url:
        url = env_url
    else:
        from jobinator.configs.settings import get_settings

        url = get_settings().database_url

    # Ensure parent directory exists for file-based SQLite databases
    if url.startswith("sqlite:///") and not url.endswith(":memory:"):
        db_path = url.replace("sqlite:///", "")
        parent = os.path.dirname(db_path)
        if parent:
            os.makedirs(parent, exist_ok=True)

    return url


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode.

    Configures the context with just a URL, not an Engine.
    Useful for generating SQL scripts without a live database.
    """
    url = get_url()
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode with a live database connection."""
    # Override the sqlalchemy.url with our dynamic URL
    configuration = config.get_section(config.config_ini_section, {})
    configuration["sqlalchemy.url"] = get_url()

    connectable = engine_from_config(
        configuration,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
