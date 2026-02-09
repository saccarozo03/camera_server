# app/api.py
from fastapi import FastAPI
from contextlib import asynccontextmanager
from fastapi.responses import StreamingResponse, HTMLResponse

import asyncio
import json
import urllib.request

from .logging_utils import log_queue, log
from . import recorder, camera

# ==========================
# AUTO TRIGGER CONFIG (tối thiểu)
# ==========================
MOVES_URL = "http://saccarozo04-ThinkBook-16-G8-IRL.local:8090/chassis/moves"
POLL_INTERVAL = 0.5
TRIGGER_ONLY_WHEN_CANCELLED = True

# Chỉ lỗi "di chuyển không được" (navigation/planning/execution)
MOVE_FAIL = {2,3,4,5,6,7, 8,9,10,11,12,13,14, 15,16,18, 701}

_poll_task = None
_armed = True          # fail_reason==0 -> True, lỗi hợp lệ -> trigger 1 lần rồi False
_lock = asyncio.Lock() # chống trigger chồng

def _pick_latest_move(moves):
    if not isinstance(moves, list) or not moves:
        return None
    return max(moves, key=lambda x: int(x.get("id", 0)))

async def poll_loop():
    global _armed
    log(f"[INFO] Polling moves: {MOVES_URL} every {POLL_INTERVAL}s")
    while True:
        try:
            def fetch():
                with urllib.request.urlopen(MOVES_URL, timeout=3) as resp:
                    raw = resp.read().decode("utf-8", errors="ignore")
                    return json.loads(raw)

            moves = await asyncio.to_thread(fetch)
            m = _pick_latest_move(moves)
            if m:
                state = (m.get("state") or "").strip()
                fr = int(m.get("fail_reason", 0))
                frs = m.get("fail_reason_str", "")
                fmsg = m.get("fail_message", "")

                # 1) về OK -> mở cờ để trigger lần sau
                if fr == 0:
                    if not _armed:
                        log("[INFO] fail_reason back to 0 -> re-armed")
                    _armed = True

                # 2) lỗi di chuyển hợp lệ -> trigger 1 lần/đợt
                elif _armed and fr in MOVE_FAIL and (not TRIGGER_ONLY_WHEN_CANCELLED or state == "cancelled"):
                    if not _lock.locked():
                        async with _lock:
                            ok, msg = recorder.trigger_event()
                            log(f"[TRIGGER-AUTO] state={state} fail_reason={fr} '{frs}' '{fmsg}' ok={ok} msg='{msg}'")
                    _armed = False

            await asyncio.sleep(POLL_INTERVAL)

        except asyncio.CancelledError:
            log("[INFO] Poll loop cancelled")
            raise
        except Exception as e:
            log(f"[WARN] poll error: {type(e).__name__}: {e}")
            await asyncio.sleep(1.0)

@asynccontextmanager
async def lifespan(app: FastAPI):
    global _poll_task

    camera.start_camera()
    recorder.start_sync_thread()

    # start poller
    _poll_task = asyncio.create_task(poll_loop())

    log("[INFO] FastAPI server started")
    log("[INFO] Camera thread started")
    log("[INFO] Sync thread started")
    log("[INFO] Poller started")

    try:
        yield
    finally:
        # stop poller
        if _poll_task:
            _poll_task.cancel()
            _poll_task = None
            log("[INFO] Poller stopped")

        recorder.stop_sync_thread()
        camera.stop_camera()

        log("[INFO] FastAPI server shutting down")
        log("[INFO] Camera thread stopped")
        log("[INFO] Sync thread stopped")

app = FastAPI(
    title="Camera Pre/Post Trigger Server",
    lifespan=lifespan,
)

# ==========================
# ROUTES
# ==========================
@app.get("/")
def root():
    return {"status": "running"}

# TRIGGER THanh cong  (manual)
@app.get("/trigger")
def http_trigger():
    ok, msg = recorder.trigger_event()
    log(f"[TRIGGER-MANUAL] ok={ok} msg='{msg}'")
    return {"success": ok, "message": msg}

@app.get("/logs")
def stream_logs():
    def event_generator():
        while True:
            msg = log_queue.get()
            yield f"data: {msg}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
    )

@app.get("/viewer", response_class=HTMLResponse)
def viewer():
    return """
<!DOCTYPE html>
<html>
<head>
  <title>Camera Log Viewer</title>
  <style>
    body { font-family: monospace; background:#111; color:#0f0; margin:0; padding:10px; }
    #log { white-space: pre-wrap; font-size:14px; }
  </style>
</head>
<body>
<h2>Camera Server Logs</h2>
<div id="log"></div>
<script>
  const logDiv = document.getElementById("log");
  const evtSource = new EventSource("/logs");
  evtSource.onmessage = function(e) {
    logDiv.textContent += e.data + "\\n";
    window.scrollTo(0, document.body.scrollHeight);
  };
</script>
</body>
</html>
"""
