# app/recorder.py
import threading
import time
import shutil
from pathlib import Path
from typing import Tuple
from datetime import datetime

import cv2

from .config import PRE_SECONDS, POST_SECONDS, FPS_TARGET, FOURCC
from .logging_utils import log
from .camera import get_latest_frame_and_buffer

# =========================
# PATH CONFIG
# =========================
# Ghi video local trước
LOCAL_VIDEO_DIR = Path("/data/videos")

# Windows share đã mount:
# //10.20.31.46/Denso.25.007 -> /mnt/denso
REMOTE_ROOT_DIR = Path("/mnt/denso247")

LOCAL_VIDEO_DIR.mkdir(parents=True, exist_ok=True)

record_threads = []


def _copy_to_share(local_path: Path, max_retry: int = 3, retry_sleep: float = 2.0) -> Tuple[bool, str]:
    """
    Copy file local sang Windows share, tổ chức theo thư mục ngày (YYYY-MM-DD).
    """
    # Lấy ngày hiện tại
    date_str = datetime.now().strftime("%Y-%m-%d")

    # Thư mục đích theo ngày
    remote_day_dir = REMOTE_ROOT_DIR / date_str

    try:
        # Tạo thư mục ngày nếu chưa có
        remote_day_dir.mkdir(parents=True, exist_ok=True)
    except Exception as e:
        return False, f"Cannot create remote day directory {remote_day_dir}: {e}"

    remote_path = remote_day_dir / local_path.name

    last_err = ""
    for attempt in range(1, max_retry + 1):
        try:
            shutil.copy2(local_path, remote_path)
            return True, f"Copied to {remote_path}"
        except Exception as e:
            last_err = str(e)
            log(f"[UPLOAD][RETRY {attempt}/{max_retry}] {last_err}")
            time.sleep(retry_sleep)

    return False, f"Copy failed after {max_retry} retries: {last_err}"


def _record_event(pre_frames, width: int, height: int) -> None:
    """
    Ghi video gồm pre_frames + POST_SECONDS từ latest_frame.
    Luồng:
      1) Ghi local /data/videos
      2) Ghi xong -> copy sang /mnt/denso/YYYY-MM-DD/
    """
    timestamp = int(time.time())
    local_path = LOCAL_VIDEO_DIR / f"video_{timestamp}.mp4"

    writer = cv2.VideoWriter(
        str(local_path),
        FOURCC,
        FPS_TARGET,
        (width, height)
    )

    if not writer.isOpened():
        log("[ERROR] Cannot create local video file")
        return

    log(f"[REC] Start recording local: {local_path}")

    # ----- PRE -----
    for f in pre_frames:
        writer.write(f)

    # ----- POST -----
    frames_needed = int(POST_SECONDS * FPS_TARGET)
    sleep_time = 1.0 / FPS_TARGET

    for _ in range(frames_needed):
        latest_frame, _ = get_latest_frame_and_buffer()
        if latest_frame is not None:
            writer.write(latest_frame.copy())
        time.sleep(sleep_time)

    writer.release()
    log(f"[REC] Done recording local: {local_path}")

    # ----- COPY TO WINDOWS SHARE -----
    ok, msg = _copy_to_share(local_path, max_retry=3, retry_sleep=2.0)
    if ok:
        log(f"[UPLOAD] {msg}")

        # (Tuỳ chọn) Xoá file local sau khi copy thành công
        # try:
        #     local_path.unlink(missing_ok=True)
        #     log(f"[CLEANUP] Removed local file: {local_path}")
        # except Exception as e:
        #     log(f"[CLEANUP][WARN] {e}")
    else:
        log(f"[UPLOAD][ERROR] {msg}")


def trigger_event() -> Tuple[bool, str]:
    """
    Gọi từ API trigger.
    """
    latest_frame, pre_frames = get_latest_frame_and_buffer()

    if latest_frame is None:
        return False, "Camera not ready"

    if len(pre_frames) < int(PRE_SECONDS * FPS_TARGET):
        return False, "Buffer not full yet"

    h, w = latest_frame.shape[:2]

    t = threading.Thread(
        target=_record_event,
        args=(pre_frames, w, h),
        daemon=False
    )
    t.start()
    record_threads.append(t)

    log("[TRIGGER] Recording triggered")
    return True, "Recording started"
