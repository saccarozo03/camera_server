# app/api.py
from fastapi import FastAPI
from contextlib import asynccontextmanager
from fastapi.responses import StreamingResponse, HTMLResponse

from .logging_utils import log_queue, log
from . import recorder, camera

@asynccontextmanager
async def lifespan(app: FastAPI):
  # Start camera when the app starts
  camera.start_camera()
  log("[INFO] FastAPI server started, camera thread started")
  try:
    yield
  finally:
    # Stop camera when the app shuts down
    camera.stop_camera()
    log("[INFO] FastAPI server shutting down, camera thread stopped")


app = FastAPI(title="Camera Pre/Post Trigger Server", lifespan=lifespan)


# ==========================
# ROUTES
# ==========================
@app.get("/")
def root():
    return {"status": "running"}


@app.get("/trigger")
def http_trigger():
    ok, msg = recorder.trigger_event()
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
    body {
      font-family: monospace;
      background: #111;
      color: #0f0;
      margin: 0;
      padding: 10px;
    }
    #log {
      white-space: pre-wrap;
      font-size: 14px;
    }
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
