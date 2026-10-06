"""Agent runner: one agent per step, run as a one-agent sequential crew with no tools.

`crewai` is imported lazily so `bugflow --version`, `--help` and unrelated commands stay fast.
The runner returns the raw reply text; validation belongs to the triage service.
"""

from __future__ import annotations

import logging
from typing import Any

from bugflow.agents.outputs import AgentSpec
from bugflow.config import configure_third_party_runtime


def _silence_crewai_logging() -> None:
    """Keep CrewAI's own error logging off stderr; failures are reported by the triage service."""
    crewai_logger = logging.getLogger("crewai")
    crewai_logger.propagate = False
    if not any(isinstance(h, logging.NullHandler) for h in crewai_logger.handlers):
        crewai_logger.addHandler(logging.NullHandler())


def run_agent(agent: AgentSpec, prompt: str, client: Any) -> str:
    """Run one agent on a rendered prompt and return the raw text of its reply.

    Raises `AgentCallError` when the provider call fails (the shared client already retried).
    """
    configure_third_party_runtime()
    from crewai import Agent, Process, Task

    from bugflow.agents.crew_llm import BugflowCrewLlm, OneShotCrew

    _silence_crewai_logging()

    llm = BugflowCrewLlm(model=client.chat_model, temperature=0.0, client=client)
    crew_agent = Agent(
        role=agent.role,
        goal=agent.goal,
        backstory=agent.backstory,
        llm=llm,
        tools=[],
        allow_delegation=False,
        verbose=False,
        max_iter=1,
        max_retry_limit=0,
        memory=False,
        cache=False,
    )
    task = Task(
        description=prompt,
        expected_output=f"A JSON object with the {agent.role} answer.",
        agent=crew_agent,
    )
    crew = OneShotCrew(
        agents=[crew_agent],
        tasks=[task],
        process=Process.sequential,
        verbose=False,
        memory=False,
        cache=False,
        tracing=False,
    )
    output = crew.kickoff()
    return str(output.raw)
