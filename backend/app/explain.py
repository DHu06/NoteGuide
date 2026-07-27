"""Turn a SymPy result into wording for the editor.

Per the flowchart, the LLM sits on the *false* branch only: it explains why a
step is wrong, it never decides whether it is wrong. SymPy owns the verdict.

If no Anthropic credentials are configured the deterministic explanation below
is used verbatim — it already carries the counterexample, so the backend is
fully useful with no API key at all.
"""

from __future__ import annotations

import logging
import os

from .models import Verdict
from .verifier import CheckResult

log = logging.getLogger(__name__)

MODEL = "claude-opus-5"

SYSTEM_PROMPT = """You explain a single incorrect step in a student's algebra work.

A computer algebra system has already proved the step is wrong; you are not
being asked to check it, and you must not contradict it. Your job is to say why,
in a way a student can act on.

Rules:
- Two or three sentences, plain text, no LaTeX, no markdown, no preamble.
- Name the specific operation that went wrong (e.g. "6 was subtracted from the
  left side but not the right").
- If a counterexample is supplied, use it — it is the most convincing evidence.
- Do not give away the final answer to the whole problem. Point at the one step.
"""


def _llm_available() -> bool:
    return bool(os.environ.get("ANTHROPIC_API_KEY"))


def deterministic_details(result: CheckResult) -> tuple[str, str, str | None]:
    """(short, details, fix) derived purely from what SymPy proved."""
    if result.parse_error:
        return (
            "Could not read this line",
            result.parse_error,
            "Write the step as math, for example 2*x + 6 = 14.",
        )

    if result.status == "correct":
        if result.previous is None:
            return (
                "Starting line accepted",
                "This is the first line, so there is no earlier step to check it "
                "against. Later steps will be checked against it.",
                None,
            )
        return (
            "Follows from the previous step",
            f"SymPy verified this line is equivalent to the previous one: "
            f"{result.reason}.",
            None,
        )

    if result.status == "incorrect":
        details = f"SymPy proved this line is not equivalent to the previous one: {result.reason}."
        if result.witness:
            details += f" For example, {result.witness}."
        return (
            "Does not follow from the previous step",
            details,
            "Recheck the operation you applied — it changed which values satisfy the line.",
        )

    return (
        "Could not verify this step",
        f"SymPy could not settle this one: {result.reason}.",
        None,
    )


async def _llm_details(result: CheckResult) -> str | None:
    """Ask Claude to explain the proved error. Returns None on any failure."""
    try:
        from anthropic import AsyncAnthropic
    except ImportError:
        return None

    previous = result.previous.raw if result.previous else "(none)"
    current = result.current.raw if result.current else "(none)"
    user_prompt = (
        f"Previous step: {previous}\n"
        f"Student's next step: {current}\n"
        f"What the algebra system proved: {result.reason}\n"
        f"Counterexample: {result.witness or '(none found)'}\n\n"
        "Explain the mistake."
    )

    client = AsyncAnthropic()
    try:
        response = await client.beta.messages.create(
            model=MODEL,
            max_tokens=2000,  # thinking and reply share this budget
            system=SYSTEM_PROMPT,
            output_config={"effort": "low"},
            # Opus 5 can decline a request outright; "default" re-serves it on
            # Anthropic's recommended fallback instead of returning nothing.
            betas=["server-side-fallback-2026-07-01"],
            fallbacks="default",
            messages=[{"role": "user", "content": user_prompt}],
        )
    except Exception:
        log.warning("LLM explanation failed; using deterministic wording", exc_info=True)
        return None
    finally:
        await client.close()

    if response.stop_reason == "refusal":
        return None

    text = "".join(
        block.text for block in response.content if getattr(block, "type", "") == "text"
    ).strip()
    return text or None


async def build_verdict(step_id: str, result: CheckResult) -> Verdict:
    short, details, fix = deterministic_details(result)
    source = "sympy"

    # Only the false branch reaches the LLM, and only to reword — never to judge.
    if result.status == "incorrect" and _llm_available():
        explanation = await _llm_details(result)
        if explanation:
            details = explanation
            source = f"sympy + {MODEL}"

    # SymPy is a decision procedure: a proved verdict is certain, and anything
    # it could not settle is reported as uncertain rather than guessed at.
    confidence = 1.0 if result.status in ("correct", "incorrect") else 0.3

    return Verdict(
        step_id=step_id,
        status=result.status,
        confidence=confidence,
        short=short,
        details=details,
        fix=fix,
        source=source,
    )
