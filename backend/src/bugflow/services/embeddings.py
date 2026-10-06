"""Embedding layer: text builders, stale detection, `ensure_embedding` and `index_all_bugs`."""

from __future__ import annotations

import hashlib
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Protocol

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session, sessionmaker

from bugflow.db.models import Bug, BugEmbedding
from bugflow.services.errors import NotFoundError

BATCH_SIZE = 20

BatchCallback = Callable[[int, int, int, int, int], None]


class EmbeddingClient(Protocol):
    embedding_model: str

    def embed(self, texts: Sequence[str]) -> list[list[float]]: ...


@dataclass(frozen=True)
class IndexResult:
    indexed: int
    total: int


def enriched_text(bug: Bug) -> str:
    """The five labeled lines that are embedded. Status, team and dates are not part of it."""
    return "\n".join(
        (
            f"Title: {bug.title}",
            f"Description: {bug.description}",
            f"Steps to reproduce: {bug.reproduction_steps}",
            f"System version: {bug.system_version}",
            f"Environment: {bug.environment}",
        )
    )


def query_text(text: str) -> str:
    """The text embedded for a search: the user's input without surrounding whitespace."""
    return text.strip()


def text_hash(model: str, text: str) -> str:
    """SHA-256 hex of the embedding model name and the enriched text."""
    return hashlib.sha256(f"{model}\n{text}".encode()).hexdigest()


def _upsert(session: Session, bug_id: int, vector: list[float], digest: str) -> None:
    statement = insert(BugEmbedding).values(
        bug_id=bug_id, embedding=vector, text_hash=digest, embedded_at=func.clock_timestamp()
    )
    session.execute(
        statement.on_conflict_do_update(
            index_elements=[BugEmbedding.bug_id],
            set_={
                "embedding": statement.excluded.embedding,
                "text_hash": statement.excluded.text_hash,
                "embedded_at": func.clock_timestamp(),
            },
        )
    )


def ensure_embedding(session: Session, client: EmbeddingClient, bug_id: int) -> bool:
    """Create or refresh the bug's embedding when missing or stale; flush, never commit.

    Returns True when an embedding was written.
    """
    bug = session.get(Bug, bug_id, populate_existing=True)
    if bug is None:
        raise NotFoundError(f"Bug {bug_id} not found")
    digest = text_hash(client.embedding_model, enriched_text(bug))
    stored = session.scalar(select(BugEmbedding.text_hash).where(BugEmbedding.bug_id == bug_id))
    if stored == digest:
        return False
    (vector,) = client.embed([enriched_text(bug)])
    _upsert(session, bug_id, vector, digest)
    session.flush()
    return True


def index_all_bugs(
    factory: sessionmaker[Session],
    client: EmbeddingClient,
    on_batch: BatchCallback | None = None,
) -> IndexResult:
    """Rebuild the embedding of every bug (any status), one committed transaction per batch."""
    with factory() as session:
        bugs = list(session.scalars(select(Bug).order_by(Bug.id)))
        items = [(bug.id, enriched_text(bug)) for bug in bugs]
    total = len(items)
    batch_count = -(-total // BATCH_SIZE)
    done = 0
    for number in range(1, batch_count + 1):
        batch = items[(number - 1) * BATCH_SIZE : number * BATCH_SIZE]
        vectors = client.embed([text for _, text in batch])
        with factory() as session:
            for (bug_id, text), vector in zip(batch, vectors, strict=True):
                _upsert(session, bug_id, vector, text_hash(client.embedding_model, text))
            session.commit()
        done += len(batch)
        if on_batch is not None:
            on_batch(done, total, number, batch_count, len(batch))
    return IndexResult(indexed=done, total=total)
