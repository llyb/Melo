"""Explicit paid native-thread smoke; only temporary synthetic messages are persisted."""
import asyncio
import logging
import sys
from pathlib import Path
from tempfile import TemporaryDirectory
from uuid import uuid4

from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver

from app.agent import AgentRunner
from app.settings import Settings


async def main():
    logging.disable(logging.CRITICAL)
    settings = Settings.from_env()
    if not settings.model_configured:
        raise RuntimeError("MODEL_API_KEY and MODEL_NAME are required")
    with TemporaryDirectory(prefix="melo-live-") as directory:
        async with AsyncSqliteSaver.from_conn_string(str(Path(directory) / "live.sqlite3")) as saver:
            runner = AgentRunner(settings, checkpointer=saver)
            sid, tag = str(uuid4()), uuid4().hex[:8]
            try:
                base = await runner.initialize_thread(sid)
                first = await asyncio.wait_for(runner.run_turn(
                    sid, str(uuid4()), 1, base, f"请记住校验码 {tag}，只回复已收到。", str(uuid4())), 60)
                second = await asyncio.wait_for(runner.run_turn(
                    sid, str(uuid4()), 1, first["result_checkpoint_id"],
                    "上一条校验码是什么？只返回校验码。", str(uuid4())), 60)
                assert tag in second["text"], "Native two-turn context verification failed"
                print(f"PASS: live native-thread two-turn context; model={settings.model_name}")
            finally:
                runner.close()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except Exception as error:  # noqa: BLE001 -- do not expose provider payloads
        print(f"LIVE CHECK FAILED: {type(error).__name__}")
        sys.exit(1)
