"""Jinja2 HTML rendering + WeasyPrint PDF conversion.

Provides two public functions:
  - render_html(): Jinja2 template -> HTML string
  - render_pdf(): HTML string -> PDF bytes via WeasyPrint

Template variables are merged from the Pydantic content model (via model_dump())
and the caller-supplied context dict (basics, company, job_title, date, etc.).

Template directory: src/jobinator/templates/
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader

logger = logging.getLogger(__name__)

# Template directory: src/jobinator/templates/
_TEMPLATES_DIR = Path(__file__).parent.parent / "templates"


def _get_env() -> Environment:
    """Create a Jinja2 Environment with FileSystemLoader pointing at templates/."""
    return Environment(
        loader=FileSystemLoader(str(_TEMPLATES_DIR)),
        autoescape=False,
    )


def render_html(template_name: str, content: Any, context: dict) -> str:
    """Render a Jinja2 template to an HTML string.

    Args:
        template_name: One of "resume", "cover_letter", "prep_brief"
        content: Pydantic model instance (ResumeContent, CoverLetterContent, PrepBriefContent)
        context: Additional template variables (basics, company, job_title, date, etc.)

    Returns:
        Rendered HTML string.

    Raises:
        TemplateNotFound: If the template file does not exist.
    """
    env = _get_env()
    template = env.get_template(f"{template_name}.html.jinja")
    # Merge: content model fields take precedence, context provides shared vars
    template_vars = {**context, **content.model_dump()}
    return template.render(**template_vars)


def render_pdf(template_name: str, content: Any, context: dict) -> bytes:
    """Render content to PDF bytes via Jinja2 HTML and WeasyPrint.

    Renders the template to HTML first, then converts to PDF using WeasyPrint.
    WeasyPrint is lazily imported to avoid hard failure on systems where it
    may not be fully installed (e.g., missing Pango/Cairo system libraries).

    Args:
        template_name: One of "resume", "cover_letter", "prep_brief"
        content: Pydantic model instance
        context: Additional template variables

    Returns:
        PDF file bytes (starts with b"%PDF").

    Raises:
        ImportError: If WeasyPrint is not installed.
        weasyprint.html.HTMLParseError: If HTML is malformed (unlikely with Jinja2 templates).
    """
    from weasyprint import HTML  # lazy import — system dep may be missing

    html_content = render_html(template_name, content, context)
    return HTML(string=html_content).write_pdf()
