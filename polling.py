"""Timing shared by the public catalogue monitors."""
from concurrent.futures import ThreadPoolExecutor
import json
import os
from datetime import timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from queue import Queue
import time

POLL_SECONDS = 20
WINDOW_SECONDS = 60


def remaining_slots(started):
    """Yield the two remaining ticks in a minute, without replaying missed ticks."""
    for offset in range(POLL_SECONDS, WINDOW_SECONDS, POLL_SECONDS):
        delay = started + offset - time.monotonic()
        if delay < 0:
            continue
        time.sleep(delay)
        yield offset


def retry_delay(value, default=60):
    try:
        return max(0, int(value))
    except (ValueError, TypeError):
        try:
            until = parsedate_to_datetime(value)
            if until.tzinfo is None:
                until = until.replace(tzinfo=timezone.utc)
            return max(0, until.timestamp() - time.time())
        except (TypeError, ValueError, OverflowError):
            return default


def trace(profile, event, **counts):
    """Optional receipt from the production process. No URLs or listing data."""
    destination = os.environ.get("POLL_TRACE_DIR")
    if destination:
        path = Path(destination) / (profile + ".jsonl")
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open("a", encoding="utf-8") as output:
                output.write(json.dumps({"at": round(time.time(), 3), "event": event, **counts}) + "\n")
        except OSError:
            pass  # Diagnostics must never interrupt a delivery.

def stream_workers(tasks, workers):
    """Workers only fetch. Their events are consumed by one owner of delivery state."""
    ready = Queue()
    finished = object()

    def run(task):
        try:
            task(ready.put)
        except Exception as error:
            ready.put(error)
        finally:
            ready.put(finished)

    with ThreadPoolExecutor(max_workers=workers) as pool:
        for task in tasks:
            pool.submit(run, task)
        remaining = len(tasks)
        while remaining:
            event = ready.get()
            if event is finished:
                remaining -= 1
            elif isinstance(event, Exception):
                raise event
            else:
                yield event


def summarize(directory):
    lines = []
    for path in sorted(Path(directory).glob("*.jsonl")):
        events = [json.loads(line) for line in path.read_text().splitlines() if line]
        reads = sorted(event["started"] for event in events if event["event"] == "front_read")
        gaps = [later - earlier for earlier, later in zip(reads, reads[1:])]
        accepted = [event["since_detection"] for event in events if event["event"] == "accepted"]
        parts = [f"{path.stem} • odczyty {len(reads)}"]
        if gaps:
            parts.append(f"najdłuższy odstęp {max(gaps):.1f} s")
        parts.append(f"wysyłki {len(accepted)}")
        if accepted:
            parts.append(f"do potwierdzenia maks. {max(accepted):.1f} s od wykrycia")
        lines.append(", ".join(parts))
    return " | ".join(lines) or "Brak zarejestrowanych odczytów"


if __name__ == "__main__":
    import sys
    summary = summarize(sys.argv[1])
    print(summary)
    for name, line in (("GITHUB_STEP_SUMMARY", summary), ("GITHUB_OUTPUT", "sample=" + summary)):
        if os.getenv(name):
            with open(os.environ[name], "a", encoding="utf-8") as output:
                print(line, file=output)
