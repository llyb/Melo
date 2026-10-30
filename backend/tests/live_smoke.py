"""Explicit paid two-turn provider smoke. No credentials or responses are persisted."""
import asyncio
import logging
import os
import sys
from uuid import uuid4

from app.agent import AgentRunner
from app.schemas import Message
from app.settings import Settings


async def main():
    logging.disable(logging.CRITICAL)
    key = os.getenv("MODEL_API_KEY") or sys.stdin.readline().strip()
    if not key:
        raise RuntimeError("MODEL_API_KEY is required")
    settings = Settings(local_token="live-smoke-only", model_api_key=key,
                        model_name=os.getenv("MODEL_NAME", "glm-5.3"))
    runner = AgentRunner(settings)
    tag = uuid4().hex[:8]
    messages = [Message(role="user", content=f"请记住校验码 {tag}，只回复已收到。")]
    first = await asyncio.wait_for(runner.reply(messages), 60)
    messages += [Message(role="assistant", content=first),
                 Message(role="user", content="上一条校验码是什么？只返回校验码。")]
    second = await asyncio.wait_for(runner.reply(messages), 60)
    assert tag in second, "Two-turn context verification failed"
    print(f"PASS: live Deep Agents two-turn context; model={settings.model_name}")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except Exception as error:  # noqa: BLE001 -- never print provider bodies or credentials
        print(f"LIVE CHECK FAILED: {type(error).__name__}")
        sys.exit(1)
