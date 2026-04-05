"""Tests for OutputManager: directory structure, symlinks, bundle manifest, metadata writing."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from jobinator.output import BUNDLE_FILES, OutputManager, make_role_slug


def test_create_output_dir(tmp_path: Path) -> None:
    """Creates {tmp}/acme/senior-ml-engineer/{timestamp}/ directory."""
    mgr = OutputManager(output_dir=str(tmp_path))
    ts = datetime(2026, 4, 5, 12, 0, 0, tzinfo=timezone.utc)
    result = mgr.create_application_dir("acme", "senior-ml-engineer", timestamp=ts)

    assert result.exists()
    assert result.is_dir()
    assert result.name == "20260405T120000Z"
    assert result.parent.name == "senior-ml-engineer"
    assert result.parent.parent.name == "acme"


def test_output_dir_structure(tmp_path: Path) -> None:
    """Returned path matches {output_dir}/{company_slug}/{role_slug}/{ISO-timestamp}/."""
    mgr = OutputManager(output_dir=str(tmp_path))
    ts = datetime(2026, 1, 15, 8, 30, 45, tzinfo=timezone.utc)
    result = mgr.create_application_dir("startup-co", "ml-engineer", timestamp=ts)

    assert result == tmp_path / "startup-co" / "ml-engineer" / "20260115T083045Z"


def test_latest_symlink_created(tmp_path: Path) -> None:
    """After create, {tmp}/acme/senior-ml-engineer/latest is a symlink (D-12)."""
    mgr = OutputManager(output_dir=str(tmp_path))
    ts = datetime(2026, 4, 5, 12, 0, 0, tzinfo=timezone.utc)
    app_dir = mgr.create_application_dir("acme", "senior-ml-engineer", timestamp=ts)

    latest_link = tmp_path / "acme" / "senior-ml-engineer" / "latest"
    assert latest_link.is_symlink()
    assert latest_link.resolve() == app_dir.resolve()


def test_latest_symlink_updated(tmp_path: Path) -> None:
    """Call create twice -> latest points to the second (newer) dir."""
    mgr = OutputManager(output_dir=str(tmp_path))
    ts1 = datetime(2026, 4, 5, 10, 0, 0, tzinfo=timezone.utc)
    ts2 = datetime(2026, 4, 5, 11, 0, 0, tzinfo=timezone.utc)

    mgr.create_application_dir("acme", "ml-engineer", timestamp=ts1)
    app_dir2 = mgr.create_application_dir("acme", "ml-engineer", timestamp=ts2)

    latest_link = tmp_path / "acme" / "ml-engineer" / "latest"
    assert latest_link.resolve() == app_dir2.resolve()


def test_output_dir_expands_tilde(monkeypatch, tmp_path: Path) -> None:
    """output_dir='~/jobinator-output' resolves to absolute path under home."""
    monkeypatch.setenv("HOME", str(tmp_path))
    mgr = OutputManager(output_dir="~/jobinator-output")
    assert not str(mgr.base_dir).startswith("~")
    assert mgr.base_dir.is_absolute()


def test_list_expected_files(tmp_path: Path) -> None:
    """get_bundle_manifest() returns 9 expected files (D-11)."""
    mgr = OutputManager(output_dir=str(tmp_path))
    manifest = mgr.get_bundle_manifest()

    expected = [
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
    assert sorted(manifest) == sorted(expected)
    assert len(manifest) == 9


def test_write_metadata(tmp_path: Path) -> None:
    """write_metadata(path, metadata_dict) creates metadata.json with correct content."""
    mgr = OutputManager(output_dir=str(tmp_path))
    ts = datetime(2026, 4, 5, 12, 0, 0, tzinfo=timezone.utc)
    app_dir = mgr.create_application_dir("acme", "ml-engineer", timestamp=ts)

    metadata = {"company": "Acme", "role": "ML Engineer", "score": 0.92}
    meta_path = mgr.write_metadata(app_dir, metadata)

    assert meta_path.exists()
    with open(meta_path) as f:
        loaded = json.load(f)
    assert loaded["company"] == "Acme"
    assert loaded["role"] == "ML Engineer"
    assert abs(loaded["score"] - 0.92) < 1e-9
