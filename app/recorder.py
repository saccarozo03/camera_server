# app/recorder.py
import threading
import time
#import shutil
from pathlib import Path
from typing import Tuple, List, Any
from datetime import datetime


import cv2
from .samba_uploader import upload_file_to_samba

from .config import PRE_SECONDS, POST_SECONDS, FPS_TARGET, FOURCC
from .logging_utils import log
from .camera import (
    get_current_fps,
    get_latest_frame_raw,
    get_buffer_snapshot,
    get_items_after,
)

# LƯU TRÊN SSD (CHIA THEO NGÀY)
LOCAL_VIDEO_DIR = Path("/mnt/ssd/camera_videos")

# COPY LÊN WINDOWS SHARE
#REMOTE_ROOT_DIR = Path("/mnt/vision_new1")

LOCAL_VIDEO_DIR.mkdir(parents=True, exist_ok=True)

record_threads: List[threading.Thread] = []


def _upload_to_samba(local_path: Path):
    date_str = datetime.now().strftime("%Y-%m-%d")
    remote_path = f"{date_str}/{local_path.name}"

    try:
        upload_file_to_samba(local_path, remote_path)
        return True, f"Uploaded: {remote_path}"
    except Exception as e:
        return False, str(e)



def _decode_jpeg(enc: Any) -> Any:
    """
    enc là numpy 1D do cv2.imencode trả về
    """
    frame = cv2.imdecode(enc, cv2.IMREAD_COLOR)
    return frame


def _record_event(pre_items: List[Tuple[float, Any]], width: int, height: int, anchor_ts: float) -> None:
    """
    Ghi video:
      - PRE: theo pre_items (timestamp + jpeg) đã cắt theo anchor_ts
      - POST: drain theo timestamp từ anchor_ts đến anchor_ts + POST_SECONDS
    """
    fps = get_current_fps()
    if fps <= 0:
        fps = float(FPS_TARGET)

    timestamp = int(time.time())

    # ====== CHIA THƯ MỤC THEO NGÀY ======
    day_str = datetime.now().strftime("%Y-%m-%d")
    day_dir = LOCAL_VIDEO_DIR / day_str
    day_dir.mkdir(parents=True, exist_ok=True)

    local_path = day_dir / f"video_{timestamp}.mp4"

    writer = cv2.VideoWriter(str(local_path), FOURCC, fps, (width, height))
    if not writer.isOpened():
        log("[ERROR] Cannot create local video file")
        return

    log(f"[REC] Start recording local: {local_path} (fps={fps:.2f})")

    if pre_items:
        log(f"[REC] PRE count={len(pre_items)} span~{pre_items[-1][0] - pre_items[0][0]:.2f}s")

    # ===== PRE =====
    for _, enc in pre_items:
        fr = _decode_jpeg(enc)
        if fr is None:
            continue
        if fr.shape[1] != width or fr.shape[0] != height:
            fr = cv2.resize(fr, (width, height))
        writer.write(fr)

    # ===== POST (drain theo timestamp) =====
    end_ts = anchor_ts + POST_SECONDS
    last_written_ts = anchor_ts

    log(f"[REC] POST drain from {anchor_ts:.3f} to {end_ts:.3f}")

    idle = 0
    while last_written_ts < end_ts:
        new_items = get_items_after(last_written_ts)

        if new_items:
            for ts, enc in new_items:
                if ts > end_ts:
                    last_written_ts = end_ts
                    break

                fr = _decode_jpeg(enc)
                if fr is None:
                    continue

                if fr.shape[1] != width or fr.shape[0] != height:
                    fr = cv2.resize(fr, (width, height))

                writer.write(fr)
                last_written_ts = ts

            idle = 0
        else:
            idle += 1
            time.sleep(0.003)

            if idle % 500 == 0:
                remain = end_ts - last_written_ts
                log(f"[REC][WARN] No new frames yet. remain~{remain:.2f}s")

    writer.release()
    log(f"[REC] Done recording local: {local_path}")

    ok, msg = _upload_to_samba(local_path)

    if ok:
        log(f"[UPLOAD] {msg}")
    else:
        log(f"[UPLOAD][ERROR] {msg}")


def trigger_event() -> Tuple[bool, str]:
    """
    Trigger:
      - anchor_ts = timestamp của frame mới nhất trong buffer
      - PRE cắt theo anchor_ts
      - POST drain (không hụt giây)
    """
    buf = get_buffer_snapshot()
    if not buf:
        return False, "Buffer is empty"

    anchor_ts = buf[-1][0]

    if (anchor_ts - buf[0][0]) < PRE_SECONDS:
        return False, "Buffer not full yet"

    pre_items = [(ts, enc) for (ts, enc) in buf if (anchor_ts - PRE_SECONDS) <= ts <= anchor_ts]

    lf = get_latest_frame_raw()
    if lf is not None:
        h, w = lf.shape[:2]
    else:
        fr = _decode_jpeg(buf[-1][1])
        if fr is None:
            return False, "Cannot decode frame"
        h, w = fr.shape[:2]

    log(f"[TRIGGER] anchor_ts={anchor_ts:.3f}, pre_count={len(pre_items)}")

    t = threading.Thread(
        target=_record_event,
        args=(pre_items, w, h, anchor_ts),
        daemon=False,
    )
    t.start()
    record_threads.append(t)

    log("[TRIGGER] Recording triggered")
    return True, "Recording started"
