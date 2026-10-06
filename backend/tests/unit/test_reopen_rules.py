import inspect

from bugflow.db.base import Base
from bugflow.services import reopen as reopen_module
from bugflow.services.reopen import (
    REOPENABLE_STATUSES,
    RESULT_MODELS,
    ReopenFailedError,
    already_open_message,
    clear_reopen_hooks,
    processing_message,
    register_reopen_hook,
    unregister_reopen_hook,
)


def test_deleted_tables_are_the_five_result_tables():
    expected = {
        table.name
        for table in Base.metadata.tables.values()
        if [c.name for c in table.primary_key.columns] == ["bug_id"] and "run_id" in table.columns
    }
    assert {model.__tablename__ for model in RESULT_MODELS} == expected
    assert len(expected) == 5
    assert "bug_embeddings" not in expected


def test_source_statuses_derive_from_the_transition_table():
    assert set(REOPENABLE_STATUSES) == {"processed", "failed"}


def test_rejection_messages_are_fixed_text():
    assert processing_message(7) == "Bug 7 is being processed and cannot be reopened"
    assert already_open_message(7) == "Bug 7 is already open"
    assert str(ReopenFailedError(7)) == "Reopen of bug 7 failed; nothing was changed"


def test_hook_registry_order_and_clear():
    clear_reopen_hooks()

    def first(session, bug_id):
        return None

    def second(session, bug_id):
        return None

    register_reopen_hook(first)
    register_reopen_hook(second)
    assert reopen_module._REOPEN_HOOKS == [first, second]
    unregister_reopen_hook(first)
    unregister_reopen_hook(first)
    assert reopen_module._REOPEN_HOOKS == [second]
    clear_reopen_hooks()
    assert reopen_module._REOPEN_HOOKS == []


def test_statements_use_only_allowlisted_models():
    source = inspect.getsource(reopen_module.reopen_bug)
    assert "for model in RESULT_MODELS" in source
    assert "text(" not in source.replace("context(", "") and "execute(f" not in source
    assert (
        "BugEmbedding" not in inspect.getsource(reopen_module).split("RESULT_MODELS = (")[1][:200]
    )
