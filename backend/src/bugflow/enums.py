"""Canonical enums: codes (stored), English labels (displayed) and definitions."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class BugStatus(StrEnum):
    OPEN = "open"
    PROCESSING = "processing"
    PROCESSED = "processed"
    FAILED = "failed"


class Environment(StrEnum):
    PRODUCTION = "production"
    STAGING = "staging"
    DEVELOPMENT = "development"
    TESTING = "testing"


class Team(StrEnum):
    FRONTEND = "frontend"
    BACKEND = "backend"
    DATA = "data"
    DEVOPS = "devops"
    SECURITY = "security"
    QA = "qa"
    SUPPORT = "support"
    PRODUCT = "product"


class Component(StrEnum):
    FRONTEND = "frontend"
    BACKEND = "backend"
    DATABASE = "database"
    DEVOPS = "devops"
    SECURITY = "security"
    INTEGRATION = "integration"
    UI_UX = "ui_ux"
    INFRASTRUCTURE = "infrastructure"


class Severity(StrEnum):
    CRITICAL = "critical"
    MAJOR = "major"
    MINOR = "minor"


class ResolutionStatus(StrEnum):
    PLANNED = "planned"
    NEEDS_INFO = "needs_info"
    DEFERRED = "deferred"
    WONT_FIX = "wont_fix"


class Priority(StrEnum):
    URGENT = "urgent"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class Seniority(StrEnum):
    JUNIOR = "junior"
    MID = "mid"
    SENIOR = "senior"
    LEAD = "lead"


class RunType(StrEnum):
    TRIAGE = "triage"
    INDEX = "index"
    SEED = "seed"
    INIT = "init"
    RESET = "reset"


class RunStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


class StepStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    SKIPPED = "skipped"


LABELS: dict[type[StrEnum], dict[str, str]] = {
    BugStatus: {
        "open": "Open",
        "processing": "Processing",
        "processed": "Processed",
        "failed": "Failed",
    },
    Environment: {
        "production": "Production",
        "staging": "Staging",
        "development": "Development",
        "testing": "Testing",
    },
    Team: {
        "frontend": "Frontend",
        "backend": "Backend",
        "data": "Data",
        "devops": "DevOps",
        "security": "Security",
        "qa": "QA",
        "support": "Support",
        "product": "Product",
    },
    Component: {
        "frontend": "Frontend",
        "backend": "Backend",
        "database": "Database",
        "devops": "DevOps",
        "security": "Security",
        "integration": "Integration",
        "ui_ux": "UI/UX",
        "infrastructure": "Infrastructure",
    },
    Severity: {"critical": "Critical", "major": "Major", "minor": "Minor"},
    ResolutionStatus: {
        "planned": "Planned",
        "needs_info": "Needs info",
        "deferred": "Deferred",
        "wont_fix": "Won't fix",
    },
    Priority: {"urgent": "Urgent", "high": "High", "medium": "Medium", "low": "Low"},
    Seniority: {"junior": "Junior", "mid": "Mid", "senior": "Senior", "lead": "Lead"},
    RunType: {
        "triage": "Triage",
        "index": "Index",
        "seed": "Seed",
        "init": "Init",
        "reset": "Reset",
    },
    RunStatus: {
        "queued": "Queued",
        "running": "Running",
        "succeeded": "Succeeded",
        "failed": "Failed",
    },
    StepStatus: {
        "pending": "Pending",
        "running": "Running",
        "succeeded": "Succeeded",
        "failed": "Failed",
        "skipped": "Skipped",
    },
}

DEFINITIONS: dict[type[StrEnum], dict[str, str]] = {
    Component: {
        "frontend": "browser-side logic, rendering, state",
        "backend": "server-side business logic and APIs",
        "database": "queries, schema, integrity, data-store performance",
        "devops": "build, release, deployment, configuration",
        "security": "authentication, authorization, data exposure, vulnerabilities",
        "integration": "communication with external systems",
        "ui_ux": "layout, visual design, usability, wording",
        "infrastructure": "servers, networking, containers, capacity",
    },
    Severity: {
        "critical": (
            "data loss, security breach, or complete failure of a core function with no workaround"
        ),
        "major": "a significant function broken or degraded for many users, or costly workaround",
        "minor": "cosmetic or low-impact; core functions work",
    },
}

ENUM_CLASSES: tuple[type[StrEnum], ...] = tuple(LABELS)


@dataclass(frozen=True)
class EnumValue:
    code: str
    label: str
    definition: str | None


@dataclass(frozen=True)
class EnumDescriptor:
    name: str
    values: tuple[EnumValue, ...]


def label_of(member: StrEnum) -> str:
    return LABELS[type(member)][member.value]


def definition_of(member: StrEnum) -> str | None:
    return DEFINITIONS.get(type(member), {}).get(member.value)


def codes(enum_cls: type[StrEnum]) -> list[str]:
    return [member.value for member in enum_cls]


def all_enums() -> list[EnumDescriptor]:
    """Describe every enum (code, label, definition) in the canonical order."""
    return [
        EnumDescriptor(
            name=enum_cls.__name__,
            values=tuple(
                EnumValue(member.value, label_of(member), definition_of(member))
                for member in enum_cls
            ),
        )
        for enum_cls in ENUM_CLASSES
    ]
