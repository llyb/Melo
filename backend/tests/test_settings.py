import pytest

from app.settings import Settings


@pytest.mark.parametrize("base", ["https://gateway.example/v1", "http://127.0.0.1:1234/v1",
                                 "http://192.168.1.5:8080/api/v1"])
def test_env_accepts_custom_model_endpoint(monkeypatch, base):
    monkeypatch.setattr("app.settings.load_dotenv", lambda *_args, **_kwargs: None)
    monkeypatch.setenv("MELO_LOCAL_TOKEN", "local-token")
    monkeypatch.setenv("LANGSMITH_TRACING", "false")
    monkeypatch.setenv("MODEL_BASE_URL", f" {base}/ ")
    monkeypatch.setenv("MODEL_API_KEY", " custom-key ")
    monkeypatch.setenv("MODEL_NAME", " custom-chat ")
    settings = Settings.from_env()
    assert settings.model_base_url == base
    assert settings.model_api_key == "custom-key"
    assert settings.model_name == "custom-chat"
    assert settings.model_configured


@pytest.mark.parametrize("base", ["", "gateway.example/v1", "ftp://gateway.example/v1",
    "https://user:password@gateway.example/v1", "https://gateway.example/v1?key=secret",
    "https://gateway.example/v1#fragment", "http://[broken", "https://gateway.example:bad/v1"])
def test_invalid_model_endpoint_is_rejected_without_echoing_value(base):
    with pytest.raises(ValueError, match="MODEL_BASE_URL") as error:
        Settings(local_token="t", model_base_url=base)
    assert "password" not in str(error.value)
    assert "secret" not in str(error.value)
