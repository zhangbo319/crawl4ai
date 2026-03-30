import asyncio
import json
import os

from news_scheduler_service import NewsSchedulerService


def _enabled() -> bool:
    return os.environ.get("BIOON_NEWS_SCHEDULER_ENABLED", "true").lower() == "true"


def _interval() -> int:
    return int(os.environ.get("BIOON_NEWS_SCHEDULER_INTERVAL_SECONDS", "60"))


async def main() -> None:
    printed_disabled = False
    service = NewsSchedulerService()
    while True:
        if not _enabled():
            if not printed_disabled:
                print("[bioon-news-scheduler] disabled, sleeping", flush=True)
                printed_disabled = True
            await asyncio.sleep(3600)
            continue

        printed_disabled = False
        try:
            results = await service.run_due_schedules()
            if results:
                print(f"[bioon-news-scheduler] trigger success: {json.dumps(results, ensure_ascii=False)}", flush=True)
        except Exception as exc:  # pragma: no cover
            print(f"[bioon-news-scheduler] trigger failed: {exc}", flush=True)
        await asyncio.sleep(_interval())


if __name__ == "__main__":
    asyncio.run(main())
