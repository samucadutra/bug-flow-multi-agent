"""Request and response models of the API."""

from __future__ import annotations

from enum import StrEnum
from typing import Any, Self

from pydantic import BaseModel, ConfigDict, StrictBool, StrictInt, field_validator, model_validator
from pydantic_core import PydanticCustomError

from bugflow.services.bug_detail import BugDetail
from bugflow.services.health import CheckResult
from bugflow.services.schemas import RunRead
from bugflow.services.similarity import SimilarBug
from bugflow.services.stats import DashboardStats

__all__ = [
    "BugDetail",
    "ConfirmBody",
    "EnumEntry",
    "EnumValueOut",
    "EnumsResponse",
    "HealthResponse",
    "InitResponse",
    "ReportFormatQuery",
    "ReportJson",
    "RunIdsResponse",
    "RunListResponse",
    "SimilarResponse",
    "StatsResponse",
    "TriageRunBody",
]

StatsResponse = DashboardStats


class ConfirmBody(BaseModel):
    """Body of the destructive endpoints: `confirm` must be the JSON value `true`."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    confirm: StrictBool

    @field_validator("confirm")
    @classmethod
    def _must_be_true(cls, value: bool) -> bool:
        if value is not True:
            raise PydanticCustomError("confirm_required", "must be true")
        return value


class TriageRunBody(BaseModel):
    """Exactly one of `bug_id` or `all: true`."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    bug_id: StrictInt | None = None
    all: StrictBool | None = None

    @model_validator(mode="after")
    def _exactly_one_target(self) -> Self:
        if (self.bug_id is not None) + (self.all is True) != 1:
            raise PydanticCustomError(
                "target_required", "exactly one of bug_id or all must be given"
            )
        return self

    def params(self) -> dict[str, Any]:
        return {"bug_id": self.bug_id} if self.bug_id is not None else {"all": True}


class RunIdsResponse(BaseModel):
    run_ids: list[int]


class RunListResponse(BaseModel):
    items: list[RunRead]


class SimilarResponse(BaseModel):
    items: list[SimilarBug]


class InitResponse(BaseModel):
    applied_revisions: list[str]
    messages: list[str]


class HealthResponse(BaseModel):
    ok: bool
    database: CheckResult
    vector_search: CheckResult
    llm: CheckResult


class EnumValueOut(BaseModel):
    code: str
    label: str
    definition: str | None


class EnumEntry(BaseModel):
    name: str
    values: list[EnumValueOut]


class EnumsResponse(BaseModel):
    enums: list[EnumEntry]


class ReportJson(BaseModel):
    bug_id: int
    markdown: str
    html: str


class ReportFormatQuery(StrEnum):
    JSON = "json"
    MD = "md"
    HTML = "html"
