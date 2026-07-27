"""Wire schemas. The verdict shape matches what editor-shell/app.js already renders."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

Status = Literal["correct", "incorrect", "uncertain"]


class VerifyRequest(BaseModel):
    step_id: str = Field(..., max_length=200)
    text: str = Field(..., max_length=1000)
    # Prior lines of the same note, oldest first. The last one is the reference
    # the current step has to follow from.
    context: list[str] = Field(default_factory=list)

    @property
    def previous(self) -> str | None:
        for line in reversed(self.context):
            if line.strip():
                return line
        return None


class Verdict(BaseModel):
    step_id: str
    status: Status
    confidence: float
    short: str
    details: str
    fix: str | None = None
    source: str = "sympy"


class WSError(BaseModel):
    type: Literal["error"] = "error"
    message: str
