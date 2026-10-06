"""Pydantic input and output models of the service layer and the payload validation helper."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime
from enum import StrEnum
from typing import Annotated, Any, Self

from pydantic import (
    AfterValidator,
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    ValidationError,
    field_validator,
    model_validator,
)
from pydantic_core import PydanticCustomError

from bugflow.enums import (
    BugStatus,
    Component,
    Environment,
    RunStatus,
    RunType,
    Severity,
    StepStatus,
    Team,
)
from bugflow.services.errors import FieldError, ValidationFailedError

UPDATE_FIELD = "update"


class SortBy(StrEnum):
    OPENED_AT = "opened_at"
    STATUS = "status"
    SEVERITY = "severity"


class SortDir(StrEnum):
    ASC = "asc"
    DESC = "desc"


# Fields whose invalid values are reported as "must be one of: <codes>".
_ENUM_FIELDS: dict[str, type[StrEnum]] = {
    "environment": Environment,
    "reporting_team": Team,
    "status": BugStatus,
    "component": Component,
    "severity": Severity,
    "sort_by": SortBy,
    "sort_dir": SortDir,
}


def _not_blank(value: str) -> str:
    if not value.strip():
        raise PydanticCustomError("blank_text", "must not be empty")
    return value


def _text(max_length: int) -> Any:
    return Annotated[
        str,
        StringConstraints(min_length=1, max_length=max_length),
        AfterValidator(_not_blank),
    ]


Title = _text(120)
Description = _text(5000)
ReproductionSteps = _text(5000)
SystemVersion = _text(50)


def _message_for(error: Mapping[str, Any], field: str) -> str:
    kind = error["type"]
    ctx = error.get("ctx") or {}
    if kind == "missing":
        return "is required"
    if kind == "extra_forbidden":
        return "is not allowed"
    if kind in ("string_too_short", "blank_text"):
        return "must not be empty"
    if kind == "string_too_long":
        return f"must be at most {ctx['max_length']} characters"
    if kind == "less_than_equal":
        return f"must be at most {ctx['le']}"
    if kind == "greater_than_equal":
        return f"must be at least {ctx['ge']}"
    if kind == "empty_update":
        return "at least one field is required"
    if kind in ("enum", "literal_error") and field in _ENUM_FIELDS:
        allowed = ", ".join(member.value for member in _ENUM_FIELDS[field])
        return f"must be one of: {allowed}"
    return "is invalid"


def field_errors_from(exc: ValidationError) -> list[FieldError]:
    """Translate a Pydantic error into per-field messages that never include the input."""
    result: list[FieldError] = []
    for error in exc.errors(include_input=False, include_url=False, include_context=True):
        loc = error["loc"]
        field = str(loc[0]) if loc else UPDATE_FIELD
        result.append(FieldError(field=field, message=_message_for(error, field)))
    return result


class ServiceModel(BaseModel):
    """Base of the input models: unknown fields are rejected and errors are translated."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    def __init__(self, **data: Any) -> None:
        try:
            super().__init__(**data)
        except ValidationError as exc:
            raise ValidationFailedError(field_errors_from(exc)) from None


def validate_payload[ModelT: BaseModel](model: type[ModelT], payload: Mapping[str, Any]) -> ModelT:
    """Build `model` from a plain mapping or raise `ValidationFailedError` with field errors."""
    try:
        return model.model_validate(dict(payload))
    except ValidationError as exc:
        raise ValidationFailedError(field_errors_from(exc)) from None


class BugCreate(ServiceModel):
    title: Title
    description: Description
    reproduction_steps: ReproductionSteps
    system_version: SystemVersion
    environment: Environment
    reporting_team: Team


class BugUpdate(ServiceModel):
    """Optional subset of `BugCreate`; status and dates cannot be edited."""

    title: Title | None = None
    description: Description | None = None
    reproduction_steps: ReproductionSteps | None = None
    system_version: SystemVersion | None = None
    environment: Environment | None = None
    reporting_team: Team | None = None

    @model_validator(mode="after")
    def _require_a_field(self) -> Self:
        if not self.changes():
            raise PydanticCustomError("empty_update", "at least one field is required")
        return self

    def changes(self) -> dict[str, Any]:
        """The provided fields as column values."""
        values = self.model_dump(exclude_none=True)
        return {
            name: value.value if isinstance(value, StrEnum) else value
            for name, value in values.items()
        }


class BugRead(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: int
    title: str
    description: str
    reproduction_steps: str
    system_version: str
    environment: Environment
    reporting_team: Team
    status: BugStatus
    opened_at: datetime
    updated_at: datetime
    component: Component | None = None
    severity: Severity | None = None


class BugListQuery(ServiceModel):
    status: BugStatus | None = None
    component: Component | None = None
    severity: Severity | None = None
    environment: Environment | None = None
    reporting_team: Team | None = None
    search: Annotated[str, StringConstraints(max_length=200)] | None = None
    sort_by: SortBy = SortBy.OPENED_AT
    sort_dir: SortDir = SortDir.DESC
    page: Annotated[int, Field(ge=1)] = 1
    page_size: Annotated[int, Field(ge=1, le=100)] = 20

    @field_validator("search")
    @classmethod
    def _blank_search_means_none(cls, value: str | None) -> str | None:
        if value is None or not value.strip():
            return None
        return value


class BugPage(BaseModel):
    model_config = ConfigDict(frozen=True)

    items: list[BugRead]
    total: int
    page: int
    page_size: int


class RunRead(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: int
    type: RunType
    bug_id: int | None
    status: RunStatus
    progress_done: int
    progress_total: int
    error: str | None
    started_at: datetime
    finished_at: datetime | None


class RunLogRead(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: int
    run_id: int
    logged_at: datetime
    level: str
    message: str


class RunStepRead(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: int
    run_id: int
    position: int
    agent_key: str
    status: StepStatus
    input: Any | None
    output: Any | None
    error: str | None
    started_at: datetime | None
    duration_ms: int | None
