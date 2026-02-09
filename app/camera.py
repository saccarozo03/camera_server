# app/camera.py
import threading
import time
from collections import deque
from typing import Deque, List, Tuple, Optional, Any

import cv2

from .config import (
    PRE_SECONDS,
    POST_SECONDS,
    FPS_TARGET,
    FRAME_WIDTH,
    FRAME_HEIGHT,
    JPEG_QUALITY,
    BUFFER_SECONDS_HEADROOM,
)
from .logging_utils import log

# ======================================================
# BUFFER: lưu (timestamp, jpeg_bytes_as_numpy_1d)
# ======================================================
# Buffer đủ lớn để giữ pre + phần post phát sinh trong lúc đang ghi pre
# Dùng FPS_TARGET để tính upper bound; thực tế fps thấp hơn thì càng an toàn
MAXLEN = int(BUFFER_SECONDS_HEADROOM * FPS_TARGET)

buffer: Deque[Tuple[float, Any]] = deque(maxlen=MAXLEN)

frame_lock = threading.Lock()

# latest_frame_raw chỉ phục vụ preview/đo kích thước, không nhét vào buffer
latest_frame_raw: Optional[Any] = None

running = False
_camera_thread: Optional[threading.Thread] = None

# FPS thực tế đo được
current_fps: float = float(FPS_TARGET)

# JPEG encode params
ENCODE_PARAMS = [int(cv2.IMWRITE_JPEG_QUALITY), int(JPEG_QUALITY)]

FPS_LOG_INTERVAL_SEC = 15.0


def _camera_loop() -> None:
    global latest_frame_raw, running, current_fps

    cap = cv2.VideoCapture(0, cv2.CAP_V4L2)

    # Giảm latency nếu driver hỗ trợ
    try:
        cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
    except Exception:
        pass

    # Ép MJPG + resolution + FPS
    mjpg_fourcc = cv2.VideoWriter_fourcc(*"MJPG")
    cap.set(cv2.CAP_PROP_FOURCC, mjpg_fourcc)
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, FRAME_WIDTH)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, FRAME_HEIGHT)
    cap.set(cv2.CAP_PROP_FPS, FPS_TARGET)

    if not cap.isOpened():
        log("[ERROR] Cannot open camera")
        running = False
        return

    actual_w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    actual_h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    actual_fps = cap.get(cv2.CAP_PROP_FPS)
    log(
        f"[CAM] Requested {FRAME_WIDTH}x{FRAME_HEIGHT}@{FPS_TARGET}, "
        f"actual {actual_w}x{actual_h}@{actual_fps:.2f}, buffer_maxlen={MAXLEN}"
    )
    log("[CAM] Camera started")

    frame_count = 0
    t_start = time.time()

    while running:
        ret, frame = cap.read()
        if not ret:
            continue

        # Ensure size
        if frame.shape[1] != FRAME_WIDTH or frame.shape[0] != FRAME_HEIGHT:
            frame = cv2.resize(frame, (FRAME_WIDTH, FRAME_HEIGHT))

        ts = time.time()

        # Encode JPEG để giảm RAM
        ok, enc = cv2.imencode(".jpg", frame, ENCODE_PARAMS)
        if not ok:
            continue

        with frame_lock:
            latest_frame_raw = frame
            buffer.append((ts, enc))  # enc là numpy 1D (bytes)

        frame_count += 1
        if frame_count >= int(FPS_TARGET * FPS_LOG_INTERVAL_SEC):
            elapsed = time.time() - t_start
            if elapsed > 0:
                current_fps = frame_count / elapsed
                log(f"[CAM] Measured FPS ~ {current_fps:.2f}")
            frame_count = 0
            t_start = time.time()

    cap.release()
    log("[CAM] Camera stopped")


def start_camera() -> None:
    global running, _camera_thread
    if running:
        return
    running = True
    _camera_thread = threading.Thread(target=_camera_loop, daemon=True)
    _camera_thread.start()


def stop_camera() -> None:
    global running, _camera_thread
    running = False
    if _camera_thread is not None:
        _camera_thread.join(timeout=2.0)
        _camera_thread = None


def get_current_fps() -> float:
    return current_fps


def get_latest_frame_raw() -> Optional[Any]:
    """Frame raw (BGR) chỉ để preview / lấy kích thước."""
    with frame_lock:
        return None if latest_frame_raw is None else latest_frame_raw.copy()


def get_buffer_snapshot() -> List[Tuple[float, Any]]:
    """Snapshot buffer (shallow) - không copy nội dung JPEG để giảm CPU."""
    with frame_lock:
        return list(buffer)


def get_items_after(ts: float) -> List[Tuple[float, Any]]:
    """
    Trả về các item (t, jpeg) có t > ts.
    Dùng cho recorder drain theo timestamp, tránh thiếu giây sau trigger.
    """
    with frame_lock:
        return [(t, enc) for (t, enc) in buffer if t > ts]
