# app/recorder.py
import threading
import time
from typing import Tuple

import cv2

from .config import PRE_SECONDS, POST_SECONDS, FPS_TARGET, FOURCC
from .logging_utils import log
from .camera import get_latest_frame_and_buffer

record_threads = []  # chỉ để giữ reference, tránh bị GC nếu bạn muốn quản lý thêm


def _record_event(pre_frames, width: int, height: int) -> None:
    #Ghi video gồm pre_frames + POST_SECONDS từ latest_frame.
    timestamp = int(time.time())
    filename = f"video_{timestamp}.mp4"

    writer = cv2.VideoWriter(filename, FOURCC, FPS_TARGET, (width, height))
    if not writer.isOpened():
        log("[ERROR] Cannot create video file")
        return

    log(f"[REC] Start recording: {filename}")

    # ----- PRE -----
    for f in pre_frames:
        writer.write(f)

    # ----- POST -----
    frames_needed = POST_SECONDS * FPS_TARGET
    sleep_time = 1.0 / FPS_TARGET

    for _ in range(frames_needed):
        latest_frame, _ = get_latest_frame_and_buffer()
        if latest_frame is not None:
            writer.write(latest_frame.copy())
        time.sleep(sleep_time)

    writer.release()
    log(f"[REC] Done recording: {filename}")


def trigger_event() -> Tuple[bool, str]:
    
    # Gọi hàm này từ API để bắt đầu ghi:
    # Check camera ready
    # Check buffer đủ PRE_SECONDS
    # Spawn thread ghi _record_event
    
    latest_frame, pre_frames = get_latest_frame_and_buffer()

    if latest_frame is None:
        return False, "Camera not ready"

    if len(pre_frames) < PRE_SECONDS * FPS_TARGET:
        return False, "Buffer not full yet"

    h, w = latest_frame.shape[:2]

    t = threading.Thread(
        target=_record_event,
        args=(pre_frames, w, h),
        daemon=False,  # có thể để False để đảm bảo ghi xong file
    )
    t.start()
    record_threads.append(t)

    log("[TRIGGER] Recording triggered")
    return True, "Recording started"
