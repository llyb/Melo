"""Offline desktop smoke only: actual Deep Agents with a deterministic local model."""
import os
from pathlib import Path

from app.agent import AgentRunner
from app.main import create_app
from app.settings import Settings
from tests.test_agent import LocalModel

settings = Settings(local_token=os.environ["MELO_LOCAL_TOKEN"], model_api_key="offline-only",
                    data_dir=Path(os.environ["MELO_TEST_DATA_DIR"]))
app = create_app(settings, AgentRunner(settings, model=LocalModel()))
