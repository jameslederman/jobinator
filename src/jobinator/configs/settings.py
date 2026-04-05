"""Typed configuration settings loaded from TOML + .env files (D-14)."""

from __future__ import annotations

import os
from functools import lru_cache
from typing import Any, Tuple, Type

import platformdirs
from pydantic_settings import BaseSettings, PydanticBaseSettingsSource, SettingsConfigDict
from pydantic_settings.main import BaseSettings


class Settings(BaseSettings):
    """Application settings loaded from config.toml and .env.

    Load priority (highest to lowest):
      1. Environment variables
      2. .env file (for API keys)
      3. ~/.config/jobinator/config.toml (for user preferences)
      4. Defaults below
    """

    # Database
    database_url: str = (
        f"sqlite:///{platformdirs.user_data_dir('jobinator')}/jobinator.db"
    )

    # Config and output directories
    config_dir: str = platformdirs.user_config_dir("jobinator")
    output_dir: str = "~/jobinator-output"

    # LLM provider API keys (loaded from .env)
    anthropic_api_key: str = ""
    openai_api_key: str = ""

    # Budget enforcement
    daily_budget_usd: float = 5.00
    per_job_budget_usd: float = 0.50
    budget_warn_threshold: float = 0.80  # warn at 80% of daily budget

    # Deduplication
    fuzzy_match_threshold: int = 90  # rapidfuzz score threshold (D-04)

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: Type[BaseSettings],
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,
    ) -> Tuple[PydanticBaseSettingsSource, ...]:
        """Configure settings sources to include TOML config file (D-14).

        Source priority (highest to lowest): init > env vars > .env > TOML > defaults.
        """
        toml_path = os.path.join(
            platformdirs.user_config_dir("jobinator"), "config.toml"
        )

        # Only add TOML source if the file exists
        if os.path.exists(toml_path):
            try:
                from pydantic_settings import TomlConfigSettingsSource

                return (
                    init_settings,
                    env_settings,
                    dotenv_settings,
                    TomlConfigSettingsSource(settings_cls, toml_file=toml_path),  # type: ignore[arg-type]
                )
            except ImportError:
                pass

        return (
            init_settings,
            env_settings,
            dotenv_settings,
            file_secret_settings,
        )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return cached Settings instance.

    Use this factory throughout the codebase rather than instantiating
    Settings directly — it ensures a single config object per process.
    """
    return Settings()
