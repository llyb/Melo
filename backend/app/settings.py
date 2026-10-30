import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv


@dataclass(frozen=True)
class Settings:
    local_token: str = field(repr=False)
    model_api_key: str = field(default="", repr=False)
    model_base_url: str = "https://api.z.ai/api/paas/v4"
    model_name: str = "glm-5.3"

    @property
    def model_configured(self):
        return bool(self.model_api_key.strip() and self.model_name.strip())

    @classmethod
    def from_env(cls):
        load_dotenv(Path(__file__).resolve().parents[1] / ".env")
        token = os.getenv("MELO_LOCAL_TOKEN", "").strip()
        if not token:
            raise RuntimeError("Set MELO_LOCAL_TOKEN in backend/.env before starting.")
        base = os.getenv("MODEL_BASE_URL", cls.model_base_url).rstrip("/")
        if base != "https://api.z.ai/api/paas/v4":
            raise RuntimeError("MODEL_BASE_URL must use the configured Z.AI standard endpoint.")
        return cls(token, os.getenv("MODEL_API_KEY", ""), base,
                   os.getenv("MODEL_NAME", cls.model_name))
