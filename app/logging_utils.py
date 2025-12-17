# app/logging_utils.py
import time
import queue

log_queue: "queue.Queue[str]" = queue.Queue()

def log(msg: str) -> None:
    ts = time.strftime("%H:%M:%S")
    line = f"[{ts}] {msg}"
    print(line, flush=True)
    log_queue.put(line)
