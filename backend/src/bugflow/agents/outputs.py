"""Strict output models of the five triage agents and the agent table.

Models reject unknown fields and never coerce: enum values must match exactly, numbers must be
real integers, and required fields have no defaults. A person's name field in the plan is
rejected because `extra="forbid"` knows no such field.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Annotated

from pydantic import AfterValidator, BaseModel, ConfigDict, Field, StringConstraints

from bugflow.agents.templates import TEMPLATES
from bugflow.enums import Component, Priority, ResolutionStatus, Seniority, Severity, Team


def _not_blank(value: str) -> str:
    if not value.strip():
        raise ValueError("must not be blank")
    return value


def _bounded(max_length: int) -> object:
    return Annotated[
        str, StringConstraints(min_length=1, max_length=max_length), AfterValidator(_not_blank)
    ]


Text400 = _bounded(400)
Text600 = _bounded(600)
Text800 = _bounded(800)
Notes = Annotated[str, StringConstraints(max_length=600)]
Item = Annotated[str, StringConstraints(min_length=1, max_length=400), AfterValidator(_not_blank)]
Skill = Annotated[str, StringConstraints(min_length=1, max_length=60), AfterValidator(_not_blank)]
Role = Annotated[str, StringConstraints(min_length=1, max_length=100), AfterValidator(_not_blank)]


class AgentOutput(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class ComponentOutput(AgentOutput):
    component: Component
    justification: Text600  # type: ignore[valid-type]


class SeverityOutput(AgentOutput):
    severity: Severity
    justification: Text600  # type: ignore[valid-type]
    user_impact: Text400  # type: ignore[valid-type]


class AnalysisOutput(AgentOutput):
    root_cause: Text800  # type: ignore[valid-type]
    technical_impact: Text600  # type: ignore[valid-type]
    debugging_approach: Annotated[list[Item], Field(min_length=1, max_length=6)]
    proposed_solution: Text800  # type: ignore[valid-type]
    side_effects: Annotated[list[Item], Field(max_length=5)]
    referenced_similar_bug_ids: list[int]


class AssigneeProfile(AgentOutput):
    role: Role
    seniority: Seniority
    skills: Annotated[list[Skill], Field(min_length=1, max_length=6)]


class PlanOutput(AgentOutput):
    resolution_status: ResolutionStatus
    assigned_team: Team
    assignee_profile: AssigneeProfile
    target_days: Annotated[int, Field(ge=1, le=90)]
    priority: Priority
    notes: Notes


class DocumentOutput(AgentOutput):
    executive_summary: Text600  # type: ignore[valid-type]
    key_takeaways: Annotated[list[Item], Field(min_length=1, max_length=5)]
    next_steps: Annotated[list[Item], Field(min_length=1, max_length=5)]


@dataclass(frozen=True)
class AgentSpec:
    position: int
    key: str
    label: str
    role: str
    goal: str
    backstory: str
    model: type[AgentOutput]
    template: str


AGENTS: tuple[AgentSpec, ...] = (
    AgentSpec(
        1,
        "component_classifier",
        "AG1 Component Classifier",
        "Component Classifier",
        "Decide which software component a bug belongs to.",
        "You are a senior engineer who knows how web products are split into components.",
        ComponentOutput,
        TEMPLATES["component_classifier"],
    ),
    AgentSpec(
        2,
        "severity_classifier",
        "AG2 Severity Classifier",
        "Severity Classifier",
        "Rate how severe a bug is and how it affects users.",
        "You are a support lead who judges the impact of defects on real users.",
        SeverityOutput,
        TEMPLATES["severity_classifier"],
    ),
    AgentSpec(
        3,
        "technical_analyst",
        "AG3 Technical Analyst",
        "Technical Analyst",
        "Find the likely technical cause of a bug and propose a fix.",
        "You are a staff engineer who debugs production incidents and learns from similar bugs.",
        AnalysisOutput,
        TEMPLATES["technical_analyst"],
    ),
    AgentSpec(
        4,
        "resolution_manager",
        "AG4 Resolution Manager",
        "Resolution Manager",
        "Plan who should fix a bug, how soon and with which priority.",
        "You are an engineering manager who assigns work to teams by profile, never by name.",
        PlanOutput,
        TEMPLATES["resolution_manager"],
    ),
    AgentSpec(
        5,
        "bug_documenter",
        "AG5 Bug Documenter",
        "Bug Documenter",
        "Write a clear executive report of a triaged bug.",
        "You are a technical writer who summarizes engineering findings for managers.",
        DocumentOutput,
        TEMPLATES["bug_documenter"],
    ),
)

AGENT_KEYS = tuple(agent.key for agent in AGENTS)
AGENTS_BY_KEY = {agent.key: agent for agent in AGENTS}
