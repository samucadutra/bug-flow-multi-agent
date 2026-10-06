import pytest

from bugflow.config import ConfigError, load_settings


def test_defaults_applied(make_settings):
    s = make_settings()
    assert s.openai_model == "gpt-4o-mini"
    assert s.openai_embedding_model == "text-embedding-3-small"
    assert s.llm_timeout_seconds == 60
    assert s.llm_max_retries == 2
    assert s.similar_bugs_k == 5
    assert s.api_host == "127.0.0.1"
    assert s.api_port == 8000
    assert s.cors_origins == ["http://localhost:3000"]
    assert s.log_level == "INFO"
    assert s.test_database_url is None


def test_env_overrides_defaults(make_settings):
    s = make_settings(OPENAI_MODEL="custom-model", API_PORT="9000", LLM_MAX_RETRIES="0")
    assert s.openai_model == "custom-model"
    assert s.api_port == 9000
    assert s.llm_max_retries == 0


def test_env_beats_env_file(clean_env, tmp_path, canary_db_url):
    env_file = tmp_path / ".env"
    env_file.write_text(f"DATABASE_URL={canary_db_url}\nOPENAI_MODEL=from-file\nAPI_PORT=7000\n")
    clean_env.setenv("OPENAI_MODEL", "from-env")
    s = load_settings(env_file=env_file)
    assert s.openai_model == "from-env"
    assert s.api_port == 7000


def test_missing_openai_key_does_not_crash(make_settings):
    s = make_settings()
    assert s.has_openai_key is False
    with pytest.raises(ConfigError) as info:
        s.require_openai_key()
    assert str(info.value) == "OPENAI_API_KEY is not set"


def test_require_openai_key_returns_key(make_settings, canary_api_key):
    assert make_settings(OPENAI_API_KEY=canary_api_key).require_openai_key() == canary_api_key


def test_missing_database_url_fails_fast(clean_env):
    with pytest.raises(ConfigError) as info:
        load_settings(env_file=None)
    assert str(info.value) == "DATABASE_URL is missing or invalid"


def test_empty_database_url_fails_fast(clean_env):
    clean_env.setenv("DATABASE_URL", "")
    with pytest.raises(ConfigError) as info:
        load_settings(env_file=None)
    assert str(info.value) == "DATABASE_URL is missing or invalid"


def test_malformed_database_url_message_has_no_value(clean_env, canary_db_password):
    clean_env.setenv("DATABASE_URL", f"mysql://bugflow:{canary_db_password}@localhost:5432/bugflow")
    with pytest.raises(ConfigError) as info:
        load_settings(env_file=None)
    assert str(info.value) == "DATABASE_URL is missing or invalid"
    assert canary_db_password not in str(info.value)
    assert "mysql" not in str(info.value)
    assert info.value.__cause__ is None
    assert info.value.__suppress_context__


def test_invalid_numeric_names_variable_only(make_settings):
    with pytest.raises(ConfigError) as info:
        make_settings(LLM_TIMEOUT_SECONDS="abc")
    assert "LLM_TIMEOUT_SECONDS" in str(info.value)
    assert "abc" not in str(info.value)


@pytest.mark.parametrize(
    ("name", "value"),
    [("SIMILAR_BUGS_K", "21"), ("SIMILAR_BUGS_K", "0"), ("API_PORT", "0"), ("API_PORT", "65536")],
)
def test_numeric_bounds(make_settings, name, value):
    with pytest.raises(ConfigError) as info:
        make_settings(**{name: value})
    assert str(info.value) == f"{name} is invalid"


def test_log_level_case_insensitive(make_settings):
    assert make_settings(LOG_LEVEL="warning").log_level == "WARNING"


def test_invalid_log_level(make_settings):
    with pytest.raises(ConfigError):
        make_settings(LOG_LEVEL="loud")


def test_cors_origins_comma_separated(make_settings):
    s = make_settings(CORS_ORIGINS="http://a.example, http://b.example")
    assert s.cors_origins == ["http://a.example", "http://b.example"]


def test_unrelated_variables_ignored(make_settings):
    s = make_settings(POSTGRES_PASSWORD="x", NEXT_PUBLIC_API_BASE_URL="http://x/api")
    assert s.api_port == 8000


def test_test_database_url_validated(make_settings):
    with pytest.raises(ConfigError) as info:
        make_settings(TEST_DATABASE_URL="http://nope")
    assert str(info.value) == "TEST_DATABASE_URL is invalid"


def test_repr_masks_secrets(make_settings, canary_api_key, canary_db_password):
    text = repr(make_settings(OPENAI_API_KEY=canary_api_key))
    assert "***" in text
    assert canary_api_key not in text
    assert canary_db_password not in text


def test_str_masks_secrets(make_settings, canary_api_key, canary_db_password):
    text = str(make_settings(OPENAI_API_KEY=canary_api_key))
    assert "***" in text
    assert canary_api_key not in text
    assert canary_db_password not in text
