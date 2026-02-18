# app/recorder.py
import threading
import time
import shutil
import os
from pathlib import Path
from typing import Tuple, List, Any, Optional
from datetime import datetime, timedelta

import cv2

from .config import (
	FPS_TARGET,
	LOCAL_VIDEO_DIR,
	POST_SECONDS,
	PRE_SECONDS,
	REMOTE_ROOT_DIR,
	SYNC_INTERVAL_SEC,
	SYNC_SCAN_DAYS_BACK,
	SYNC_SKIP_RECENT_FILE_SEC,
	VIDEO_FILE_EXTENSION,
	VIDEO_FILENAME_PREFIX,
	VIDEO_FOURCC,
)
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
LOCAL_VIDEO_DIR.mkdir(parents=True, exist_ok=True)

record_threads: List[threading.Thread] = []

# ==========================================================
# [MINIMAL FIX] SYNC THREAD CONTROL
# (KHONG start thread khi import module nua)
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
	Windows Share phai duoc mount that va co quyen ghi.
	Tranh truong hop folder local ton tai nhung mount da rot.
	"""
	p = str(REMOTE_ROOT_DIR)
	return os.path.ismount(p) and os.access(p, os.W_OK)


def sync_pending_videos(days_back: int = SYNC_SCAN_DAYS_BACK) -> None:
	"""
	Chi dong bo cac video trong N ngay gan nhat (mac dinh 1 ngay gan nhat).
	days_back=1 -> quet hom nay va hom qua (buffer an toan).
	"""
	if not check_network():
		return

	# Danh sach folder ngay can quet: hom nay va lui N ngay
	targets: List[Path] = []
	for i in range(days_back + 1):  # +1 de gom ca hom nay
		day_str = (datetime.now() - timedelta(days=i)).strftime("%Y-%m-%d")
		day_dir = LOCAL_VIDEO_DIR / day_str
		if day_dir.exists():
			targets.append(day_dir)

	for day_dir in targets:
		for local_file in day_dir.rglob(f"*.{VIDEO_FILE_EXTENSION}"):
			# Skip file vua ghi xong (tranh copy khi file chua "on dinh")
			try:
				if time.time() - local_file.stat().st_mtime < SYNC_SKIP_RECENT_FILE_SEC:
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
	"""Luong chay ngam: sync theo chu ky cau hinh, co the stop bang Event."""
	while not _sync_stop.is_set():
		try:
			sync_pending_videos()
		except Exception as e:
			log(f"[SYNC][CRITICAL] Worker error: {e}")
		_sync_stop.wait(SYNC_INTERVAL_SEC)


def _copy_to_share(local_path: Path) -> Tuple[bool, str]:
	"""
	Thu copy file ngay lap tuc. Neu loi hoac offline -> background sync se xu ly sau.
	"""
	if not check_network():
		return False, "Network is offline. File saved to SSD and queued for sync."

	# Lay thu muc ngay tu chinh file local (vi du: 2026-02-03)
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
	"""enc la numpy 1D do cv2.imencode tra ve"""
	return cv2.imdecode(enc, cv2.IMREAD_COLOR)


def _record_event(pre_items: List[Tuple[float, Any]], width: int, height: int, anchor_ts: float) -> None:
	fps = get_current_fps()
	if fps <= 0:
		fps = float(FPS_TARGET)

	timestamp = int(time.time())

	# ====== CHIA THU MUC THEO NGAY ======
	day_str = datetime.now().strftime("%Y-%m-%d")
	day_dir = LOCAL_VIDEO_DIR / day_str
	day_dir.mkdir(parents=True, exist_ok=True)

	local_path = day_dir / f"{VIDEO_FILENAME_PREFIX}_{timestamp}.{VIDEO_FILE_EXTENSION}"

	writer = cv2.VideoWriter(str(local_path), VIDEO_FOURCC, fps, (width, height))
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

	# Thu upload ngay
	ok, msg = _copy_to_share(local_path)
	if ok:
		log(f"[UPLOAD][OK] {msg}")
	else:
		log(f"[UPLOAD][PENDING] {msg}")


def trigger_event() -> Tuple[bool, str]:
	"""
	Trigger:
	  - anchor_ts = timestamp cua frame moi nhat trong buffer
	  - PRE cat theo anchor_ts
	  - POST drain (khong hut giay)
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
