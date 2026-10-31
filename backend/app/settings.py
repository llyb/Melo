import os
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urlsplit

from dotenv import load_dotenv
from langsmith import agent_address


@dataclass(frozen=True)
class Settings:
    local_token: str = field(repr=False)
    model_api_key: str = field(default="", repr=False)
    model_base_url: str = "https://api.z.ai/api/paas/v4"
    model_name: str = "glm-5.3"
    langsmith_enabled: bool = False
    langsmith_api_key: str = field(default="", repr=False)
    langsmith_project: str = "melo"
    langsmith_endpoint: str = "https://api.smith.langchain.com"
    langsmith_workspace_id: str = ""
    langsmith_agent_id: str = ""
    langsmith_agent_environment: str = "development"

    def __post_init__(self):
        try:
            model_url = urlsplit(self.model_base_url)
            valid_model_url = (model_url.scheme in {"http", "https"} and model_url.hostname
                               and not (model_url.username or model_url.password
                                        or model_url.query or model_url.fragment))
            _ = model_url.port  # Validate a supplied port without exposing the URL in errors.
        except ValueError:
            valid_model_url = False
        if not valid_model_url:
            raise ValueError("MODEL_BASE_URL must be an HTTP(S) API base URL without credentials, query or fragment")
        if self.langsmith_enabled:
            if not self.langsmith_api_key.strip():
                raise ValueError("LANGSMITH_API_KEY is required when LANGSMITH_TRACING=true")
            if self.langsmith_agent_id:
                agent_address(self.langsmith_agent_id, self.langsmith_agent_environment)
            elif not self.langsmith_project.strip():
                raise ValueError("LANGSMITH_PROJECT must not be empty")
            endpoint = urlsplit(self.langsmith_endpoint)
            local = endpoint.hostname in {"localhost", "127.0.0.1", "::1"}
            if (not endpoint.hostname or endpoint.username or endpoint.password
                    or endpoint.query or endpoint.fragment
                    or (endpoint.scheme != "https" and not (local and endpoint.scheme == "http"))):
                raise ValueError("LANGSMITH_ENDPOINT must be HTTPS (or local HTTP)")

    @property
    def model_configured(self):
        return bool(self.model_api_key.strip() and self.model_name.strip())

    @classmethod
    def from_env(cls):
        load_dotenv(Path(__file__).resolve().parents[1] / ".env")
        token = os.getenv("MELO_LOCAL_TOKEN", "").strip()
        if not token:
            raise RuntimeError("Set MELO_LOCAL_TOKEN in backend/.env before starting.")
        base = os.getenv("MODEL_BASE_URL", cls.model_base_url).strip().rstrip("/")
        tracing = os.getenv("LANGSMITH_TRACING", "false").strip().lower()
        if tracing not in {"true", "false"}:
            raise ValueError("LANGSMITH_TRACING must be true or false")
        return cls(
            token, os.getenv("MODEL_API_KEY", "").strip(), base,
            os.getenv("MODEL_NAME", cls.model_name).strip(),
            langsmith_enabled=tracing == "true",
            langsmith_api_key=os.getenv("LANGSMITH_API_KEY", "").strip(),
            langsmith_project=os.getenv("LANGSMITH_PROJECT", cls.langsmith_project).strip(),
            langsmith_endpoint=os.getenv("LANGSMITH_ENDPOINT", cls.langsmith_endpoint).strip().rstrip("/"),
            langsmith_workspace_id=os.getenv("LANGSMITH_WORKSPACE_ID", "").strip(),
            langsmith_agent_id=os.getenv("LANGSMITH_AGENT_ID", "").strip(),
            langsmith_agent_environment=os.getenv("LANGSMITH_AGENT_ENVIRONMENT", "development").strip(),
        )
