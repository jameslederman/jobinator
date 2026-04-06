"""Apply pipeline orchestrator.

Generates tailored materials for a job, previews them, and writes to disk
only after user confirmation. Mirrors the score.py pipeline pattern.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import TYPE_CHECKING

import typer
from rich.console import Console
from rich.panel import Panel
from sqlmodel import Session, select

from jobinator.budget.tracker import BudgetExceeded
from jobinator.generation.generator import MaterialsGenerator
from jobinator.generation.models import CoverLetterContent, PrepBriefContent, ResumeContent
from jobinator.generation.renderer import render_pdf
from jobinator.models.job import NormalizedJob, StatusEvent
from jobinator.models.material import GeneratedMaterial
from jobinator.models.score import JobScore
from jobinator.output.manager import OutputManager, make_role_slug

if TYPE_CHECKING:
    from jobinator.budget.tracker import BudgetTracker
    from jobinator.configs.settings import MaterialsConfig

log = logging.getLogger(__name__)
console = Console()


@dataclass
class ApplyResult:
    """Result from an apply run."""

    success: bool = False
    confirmed: bool = False
    budget_stopped: bool = False
    bundle_path: str | None = None
    total_cost_usd: float = 0.0
    errors: list[str] = field(default_factory=list)


def get_job_with_score(
    session: Session, job_id: str
) -> tuple[NormalizedJob | None, JobScore | None]:
    """Load job and its score by job ID.

    Args:
        session: Active SQLModel session.
        job_id: Job ID to look up.

    Returns:
        Tuple of (NormalizedJob, JobScore) — either may be None if not found.
    """
    job = session.get(NormalizedJob, job_id)
    if job is None:
        return None, None
    score = session.exec(select(JobScore).where(JobScore.job_id == job_id)).first()
    return job, score


def run_apply(
    session: Session,
    job: NormalizedJob,
    score: JobScore | None,
    profile_data: dict,
    generator: MaterialsGenerator,
    budget_tracker: "BudgetTracker",
    config: "MaterialsConfig",
    confirm_callback=typer.confirm,  # injectable for testing
) -> ApplyResult:
    """Generate materials, preview, confirm, write files.

    Flow:
    1. Check fit_score >= apply_threshold (if score exists)
    2. Generate resume, cover letter, prep brief (each budget-gated)
    3. Show Rich preview (summary, opening line, question count)
    4. typer.confirm() gate — abort if user declines
    5. Create versioned output dir via OutputManager
    6. Write PDFs, markdown, metadata, job snapshot, scoring JSON
    7. Persist GeneratedMaterial record to DB
    8. Log decision via budget_tracker

    Args:
        session: Active SQLModel session.
        job: NormalizedJob to generate materials for.
        score: Optional JobScore (used for threshold check and scoring.json).
        profile_data: JSON Resume dict (the complete candidate profile).
        generator: MaterialsGenerator instance with configured model.
        budget_tracker: BudgetTracker for budget gating and decision logging.
        config: MaterialsConfig with model, threshold, output_dir.
        confirm_callback: Callable for user confirmation (injectable for tests).

    Returns:
        ApplyResult with success status, bundle_path, and cost info.
    """
    result = ApplyResult()

    # 1. Threshold check — fail fast before any LLM calls
    if score and score.fit_score < config.apply_threshold:
        result.errors.append(
            f"Job fit_score {score.fit_score:.2f} is below apply_threshold "
            f"{config.apply_threshold:.2f}. Use --force to override."
        )
        return result

    # 2. Generate all three materials (each individually budget-gated)
    try:
        resume_content, resume_spend = generator.generate_resume(job, profile_data, score)
        result.total_cost_usd += resume_spend.cost_usd
    except BudgetExceeded:
        result.budget_stopped = True
        return result

    try:
        cover_content, cover_spend = generator.generate_cover_letter(job, profile_data, score)
        result.total_cost_usd += cover_spend.cost_usd
    except BudgetExceeded:
        result.budget_stopped = True
        return result

    try:
        prep_content, prep_spend = generator.generate_prep_brief(job, profile_data, score)
        result.total_cost_usd += prep_spend.cost_usd
    except BudgetExceeded:
        result.budget_stopped = True
        return result

    # 3. Show preview
    console.print()
    console.print(
        Panel(
            resume_content.summary[:300],
            title="[bold]Resume Summary Preview[/bold]",
            expand=False,
        )
    )
    console.print(
        f"  Resume: {len(resume_content.summary.split())} word summary, "
        f"{len(resume_content.relevant_experience)} experience entries, "
        f"{len(resume_content.highlighted_skills)} skills"
    )
    console.print(f"  Cover letter: {cover_content.opening[:100]}...")
    console.print(
        f"  Prep brief: {len(prep_content.likely_questions)} likely questions, "
        f"{len(prep_content.talking_points)} talking points"
    )
    console.print(f"  Total generation cost: ${result.total_cost_usd:.4f}")
    console.print()

    # 4. Confirmation gate — NO files written before this point
    try:
        confirm_callback("Write these files to disk?", abort=True)
    except typer.Abort:
        result.confirmed = False
        budget_tracker.log_decision(
            decision_type="apply_decline",
            decision="user_declined",
            reason="User declined after preview",
            job_id=job.id,
        )
        return result

    result.confirmed = True

    # 5. Create output directory AFTER confirmation
    output_manager = OutputManager(output_dir=config.output_dir)
    role_slug = make_role_slug(job.title)
    app_dir = output_manager.create_application_dir(job.company_slug, role_slug)

    # 6. Build template context
    template_context = {
        "basics": profile_data.get("basics", {}),
        "company": job.company,
        "job_title": job.title,
        "date": datetime.now(timezone.utc).strftime("%B %d, %Y"),
    }

    # Write PDFs
    resume_pdf = render_pdf("resume", resume_content, template_context)
    (app_dir / "resume.pdf").write_bytes(resume_pdf)

    cover_pdf = render_pdf("cover_letter", cover_content, template_context)
    (app_dir / "cover_letter.pdf").write_bytes(cover_pdf)

    prep_pdf = render_pdf("prep_brief", prep_content, template_context)
    (app_dir / "prep_brief.pdf").write_bytes(prep_pdf)

    # Write markdown versions
    (app_dir / "resume.md").write_text(_resume_to_markdown(resume_content))
    (app_dir / "cover_letter.md").write_text(_cover_to_markdown(cover_content))
    (app_dir / "prep_brief.md").write_text(_prep_to_markdown(prep_content))

    # Write job snapshot and metadata
    output_manager.write_job_snapshot(app_dir, job.description)

    scoring_data: dict = {}
    if score:
        scoring_data = {
            "fit_score": score.fit_score,
            "priority_score": score.priority_score,
            "strengths": json.loads(score.strengths_json),
            "gaps": json.loads(score.gaps_json),
            "reasoning": score.reasoning,
        }
    (app_dir / "scoring.json").write_text(json.dumps(scoring_data, indent=2))

    output_manager.write_metadata(
        app_dir,
        {
            "job_id": job.id,
            "company": job.company,
            "title": job.title,
            "model_used": config.strong_model,
            "total_cost_usd": result.total_cost_usd,
            "generated_at": datetime.now(timezone.utc).isoformat(),
        },
    )

    # 7. Persist GeneratedMaterial record
    material = GeneratedMaterial(
        job_id=job.id,
        bundle_path=str(app_dir),
        resume_word_count=len(resume_content.summary.split()),
        cover_letter_word_count=sum(len(p.split()) for p in cover_content.body_paragraphs),
        prep_brief_question_count=len(prep_content.likely_questions),
        model_used=config.strong_model,
        total_cost_usd=result.total_cost_usd,
        confirmed=True,
    )
    session.add(material)

    # Add status event
    event = StatusEvent(
        job_id=job.id,
        status="applied",
        reason=f"Materials generated, cost=${result.total_cost_usd:.4f}",
    )
    session.add(event)
    session.commit()

    # 8. Log decision
    budget_tracker.log_decision(
        decision_type="apply_approve",
        decision="materials_generated",
        reason=f"Generated resume, cover letter, prep brief. Cost: ${result.total_cost_usd:.4f}",
        job_id=job.id,
    )

    result.success = True
    result.bundle_path = str(app_dir)
    return result


def _resume_to_markdown(content: ResumeContent) -> str:
    """Render ResumeContent to a Markdown string."""
    lines = ["# Resume\n", f"## Summary\n{content.summary}\n", "## Experience\n"]
    for entry in content.relevant_experience:
        lines.append(f"### {entry.company} - {entry.position}")
        lines.append(f"*{entry.start_date} - {entry.end_date}*\n")
        for h in entry.highlights:
            lines.append(f"- {h}")
        lines.append("")
    if content.highlighted_skills:
        lines.append("## Skills\n")
        lines.append(", ".join(content.highlighted_skills))
        lines.append("")
    if content.education:
        lines.append("## Education\n")
        for edu in content.education:
            lines.append(
                f"- {edu.get('institution', '')} - {edu.get('studyType', '')} {edu.get('area', '')}"
            )
    return "\n".join(lines)


def _cover_to_markdown(content: CoverLetterContent) -> str:
    """Render CoverLetterContent to a Markdown string."""
    lines = ["# Cover Letter\n", content.opening, ""]
    for p in content.body_paragraphs:
        lines.extend([p, ""])
    lines.append(content.closing)
    return "\n".join(lines)


def _prep_to_markdown(content: PrepBriefContent) -> str:
    """Render PrepBriefContent to a Markdown string."""
    lines = [
        "# Interview Prep Brief\n",
        "## Company Overview\n",
        content.company_overview,
        "",
        "## Role Summary\n",
        content.role_summary,
        "",
        "## Likely Questions\n",
    ]
    for q in content.likely_questions:
        lines.append(f"- {q}")
    lines.append("\n## Talking Points\n")
    for tp in content.talking_points:
        lines.append(f"- {tp}")
    if content.gaps_to_address:
        lines.append("\n## Gaps to Address\n")
        for g in content.gaps_to_address:
            lines.append(f"- {g}")
    return "\n".join(lines)
