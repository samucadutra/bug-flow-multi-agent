import io
import logging
import re

import pytest

from bugflow.logging_config import bind_run, configure_logging, get_logger


@pytest.fixture
def emit(make_settings, canary_api_key):
    def _setup(level="DEBUG", key=canary_api_key):
        env = {"LOG_LEVEL": level}
        if key:
            env["OPENAI_API_KEY"] = key
        settings = make_settings(**env)
        stream = io.StringIO()
        configure_logging(settings, stream=stream)
        return get_logger("bugflow.test"), stream

    yield _setup
    logger = logging.getLogger("bugflow")
    for handler in list(logger.handlers):
        logger.removeHandler(handler)


def test_line_format(emit):
    logger, stream = emit()
    logger.info("Starting up")
    lines = stream.getvalue().splitlines()
    assert len(lines) == 1
    assert re.fullmatch(r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ INFO Starting up", lines[0])


def test_run_id_segment(emit):
    logger, stream = emit()
    bind_run(logger, 42).info("Seeded 20 bugs")
    line = stream.getvalue().strip()
    assert "[run=42]" in line
    assert line.endswith("Seeded 20 bugs")


def test_masks_key_in_message(emit, canary_api_key):
    logger, stream = emit()
    logger.info("key is %s here" % canary_api_key)  # noqa: UP031
    assert "***" in stream.getvalue()
    assert canary_api_key not in stream.getvalue()


def test_masks_key_in_args(emit, canary_api_key):
    logger, stream = emit()
    logger.info("key=%s", canary_api_key)
    assert "key=***" in stream.getvalue()
    assert canary_api_key not in stream.getvalue()


def test_masks_db_password_in_url(emit, canary_db_url, canary_db_password):
    logger, stream = emit()
    logger.info("connecting to %s", canary_db_url)
    out = stream.getvalue()
    assert canary_db_password not in out
    assert "localhost" in out
    assert "bugflow" in out


def test_masks_secret_in_exception_text(emit, canary_api_key):
    logger, stream = emit()
    try:
        raise ValueError(f"bad key {canary_api_key}")
    except ValueError:
        logger.exception("failed")
    out = stream.getvalue()
    assert canary_api_key not in out
    assert "ValueError" in out


def test_masks_unconfigured_sk_token(emit):
    logger, stream = emit(key="")
    logger.info("token sk-abcdefghijklmnop1234 leaked")
    assert "sk-abcdefghijklmnop1234" not in stream.getvalue()


def test_empty_secret_does_not_mask_everything(emit):
    logger, stream = emit(key="")
    logger.info("Seeded 20 bugs")
    assert stream.getvalue().strip().endswith("INFO Seeded 20 bugs")
    assert "***" not in stream.getvalue()


def test_level_filtering(emit):
    logger, stream = emit(level="WARNING")
    logger.info("quiet")
    logger.warning("loud")
    out = stream.getvalue()
    assert "quiet" not in out
    assert "loud" in out


def test_configure_logging_idempotent(make_settings):
    settings = make_settings()
    configure_logging(settings, stream=io.StringIO())
    configure_logging(settings, stream=io.StringIO())
    logger = logging.getLogger("bugflow")
    ours = [h for h in logger.handlers if getattr(h, "_bugflow_handler", False)]
    assert len(ours) == 1
    logger.removeHandler(ours[0])
