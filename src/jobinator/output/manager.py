"""OutputManager: directory creation and symlink maintenance for application bundles."""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

# Expected files in a complete application bundle (per D-11)
BUNDLE_FILES = [
    "resume.pdf",
    "cover_letter.pdf",
    "prep_brief.pdf",
    "resume.md",
    "cover_letter.md",
    "prep_brief.md",
    "job_description.md",
    "scoring.json",
    "metadata.json",
]


def make_role_slug(title: str) -> str:
    """Create a filesystem-safe slug from a job title.

    Lowercases, strips special characters, replaces whitespace with hyphens,
    and truncates to 60 characters.
    """
    slug = title.lower().strip()
    slug = re.sub(r"[^a-z0-9\s-]", "", slug)
    slug = re.sub(r"[\s]+", "-", slug)
    return slug[:60]


class OutputManager:
    """Manages the output directory structure for application bundles.

    Directory layout (per D-10):
        {base_dir}/{company_slug}/{role_slug}/{ISO-timestamp}/

    A `latest` symlink is maintained per company+role (per D-12) to allow
    quick access to the most recent application bundle without knowing the timestamp.

    Usage:
        mgr = OutputManager(output_dir="~/jobinator-output")
        app_dir = mgr.create_application_dir("acme", "senior-ml-engineer")
        mgr.write_metadata(app_dir, {"company": "Acme", ...})
    """

    def __init__(self, output_dir: str = "~/jobinator-output") -> None:
        self.base_dir = Path(output_dir).expanduser().resolve()

    def create_application_dir(
        self,
        company_slug: str,
        role_slug: str,
        timestamp: Optional[datetime] = None,
    ) -> Path:
        """Create output directory: {base_dir}/{company_slug}/{role_slug}/{ISO-timestamp}/

        Also creates or updates the `latest` symlink pointing to the new directory.

        Args:
            company_slug: Filesystem-safe company identifier (e.g. "acme-corp")
            role_slug: Filesystem-safe role identifier (e.g. "senior-ml-engineer")
            timestamp: UTC datetime for the directory name. Defaults to now (UTC).

        Returns:
            Path to the created directory.
        """
        if timestamp is None:
            timestamp = datetime.now(timezone.utc)
        ts_str = timestamp.strftime("%Y%m%dT%H%M%SZ")
        app_dir = self.base_dir / company_slug / role_slug / ts_str
        app_dir.mkdir(parents=True, exist_ok=True)

        # Create/update the `latest` symlink (per D-12)
        latest_link = self.base_dir / company_slug / role_slug / "latest"
        if latest_link.is_symlink() or latest_link.exists():
            latest_link.unlink()
        latest_link.symlink_to(app_dir)

        return app_dir

    def get_bundle_manifest(self) -> list[str]:
        """Return the list of expected files in a complete application bundle (per D-11)."""
        return list(BUNDLE_FILES)

    def write_metadata(self, app_dir: Path, metadata: dict) -> Path:
        """Write metadata.json to the application directory.

        Args:
            app_dir: Directory path (returned by create_application_dir).
            metadata: Dict to serialize as JSON. Values are coerced via default=str.

        Returns:
            Path to the written metadata.json file.
        """
        metadata_path = app_dir / "metadata.json"
        with open(metadata_path, "w") as f:
            json.dump(metadata, f, indent=2, default=str)
        return metadata_path

    def write_job_snapshot(self, app_dir: Path, job_description: str) -> Path:
        """Write job_description.md to the application directory.

        Args:
            app_dir: Directory path (returned by create_application_dir).
            job_description: Raw job description text.

        Returns:
            Path to the written job_description.md file.
        """
        snapshot_path = app_dir / "job_description.md"
        with open(snapshot_path, "w") as f:
            f.write(job_description)
        return snapshot_path
