# app/tasks/worker.py
import asyncio
import logging

logging.basicConfig(level=logging.INFO, format="%(asctime)s [worker] %(message)s")
logger = logging.getLogger(__name__)


async def main() -> None:
    logger.info("Worker started, waiting for jobs...")
    # Здесь будет цикл обработки задач.
    # Заглушка: держим процесс живым, чтобы контейнер не рестартился.
    while True:
        await asyncio.sleep(3600)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Worker stopped")
