"""Interaction agent helpers for prompt construction."""

from html import escape
from pathlib import Path
from typing import Dict, List

from ...services.execution import get_agent_roster
from ...config import get_settings
from ...services.execution.discovery import WorkerDiscoveryError, render_recent

_prompt_path = Path(__file__).parent / "system_prompt.md"
SYSTEM_PROMPT, _, DISCOVERY_PROMPT = _prompt_path.read_text(encoding="utf-8").partition("<!-- bounded-discovery -->")
SYSTEM_PROMPT = SYSTEM_PROMPT.strip()


# Load and return the pre-defined system prompt from markdown file
def build_system_prompt(*, bounded=None) -> str:
    """Return the static system prompt for the interaction agent."""
    bounded = get_settings().worker_discovery_strategy == "bounded" if bounded is None else bounded
    return SYSTEM_PROMPT + ("\n\n" + DISCOVERY_PROMPT.strip() if bounded else "")


# Build structured message with conversation history, active agents, and current turn
def prepare_message_with_history(
    latest_text: str,
    transcript: str,
    message_type: str = "user",
    *, bounded=None,
) -> List[Dict[str, str]]:
    """Compose a message that bundles history, roster, and the latest turn."""
    sections: List[str] = []

    sections.append(_render_conversation_history(transcript))
    sections.append(f"<active_agents>\n{_render_active_agents(bounded=bounded)}\n</active_agents>")
    sections.append(_render_current_turn(latest_text, message_type))

    content = "\n\n".join(sections)
    return [{"role": "user", "content": content}]


# Format conversation transcript into XML tags for LLM context
def _render_conversation_history(transcript: str) -> str:
    history = transcript.strip()
    if not history:
        history = "None"
    return f"<conversation_history>\n{history}\n</conversation_history>"


# Format currently active execution agents into XML tags for LLM awareness
def _render_active_agents(*, bounded=None) -> str:
    roster = get_agent_roster()
    bounded = get_settings().worker_discovery_strategy == "bounded" if bounded is None else bounded
    if bounded:
        try:
            return render_recent(roster)
        except WorkerDiscoveryError:
            return '<worker_catalog status="unavailable">Worker lookup is unavailable. Retry find_worker; do not infer an empty catalog or create another worker.</worker_catalog>'
    roster.load()
    agents = roster.get_agents()

    if not agents:
        return "None"

    rendered: List[str] = []
    for agent_name in agents:
        name = escape(agent_name or "agent", quote=True)
        rendered.append(f'<agent name="{name}" />')

    return "\n".join(rendered)


# Wrap the current message in appropriate XML tags based on sender type
def _render_current_turn(latest_text: str, message_type: str) -> str:
    tag = "new_agent_message" if message_type == "agent" else "new_user_message"
    body = latest_text.strip()
    return f"<{tag}>\n{body}\n</{tag}>"
