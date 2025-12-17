# app/camera.py : Quản lý camera và buffer khung hình
import threading
from collections import deque
from typing import List, Tuple, Optional

import cv2

from .config import PRE_SECONDS, FPS_TARGET
from .logging_utils import log

# ==========================
# SHARED STATE CỦA CAMERA
# ==========================
buffer = deque(maxlen=PRE_SECONDS * FPS_TARGET)
frame_lock = threading.Lock()
latest_frame = None  # kiểu: Optional[np.ndarray]
running = False
_camera_thread: Optional[threading.Thread] = None


def _camera_loop() -> None:
    #Vòng lặp chính đọc frame từ camera và đẩy vào buffer.
    global latest_frame, running

    cap = cv2.VideoCapture(0)
    if not cap.isOpened():
        log("[ERROR] Cannot open camera")
        running = False
        return

    log("[CAM] Camera started")

    while running:
        ret, frame = cap.read()
        if not ret:
            continue

        with frame_lock:
            latest_frame = frame.copy()
            buffer.append(frame.copy())

    cap.release()
    log("[CAM] Camera stopped")


def start_camera() -> None:
    #Khởi động thread camera nếu chưa chạy.
    global running, _camera_thread
    if running:
        return

    running = True
    _camera_thread = threading.Thread(target=_camera_loop, daemon=True)
    _camera_thread.start()


def stop_camera() -> None:
    #Dừng thread camera một cách an toàn.
    global running, _camera_thread
    running = False
    if _camera_thread is not None:
        _camera_thread.join(timeout=2.0)
        _camera_thread = None


def get_latest_frame_and_buffer() -> Tuple[Optional["any"], List["any"]]:
    
    #Lấy bản copy của latest_frame và list copy của buffer.
    #Trả về (latest_frame, pre_frames).
    
    with frame_lock:
        lf = None if latest_frame is None else latest_frame.copy()
        pre_copy = list(buffer)
    return lf, pre_copy
