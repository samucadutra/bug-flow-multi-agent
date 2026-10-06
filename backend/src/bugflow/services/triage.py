"""Triage services: claim, pipeline execution, atomic result write, batch triage and hooks.

Five agents run strictly in sequence on one bug. Each step is recorded while it runs. Only after
the fifth step succeeded does one transaction insert the five result rows, run the registered
result hooks and move the bug from `processing` to `processed`. Any failure marks the bug
`failed` and leaves no result row. Agent and provider failures are returned as outcomes, never
raised.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel, ConfigDict, ValidationError
from sqlalchemy import Engine, select, update
from sqlalchemy import func as sql_func
from sqlalchemy.exc import DBAPIError, InterfaceError, OperationalError
from sqlalchemy.orm import Session, sessionmaker

from bugflow.agents.errors import AgentCallError
from bugflow.agents.outputs import (
    AGENT_KEYS,
    AGENTS,
    AgentSpec,
    AnalysisOutput,
    ComponentOutput,
    DocumentOutput,
    PlanOutput,
    SeverityOutput,
)
from bugflow.agents.runtime import run_agent
from bugflow.agents.templates import render_prompt
from bugflow.config import ConfigError
from bugflow.db.engine import session_factory
from bugflow.db.errors import DatabaseUnavailableError
from bugflow.db.models import (
    Bug,
    BugReport,
    ComponentClassification,
    ResolutionPlan,
    SeverityClassification,
    TechnicalAnalysis,
)
from bugflow.enums import BugStatus, RunStatus, RunType, StepStatus
from bugflow.logging_config import Redactor
from bugflow.services.bugs import get_bug
from bugflow.services.embeddings import ensure_embedding
from bugflow.services.errors import NotFoundError, ServiceError, StateConflictError
from bugflow.services.llm_client import LlmError
from bugflow.services.runs import RunRecorder
from bugflow.services.schemas import BugRead
from bugflow.services.similarity import DEFAULT_SEARCH_LIMIT, similar_to_bug

logger = logging.getLogger(__name__)

STEP_COUNT = len(AGENTS)
RAW_RESPONSE_LIMIT = 4_000
VALUE_LIMIT = 40
UNEXPECTED_AGENT_ERROR = "unexpected agent error"

Runner = Callable[[AgentSpec, str, Any], str]
StepCallback = Callable[["StepSummary"], None]
OutcomeCallback = Callable[["TriageOutcome"], None]


class StepSummary(BaseModel):
    """What a step produced, for live display and the outcome."""

    model_config = ConfigDict(frozen=True)

    position: int
    key: str
    label: str
    status: StepStatus
    summary: str

    @property
    def succeeded(self) -> bool:
        return self.status == StepStatus.SUCCEEDED


class TriageOutcome(BaseModel):
    model_config = ConfigDict(frozen=True)

    bug_id: int
    run_id: int
    status: BugStatus
    error: str | None
    steps: list[StepSummary]

    @property
    def processed(self) -> bool:
        return self.status == BugStatus.PROCESSED


@dataclass(frozen=True)
class TriageResults:
    """The five validated agent outputs, given to result hooks."""

    bug_id: int
    run_id: int
    component: ComponentOutput
    severity: SeverityOutput
    analysis: AnalysisOutput
    plan: PlanOutput
    document: DocumentOutput


ResultHook = Callable[[Session, int, TriageResults], None]
_RESULT_HOOKS: list[ResultHook] = []


def register_result_hook(hook: ResultHook) -> None:
    """Register a hook that runs inside the final transaction, in registration order."""
    _RESULT_HOOKS.append(hook)


def unregister_result_hook(hook: ResultHook) -> None:
    if hook in _RESULT_HOOKS:
        _RESULT_HOOKS.remove(hook)


def clear_result_hooks() -> None:
    _RESULT_HOOKS.clear()


class AgentFailure(Exception):
    """A step failure with the text stored on the step, the run and the bug."""

    def __init__(self, text: str, raw: str | None = None) -> None:
        super().__init__(text)
        self.text = text
        self.raw = raw


# --- validation and failure text ---------------------------------------------------------------


def _field_name(location: tuple[Any, ...]) -> str:
    return ".".join(part for part in location if isinstance(part, str))


def failure_text(agent: AgentSpec, exc: ValidationError) -> str:
    """The fixed failure text for the first validation error of an agent reply."""
    prefix = f"AG{agent.position} returned"
    error = exc.errors(include_url=False)[0]
    location = tuple(error["loc"])
    kind = error["type"]
    if kind == "json_invalid" or not location:
        return f"{prefix} malformed JSON"
    name = _field_name(location)
    if kind == "extra_forbidden":
        return f"{prefix} unexpected field '{name}'"
    if kind == "enum":
        return f"{prefix} invalid {name} '{str(error['input'])[:VALUE_LIMIT]}'"
    return f"{prefix} invalid {name}"


def validate_reply(agent: AgentSpec, raw: str, similar_ids: set[int]) -> BaseModel:
    """Parse a raw reply into the agent's output model, or raise `AgentFailure`."""
    try:
        output = agent.model.model_validate_json(raw)
    except ValidationError as exc:
        raise AgentFailure(failure_text(agent, exc), raw) from None
    if isinstance(output, AnalysisOutput) and not set(output.referenced_similar_bug_ids) <= (
        similar_ids
    ):
        raise AgentFailure(f"AG{agent.position} returned invalid referenced_similar_bug_ids", raw)
    return output


def reask_prompt(prompt: str, error_text: str) -> str:
    """The prompt plus a correction block with the validation error (never the old reply)."""
    return (
        f"{prompt}\n\nYour previous answer was rejected: {error_text}.\n"
        "Answer again with one corrected JSON object that follows the schema exactly."
    )


def ask_agent(
    runner: Runner,
    agent: AgentSpec,
    prompt: str,
    client: Any,
    similar_ids: set[int],
    on_reask: Callable[[str], None] | None = None,
) -> BaseModel:
    """Run an agent and validate the reply; an invalid reply is re-asked exactly once.

    Provider failures raise `AgentFailure` at once (no re-ask). A second invalid reply raises
    the `AgentFailure` of that reply.
    """
    raw = _call_agent(runner, agent, prompt, client)
    try:
        return validate_reply(agent, raw, similar_ids)
    except AgentFailure as first:
        if on_reask is not None:
            on_reask(first.text)
        raw = _call_agent(runner, agent, reask_prompt(prompt, first.text), client)
        return validate_reply(agent, raw, similar_ids)


def step_summary_text(output: BaseModel) -> str:
    """The one-line description of a validated output used for live display."""
    if isinstance(output, ComponentOutput):
        return output.component.value
    if isinstance(output, SeverityOutput):
        return output.severity.value
    if isinstance(output, AnalysisOutput):
        return (
            f"{len(output.debugging_approach)} debugging steps, "
            f"{len(output.referenced_similar_bug_ids)} similar bugs referenced"
        )
    if isinstance(output, PlanOutput):
        return (
            f"{output.assigned_team.value} / {output.priority.value} / "
            f"{output.resolution_status.value}"
        )
    if isinstance(output, DocumentOutput):
        return f"{len(output.key_takeaways)} key takeaways, {len(output.next_steps)} next steps"
    raise TypeError("Unknown agent output")  # pragma: no cover


# --- claim -------------------------------------------------------------------------------------


def claim_bug(engine: Engine, bug_id: int) -> BugRead:
    """Move an `open` or `failed` bug to `processing` atomically (own transaction)."""
    unreachable = False
    try:
        with session_factory(engine)() as session:
            claimed = session.execute(
                update(Bug)
                .where(
                    Bug.id == bug_id,
                    Bug.status.in_((BugStatus.OPEN.value, BugStatus.FAILED.value)),
                )
                .values(status=BugStatus.PROCESSING.value, updated_at=sql_func.clock_timestamp())
                .returning(Bug.id)
            ).first()
            if claimed is not None:
                session.commit()
                return get_bug(session, bug_id)
            current = session.scalar(select(Bug.status).where(Bug.id == bug_id))
    except (OperationalError, InterfaceError):
        unreachable = True
    if unreachable:
        raise DatabaseUnavailableError()
    if current is None:
        raise NotFoundError(f"Bug {bug_id} not found")
    if current == BugStatus.PROCESSING.value:
        raise StateConflictError(f"Bug {bug_id} is already being processed")
    raise StateConflictError(f"Bug {bug_id} has already been processed; reopen it first")


# --- similar bugs ------------------------------------------------------------------------------


def _bug_data(bug: Bug) -> dict[str, Any]:
    return {
        "id": bug.id,
        "title": bug.title,
        "description": bug.description,
        "reproduction_steps": bug.reproduction_steps,
        "system_version": bug.system_version,
        "environment": bug.environment,
        "reporting_team": bug.reporting_team,
        "opened_at": bug.opened_at.isoformat(),
    }


def retrieve_similar_bugs(
    factory: sessionmaker[Session], client: Any, bug_id: int, k: int
) -> list[dict[str, Any]]:
    """Ensure the bug's embedding, fetch its nearest bugs and enrich the triaged ones."""
    with factory() as session:
        ensure_embedding(session, client, bug_id)
        session.commit()
    with factory() as session:
        hits = similar_to_bug(session, lambda: client, bug_id, k)
        ids = [hit.bug_id for hit in hits]
        components = dict(
            session.execute(
                select(ComponentClassification.bug_id, ComponentClassification.component).where(
                    ComponentClassification.bug_id.in_(ids)
                )
            ).all()
        )
        severities = dict(
            session.execute(
                select(SeverityClassification.bug_id, SeverityClassification.severity).where(
                    SeverityClassification.bug_id.in_(ids)
                )
            ).all()
        )
        analyses = {
            row.bug_id: row
            for row in session.execute(
                select(
                    TechnicalAnalysis.bug_id,
                    TechnicalAnalysis.root_cause,
                    TechnicalAnalysis.proposed_solution,
                ).where(TechnicalAnalysis.bug_id.in_(ids))
            )
        }
    similar: list[dict[str, Any]] = []
    for hit in hits:
        item: dict[str, Any] = {"id": hit.bug_id, "title": hit.title, "score": hit.score}
        if hit.bug_id in components:
            item["component"] = components[hit.bug_id]
        if hit.bug_id in severities:
            item["severity"] = severities[hit.bug_id]
        if hit.bug_id in analyses:
            item["root_cause"] = analyses[hit.bug_id].root_cause
            item["proposed_solution"] = analyses[hit.bug_id].proposed_solution
        similar.append(item)
    return similar


# --- pipeline ----------------------------------------------------------------------------------


def _write_results(
    factory: sessionmaker[Session], results: TriageResults, bug_id: int, run_id: int
) -> None:
    """Insert the five rows, run the hooks and set `processed` in one transaction."""
    with factory() as session:
        session.add_all(
            [
                ComponentClassification(
                    bug_id=bug_id,
                    run_id=run_id,
                    component=results.component.component.value,
                    justification=results.component.justification,
                ),
                SeverityClassification(
                    bug_id=bug_id,
                    run_id=run_id,
                    severity=results.severity.severity.value,
                    justification=results.severity.justification,
                    user_impact=results.severity.user_impact,
                ),
                TechnicalAnalysis(
                    bug_id=bug_id,
                    run_id=run_id,
                    root_cause=results.analysis.root_cause,
                    technical_impact=results.analysis.technical_impact,
                    debugging_approach=list(results.analysis.debugging_approach),
                    proposed_solution=results.analysis.proposed_solution,
                    side_effects=list(results.analysis.side_effects),
                    referenced_similar_bug_ids=list(results.analysis.referenced_similar_bug_ids),
                ),
                ResolutionPlan(
                    bug_id=bug_id,
                    run_id=run_id,
                    resolution_status=results.plan.resolution_status.value,
                    assigned_team=results.plan.assigned_team.value,
                    assignee_profile=results.plan.assignee_profile.model_dump(mode="json"),
                    target_days=results.plan.target_days,
                    priority=results.plan.priority.value,
                    notes=results.plan.notes,
                ),
                BugReport(
                    bug_id=bug_id,
                    run_id=run_id,
                    executive_summary=results.document.executive_summary,
                    key_takeaways=list(results.document.key_takeaways),
                    next_steps=list(results.document.next_steps),
                ),
            ]
        )
        session.flush()
        for hook in list(_RESULT_HOOKS):
            try:
                hook(session, bug_id, results)
            except Exception as exc:
                raise _HookError(str(exc) or type(exc).__name__) from None
        changed = session.execute(
            update(Bug)
            .where(Bug.id == bug_id, Bug.status == BugStatus.PROCESSING.value)
            .values(status=BugStatus.PROCESSED.value, updated_at=sql_func.clock_timestamp())
        ).rowcount
        if changed != 1:
            raise StateConflictError(f"Bug {bug_id} is no longer being processed")
        session.commit()


class _HookError(Exception):
    pass


def _database_error_text(exc: BaseException) -> str:
    original = getattr(exc, "orig", None)
    text = str(original if original is not None else exc)
    return text.splitlines()[0] if text else type(exc).__name__


def _mark_failed(factory: sessionmaker[Session], bug_id: int) -> None:
    with factory() as session:
        session.execute(
            update(Bug)
            .where(Bug.id == bug_id, Bug.status == BugStatus.PROCESSING.value)
            .values(status=BugStatus.FAILED.value, updated_at=sql_func.clock_timestamp())
        )
        session.commit()


def execute_triage(
    engine: Engine,
    get_client: Callable[[], Any],
    bug_id: int,
    run_id: int,
    redactor: Redactor | None = None,
    on_step: StepCallback | None = None,
    *,
    similar_k: int = DEFAULT_SEARCH_LIMIT,
    runner: Runner = run_agent,
) -> TriageOutcome:
    """Run the pipeline for a claimed bug and an existing run; returns an outcome.

    Provider and validation failures are returned as a `failed` outcome. A failure of the
    database itself raises `DatabaseUnavailableError`; the bug is then moved to `failed` on a
    best-effort basis.
    """
    factory = session_factory(engine)
    recorder = RunRecorder(factory, redactor)
    try:
        return _execute(factory, recorder, get_client, bug_id, run_id, on_step, similar_k, runner)
    except (OperationalError, InterfaceError):
        _abort(factory, recorder, bug_id, run_id)
        raise DatabaseUnavailableError() from None
    except BaseException:
        # Includes KeyboardInterrupt: an interrupted triage must not leave the bug `processing`.
        _abort(factory, recorder, bug_id, run_id)
        raise


def _abort(factory: sessionmaker[Session], recorder: RunRecorder, bug_id: int, run_id: int) -> None:
    """Best effort cleanup after an unexpected error: bug `failed`, run `failed`."""
    try:
        _mark_failed(factory, bug_id)
        recorder.finish_run(run_id, RunStatus.FAILED, "Triage aborted by an unexpected error")
    except Exception:  # noqa: S110
        pass


def _execute(
    factory: sessionmaker[Session],
    recorder: RunRecorder,
    get_client: Callable[[], Any],
    bug_id: int,
    run_id: int,
    on_step: StepCallback | None,
    similar_k: int,
    runner: Runner,
) -> TriageOutcome:
    redactor = recorder.redactor
    recorder.start_run(run_id)
    recorder.update_progress(run_id, 0, STEP_COUNT)
    recorder.create_steps(run_id, list(AGENT_KEYS))
    with factory() as session:
        row = session.get(Bug, bug_id, populate_existing=True)
        if row is None:
            raise NotFoundError(f"Bug {bug_id} not found")
        bug = _bug_data(row)

    summaries = [
        StepSummary(
            position=agent.position,
            key=agent.key,
            label=agent.label,
            status=StepStatus.PENDING,
            summary="",
        )
        for agent in AGENTS
    ]
    outputs: dict[str, BaseModel] = {}
    client: Any = None
    for agent in AGENTS:
        position = agent.position
        started = time.monotonic()
        recorder.append_log(run_id, "INFO", f"{agent.label} started")
        previous = {key: value.model_dump(mode="json") for key, value in outputs.items()}
        data: dict[str, Any] = {"bug": bug, "previous_outputs": previous}
        try:
            recorder.start_step(run_id, position, {"prompt": None, "data": data})
            similar: list[dict[str, Any]] = []
            if agent.key == "technical_analyst":
                client = client or _acquire_client(get_client, agent)
                similar = _similar_for_analyst(factory, client, bug_id, similar_k, agent)
                data["similar_bugs"] = similar
            prompt = render_prompt(agent.key, agent.model, bug, previous, similar)
            step_input: dict[str, Any] = {"prompt": prompt, "data": data}
            recorder.update_step_input(run_id, position, step_input)
            client = client or _acquire_client(get_client, agent)
            similar_ids = {item["id"] for item in similar}

            on_reask = _reask_recorder(recorder, run_id, agent, step_input)
            output = ask_agent(runner, agent, prompt, client, similar_ids, on_reask)
        except AgentFailure as failure:
            text = redactor.redact(failure.text)
            raw_output = {"raw_response": failure.raw[:RAW_RESPONSE_LIMIT]} if failure.raw else None
            return _fail(
                factory,
                recorder,
                bug_id,
                run_id,
                summaries,
                agent,
                text,
                raw_output,
                started,
                on_step,
            )
        duration_ms = int((time.monotonic() - started) * 1000)
        outputs[agent.key] = output
        recorder.finish_step(
            run_id,
            position,
            StepStatus.SUCCEEDED,
            output=output.model_dump(mode="json"),
            duration_ms=duration_ms,
        )
        recorder.update_progress(run_id, position, STEP_COUNT)
        recorder.append_log(run_id, "INFO", f"{agent.label} succeeded in {duration_ms} ms")
        summary = StepSummary(
            position=position,
            key=agent.key,
            label=agent.label,
            status=StepStatus.SUCCEEDED,
            summary=step_summary_text(output),
        )
        summaries[position - 1] = summary
        if on_step is not None:
            on_step(summary)

    results = TriageResults(
        bug_id=bug_id,
        run_id=run_id,
        component=outputs["component_classifier"],  # type: ignore[arg-type]
        severity=outputs["severity_classifier"],  # type: ignore[arg-type]
        analysis=outputs["technical_analyst"],  # type: ignore[arg-type]
        plan=outputs["resolution_manager"],  # type: ignore[arg-type]
        document=outputs["bug_documenter"],  # type: ignore[arg-type]
    )
    write_error: str | None = None
    try:
        _write_results(factory, results, bug_id, run_id)
    except _HookError as exc:
        write_error = f"Result hook failed: {exc}"
    except (OperationalError, InterfaceError):
        raise
    except DBAPIError as exc:
        write_error = f"Result write failed: {_database_error_text(exc)}"
    except ServiceError as exc:
        write_error = exc.message
    if write_error is not None:
        text = redactor.redact(write_error)
        _mark_failed(factory, bug_id)
        recorder.append_log(run_id, "ERROR", text)
        recorder.finish_run(run_id, RunStatus.FAILED, text)
        return TriageOutcome(
            bug_id=bug_id, run_id=run_id, status=BugStatus.FAILED, error=text, steps=summaries
        )
    recorder.append_log(run_id, "INFO", "Triage completed")
    recorder.finish_run(run_id, RunStatus.SUCCEEDED)
    return TriageOutcome(
        bug_id=bug_id, run_id=run_id, status=BugStatus.PROCESSED, error=None, steps=summaries
    )


def _reask_recorder(
    recorder: RunRecorder, run_id: int, agent: AgentSpec, step_input: dict[str, Any]
) -> Callable[[str], None]:
    def record(error_text: str) -> None:
        recorder.append_log(run_id, "WARNING", f"{agent.label} re-ask: {error_text}")
        recorder.update_step_input(
            run_id, agent.position, {**step_input, "reask": {"validation_error": error_text}}
        )

    return record


def _acquire_client(get_client: Callable[[], Any], agent: AgentSpec) -> Any:
    failure: str | None = None
    try:
        return get_client()
    except ConfigError as exc:
        failure = exc.message
    except LlmError as exc:
        failure = exc.message
    raise AgentFailure(f"AG{agent.position} failed: {failure}")


def _similar_for_analyst(
    factory: sessionmaker[Session], client: Any, bug_id: int, k: int, agent: AgentSpec
) -> list[dict[str, Any]]:
    failure: str | None = None
    try:
        return retrieve_similar_bugs(factory, client, bug_id, k)
    except LlmError as exc:
        failure = exc.message
    raise AgentFailure(f"AG{agent.position} failed: {failure}")


def _call_agent(runner: Runner, agent: AgentSpec, prompt: str, client: Any) -> str:
    failure: str | None = None
    try:
        return runner(agent, prompt, client)
    except AgentCallError as exc:
        failure = exc.llm_message
    except Exception as exc:
        logger.warning("Agent %s raised %s", agent.key, type(exc).__name__)
        failure = UNEXPECTED_AGENT_ERROR
    raise AgentFailure(f"AG{agent.position} failed: {failure}")


def _fail(
    factory: sessionmaker[Session],
    recorder: RunRecorder,
    bug_id: int,
    run_id: int,
    summaries: list[StepSummary],
    agent: AgentSpec,
    text: str,
    raw_output: dict[str, Any] | None,
    started: float,
    on_step: StepCallback | None,
) -> TriageOutcome:
    duration_ms = int((time.monotonic() - started) * 1000)
    recorder.finish_step(
        run_id,
        agent.position,
        StepStatus.FAILED,
        output=raw_output,
        error=text,
        duration_ms=duration_ms,
    )
    recorder.skip_remaining(run_id, agent.position)
    for position in range(agent.position + 1, STEP_COUNT + 1):
        later = AGENTS[position - 1]
        summaries[position - 1] = StepSummary(
            position=position,
            key=later.key,
            label=later.label,
            status=StepStatus.SKIPPED,
            summary="",
        )
    summaries[agent.position - 1] = StepSummary(
        position=agent.position,
        key=agent.key,
        label=agent.label,
        status=StepStatus.FAILED,
        summary=text,
    )
    if on_step is not None:
        on_step(summaries[agent.position - 1])
    _mark_failed(factory, bug_id)
    recorder.append_log(run_id, "ERROR", f"{agent.label} failed: {text}")
    recorder.finish_run(run_id, RunStatus.FAILED, text)
    return TriageOutcome(
        bug_id=bug_id, run_id=run_id, status=BugStatus.FAILED, error=text, steps=summaries
    )


def triage_bug(
    engine: Engine,
    get_client: Callable[[], Any],
    bug_id: int,
    redactor: Redactor | None = None,
    on_step: StepCallback | None = None,
    *,
    similar_k: int = DEFAULT_SEARCH_LIMIT,
    runner: Runner = run_agent,
) -> TriageOutcome:
    """Claim the bug, create a `triage` run and execute the pipeline.

    A rejected claim raises before any run is created.
    """
    claim_bug(engine, bug_id)
    factory = session_factory(engine)
    try:
        run_id = RunRecorder(factory, redactor).create_run(RunType.TRIAGE, bug_id, STEP_COUNT)
    except Exception as exc:
        unreachable = isinstance(exc, OperationalError | InterfaceError)
        try:
            _mark_failed(factory, bug_id)
        except Exception:  # noqa: S110
            pass
        if unreachable:
            raise DatabaseUnavailableError() from None
        raise
    return execute_triage(
        engine,
        get_client,
        bug_id,
        run_id,
        redactor,
        on_step,
        similar_k=similar_k,
        runner=runner,
    )


def triage_all(
    engine: Engine,
    get_client: Callable[[], Any],
    redactor: Redactor | None = None,
    on_step: StepCallback | None = None,
    *,
    on_outcome: OutcomeCallback | None = None,
    similar_k: int = DEFAULT_SEARCH_LIMIT,
    runner: Runner = run_agent,
) -> list[TriageOutcome]:
    """Triage every `open` bug in id order, one at a time; failures never stop the batch."""
    factory = session_factory(engine)
    try:
        with factory() as session:
            ids = list(
                session.scalars(
                    select(Bug.id).where(Bug.status == BugStatus.OPEN.value).order_by(Bug.id)
                )
            )
    except (OperationalError, InterfaceError):
        raise DatabaseUnavailableError() from None
    outcomes: list[TriageOutcome] = []
    for bug_id in ids:
        try:
            outcome = triage_bug(
                engine,
                get_client,
                bug_id,
                redactor,
                on_step,
                similar_k=similar_k,
                runner=runner,
            )
        except (StateConflictError, NotFoundError):
            logger.info("Bug %s was claimed elsewhere or removed; skipped", bug_id)
            continue
        outcomes.append(outcome)
        if on_outcome is not None:
            on_outcome(outcome)
    return outcomes
