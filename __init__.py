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
    ctx.register_tool(
        name="shorts_search",
        toolset="shorts_lab",
        schema=_SHORTS_SEARCH_SCHEMA,
        handler=analysis.tool_shorts_search,
    )
