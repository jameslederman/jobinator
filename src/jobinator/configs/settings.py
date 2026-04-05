"""Typed configuration settings loaded from TOML + .env files (D-14)."""

from __future__ import annotations

import os
from functools import lru_cache
from typing import Tuple, Type

import platformdirs
from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, PydanticBaseSettingsSource, SettingsConfigDict

# FilterConfig is imported lazily to avoid circular imports at module load time.
# Use get_filter_config() to access the filter configuration.


class Settings(BaseSettings):
    """Application settings loaded from config.toml and .env.

    Load priority (highest to lowest):
      1. Environment variables
      2. .env file (for API keys)
      3. ~/.config/jobinator/config.toml (for user preferences)
      4. Defaults below
    """

    # Database
    database_url: str = f"sqlite:///{platformdirs.user_data_dir('jobinator')}/jobinator.db"

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
        toml_path = os.path.join(platformdirs.user_config_dir("jobinator"), "config.toml")

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


def get_filter_config():
    """Return FilterConfig loaded from config.toml in the user config directory.

    Reads the [filter] section of ~/.config/jobinator/config.toml. Falls back
    to default FilterConfig values if the file is absent or has no [filter] section.

    Returns:
        jobinator.pipelines.filter.FilterConfig instance
    """
    from jobinator.pipelines.filter import load_filter_config

    settings = get_settings()
    return load_filter_config(settings.config_dir)


class DiscoveryConfig(BaseModel):
    """Configuration for job source discovery.

    Loaded from the [discovery] section of config.toml. Falls back to
    safe defaults when no config file is present.

    Follows the same standalone BaseModel pattern as FilterConfig (not a
    nested Settings subclass) to allow test-overridable config without
    requiring config files. See Phase 1 Pitfall 7.

    Example TOML:
        [discovery]
        greenhouse = ["anthropic", "openai"]
        lever = ["figma", "stripe"]
        wellfound_keywords = ["machine learning", "data science"]
        stale_after_days = 14
        hn_months_back = 1
    """

    greenhouse: list[str] = Field(
        default_factory=list,
        description="Greenhouse board tokens to fetch jobs from",
    )
    lever: list[str] = Field(
        default_factory=list,
        description="Lever company slugs to fetch postings from",
    )
    wellfound_keywords: list[str] = Field(
        default_factory=list,
        description="Keywords to search on Wellfound",
    )
    wellfound_companies: list[str] = Field(
        default_factory=list,
        description="Company names to fetch from Wellfound",
    )
    stale_after_days: int = Field(
        default=14,
        description="Days before a job not re-sighted is marked stale",
    )
    hn_months_back: int = Field(
        default=1,
        description="How many months of HN Who's Hiring threads to parse",
    )
    rate_limit_delay_min: float = Field(
        default=2.0,
        description="Minimum delay in seconds between requests (rate limiting)",
    )
    rate_limit_delay_max: float = Field(
        default=5.0,
        description="Maximum delay in seconds between requests (rate limiting)",
    )


def get_discovery_config(config_dir: str | None = None) -> DiscoveryConfig:
    """Return DiscoveryConfig loaded from the [discovery] section of config.toml.

    Falls back to default DiscoveryConfig if the file doesn't exist or
    has no [discovery] section.

    Args:
        config_dir: Path to the directory containing config.toml.
                    Defaults to platformdirs user_config_dir("jobinator").

    Returns:
        DiscoveryConfig instance
    """
    if config_dir is None:
        config_dir = platformdirs.user_config_dir("jobinator")

    toml_path = os.path.join(config_dir, "config.toml")
    if not os.path.exists(toml_path):
        return DiscoveryConfig()

    try:
        import tomllib  # stdlib in Python 3.11+
    except ImportError:
        try:
            import tomli as tomllib  # type: ignore[no-redef]  # fallback for older Python
        except ImportError:
            return DiscoveryConfig()

    with open(toml_path, "rb") as f:
        data = tomllib.load(f)

    discovery_data = data.get("discovery", {})
    return DiscoveryConfig(**discovery_data)
