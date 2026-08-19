"""shorts-lab — hermes plugin entry point."""
from __future__ import annotations

import logging

try:
    from . import analysis
except ImportError:  # imported outside package context (tests, tooling)
    import analysis  # type: ignore

logger = logging.getLogger(__name__)

_SHORTS_SEARCH_SCHEMA = {
    "type": "object",
    "properties": {
        "query": {"type": "string",
                  "description": "Substring to find across competitor shorts"
                                 " titles, transcripts, and channels"},
        "limit": {"type": "integer", "description": "Max results (default 5)"},
    },
    "description": ("Shorts Lab: search monitored competitors' recent "
                    "YouTube Shorts — use to answer questions like 'what "
                    "hooks is <channel> running this month'."),
}


def register(ctx) -> None:
    # Bundled skills → shorts-lab:<name> (the vendored official Remotion
    # skill pack drives the Site Video build/render workers).
    import logging
    from pathlib import Path
    _log = logging.getLogger(__name__)
    skills_dir = Path(__file__).parent / "skills"
    if skills_dir.is_dir():
        for child in sorted(skills_dir.iterdir()):
            skill_md = child / "SKILL.md"
            if child.is_dir() and skill_md.exists():
                try:
                    ctx.register_skill(child.name, skill_md)
                except Exception as exc:  # noqa: BLE001
                    _log.warning("skill %s failed to register: %s",
                                 child.name, exc)

    ctx.register_tool(
        name="shorts_search",
        toolset="shorts_lab",
        schema=_SHORTS_SEARCH_SCHEMA,
        handler=analysis.tool_shorts_search,
    )
