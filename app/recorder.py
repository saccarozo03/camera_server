# app/recorder.py
import threading
import time
import shutil
import os
from pathlib import Path
from typing import Tuple, List, Any, Optional
from datetime import datetime , timedelta

import cv2

from .config import PRE_SECONDS, POST_SECONDS, FPS_TARGET, FOURCC
from .logging_utils import log
from .camera import (
    get_current_fps,
    get_latest_frame_raw,
    get_buffer_snapshot,
    get_items_after,
)

# ==========================================================
# PATHS
# ==========================================================
# Luu TReN SSD (CHIA THEO NgaY)
LOCAL_VIDEO_DIR = Path("/mnt/ssd/camera_videos")

# WINDOWS SHARE (PHẢI MOUNT VÀO ĐÂY)
REMOTE_ROOT_DIR = Path("/mnt/vision_new")

LOCAL_VIDEO_DIR.mkdir(parents=True, exist_ok=True)

record_threads: List[threading.Thread] = []

# ==========================================================
# [MINIMAL FIX] SYNC THREAD CONTROL
# (KHÔNG start thread khi import module nữa)
# ==========================================================
_sync_stop = threading.Event()
_sync_thread: Optional[threading.Thread] = None


def start_sync_thread() -> None:
    """Call from FastAPI lifespan when app starts."""
    global _sync_thread
    if _sync_thread is not None and _sync_thread.is_alive():
        return
    _sync_stop.clear()
    _sync_thread = threading.Thread(target=_background_sync_worker, daemon=True)
    _sync_thread.start()
    log("[SYNC] Background sync thread started")


def stop_sync_thread() -> None:
    """Call from FastAPI lifespan when app stops."""
    _sync_stop.set()
    log("[SYNC] Background sync thread stop requested")


# ==========================================================
# OFFLINE-FIRST SYNC
# ==========================================================
def check_network() -> bool:
    """
    Windows Share phải được mount thật và có quyền ghi.
    Tránh trường hợp folder local tồn tại nhưng mount đã rớt.
    """
    p = str(REMOTE_ROOT_DIR)
    return os.path.ismount(p) and os.access(p, os.W_OK)


#def sync_pending_videos() -> None:
    """
    Quét SSD tìm các file chưa upload hoặc upload lỗi và đẩy lên Server.
    (Minimal) - vẫn dùng rglob, nhưng skip file mới ghi (<3s).
    """
    #if not check_network():
       # return

   # for local_file in LOCAL_VIDEO_DIR.rglob("*.mp4"):
        # Skip file vừa ghi xong để tránh copy khi file chưa "ổn định"
       # try:
           # if time.time() - local_file.stat().st_mtime < 3:
               # continue
       # except Exception:
           # continue

        #try:
            # Ví dụ: local_file = /mnt/ssd/camera_videos/2026-02-03/video_123.mp4
            # relative_path = 2026-02-03/video_123.mp4
           # relative_path = local_file.relative_to(LOCAL_VIDEO_DIR)
           # remote_path = REMOTE_ROOT_DIR / relative_path

            # Nếu file chưa tồn tại trên remote hoặc size khác nhau -> copy lại
           # if (not remote_path.exists()) or (remote_path.stat().st_size != local_file.stat().st_size):
                #remote_path.parent.mkdir(parents=True, exist_ok=True)

                #log(f"[SYNC] Uploading: {relative_path}")
                #shutil.copy2(local_file, remote_path)
                #log(f"[SYNC] Done: {relative_path}")

        #except Exception as e:
           # log(f"[SYNC][ERROR] {local_file.name}: {e}")
def sync_pending_videos(days_back: int = 1) -> None:
    """
    Chỉ đồng bộ các video trong N ngày gần nhất (mặc định 1 ngày gần nhất).
    days_back=1 -> quét hôm nay và hôm qua (buffer an toàn).
    """
    if not check_network():
        return

    # Danh sách folder ngày cần quét: hôm nay và lùi N ngày
    targets: List[Path] = []
    for i in range(days_back + 1):  # +1 để gồm cả hôm nay
        day_str = (datetime.now() - timedelta(days=i)).strftime("%Y-%m-%d")
        day_dir = LOCAL_VIDEO_DIR / day_str
        if day_dir.exists():
            targets.append(day_dir)

    for day_dir in targets:
        for local_file in day_dir.rglob("*.mp4"):
            # Skip file vừa ghi xong (tránh copy khi file chưa "ổn định")
            try:
                if time.time() - local_file.stat().st_mtime < 3:
                    continue
            except Exception:
                continue

            try:
                relative_path = local_file.relative_to(LOCAL_VIDEO_DIR)
                remote_path = REMOTE_ROOT_DIR / relative_path

                if (not remote_path.exists()) or (remote_path.stat().st_size != local_file.stat().st_size):
                    remote_path.parent.mkdir(parents=True, exist_ok=True)
                    log(f"[SYNC] Uploading: {relative_path}")
                    shutil.copy2(local_file, remote_path)
                    log(f"[SYNC] Done: {relative_path}")

            except Exception as e:
                log(f"[SYNC][ERROR] {local_file.name}: {e}")


def _background_sync_worker() -> None:
    """Luồng chạy ngầm: mỗi 60s sync 1 lần, có thể stop bằng Event."""
    while not _sync_stop.is_set():
        try:
            sync_pending_videos()
        except Exception as e:
            log(f"[SYNC][CRITICAL] Worker error: {e}")
        _sync_stop.wait(60)


def _copy_to_share(local_path: Path) -> Tuple[bool, str]:
    """
    Thử copy file ngay lập tức. Nếu lỗi hoặc offline -> background sync sẽ xử lý sau.
    """
    if not check_network():
        return False, "Network is offline. File saved to SSD and queued for sync."

    # Lấy thư mục ngày từ chính file local (ví dụ: 2026-02-03)
    date_str = local_path.parent.name
    remote_day_dir = REMOTE_ROOT_DIR / date_str
    remote_path = remote_day_dir / local_path.name

    try:
        remote_day_dir.mkdir(parents=True, exist_ok=True)
        shutil.copy2(local_path, remote_path)
        return True, f"Copied to {remote_path}"
    except Exception as e:
        return False, f"Immediate upload failed ({e}). Queued for retry."


# ==========================================================
# RECORD LOGIC
# ==========================================================
def _decode_jpeg(enc: Any) -> Any:
    """enc là numpy 1D do cv2.imencode trả về"""
    return cv2.imdecode(enc, cv2.IMREAD_COLOR)


def _record_event(pre_items: List[Tuple[float, Any]], width: int, height: int, anchor_ts: float) -> None:
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
    log(f"[REC] Done local: {local_path}")

    # Thử upload ngay
    ok, msg = _copy_to_share(local_path)
    if ok:
        log(f"[UPLOAD][OK] {msg}")
    else:
        log(f"[UPLOAD][PENDING] {msg}")


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
