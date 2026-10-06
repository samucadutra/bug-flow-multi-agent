from bugflow.db.errors import (
    BugflowDatabaseError,
    DatabaseUnavailableError,
    PgvectorUnavailableError,
)


def test_unavailable_message_exact():
    error = DatabaseUnavailableError()
    assert str(error) == "Cannot connect to the database"
    assert isinstance(error, BugflowDatabaseError)


def test_pgvector_message_exact():
    error = PgvectorUnavailableError()
    assert str(error) == "pgvector extension is not available; use the pgvector/pgvector image"
    assert isinstance(error, BugflowDatabaseError)


def test_messages_never_contain_canary_url(canary_db_url, canary_db_password):
    for error in (DatabaseUnavailableError(), PgvectorUnavailableError()):
        for text in (str(error), repr(error), *map(str, error.args)):
            assert canary_db_url not in text
            assert canary_db_password not in text
