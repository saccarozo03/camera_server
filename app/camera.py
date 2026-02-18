# app/camera.py
import threading
import time
from collections import deque
from typing import Deque, List, Tuple, Optional, Any

import cv2

from .config import (
	CAMERA_BACKEND,
	CAMERA_CODEC,
	CAMERA_DEVICE_INDEX,
	CAMERA_DRIVER_BUFFER_SIZE,
	CAMERA_ENABLE_DRIVER_BUFFER_TUNING,
	FPS_LOG_INTERVAL_SEC,
	FPS_TARGET,
	FRAME_HEIGHT,
	FRAME_WIDTH,
	JPEG_ENCODE_EXT,
	JPEG_QUALITY,
	get_buffer_maxlen,
)
from .logging_utils import log

# ======================================================
# BUFFER: luu (timestamp, jpeg_bytes_as_numpy_1d)
# ======================================================
# Buffer du lon de giu pre + phan post phat sinh trong luc dang ghi pre
# Dung FPS_TARGET de tinh upper bound; thuc te fps thap hon thi cang an toan
MAXLEN = get_buffer_maxlen()

buffer: Deque[Tuple[float, Any]] = deque(maxlen=MAXLEN)

frame_lock = threading.Lock()

# latest_frame_raw chi phuc vu preview/do kich thuoc, khong nhet vao buffer
latest_frame_raw: Optional[Any] = None

running = False
_camera_thread: Optional[threading.Thread] = None

# FPS thuc te do duoc
current_fps: float = float(FPS_TARGET)

# JPEG encode params
ENCODE_PARAMS = [int(cv2.IMWRITE_JPEG_QUALITY), int(JPEG_QUALITY)]



def _camera_loop() -> None:
	global latest_frame_raw, running, current_fps

	cap = cv2.VideoCapture(CAMERA_DEVICE_INDEX, CAMERA_BACKEND)

	# Giam latency neu driver ho tro
	if CAMERA_ENABLE_DRIVER_BUFFER_TUNING:
		try:
			cap.set(cv2.CAP_PROP_BUFFERSIZE, CAMERA_DRIVER_BUFFER_SIZE)
		except Exception:
			pass

	# Ep MJPG + resolution + FPS
	camera_fourcc = cv2.VideoWriter_fourcc(*CAMERA_CODEC)
	cap.set(cv2.CAP_PROP_FOURCC, camera_fourcc)
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

		# Encode JPEG de giam RAM
		ok, enc = cv2.imencode(JPEG_ENCODE_EXT, frame, ENCODE_PARAMS)
		if not ok:
			continue

		with frame_lock:
			latest_frame_raw = frame
			buffer.append((ts, enc))  # enc la numpy 1D (bytes)

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
	"""Frame raw (BGR) chi de preview / lay kich thuoc."""
	with frame_lock:
		return None if latest_frame_raw is None else latest_frame_raw.copy()


def get_buffer_snapshot() -> List[Tuple[float, Any]]:
	"""Snapshot buffer (shallow) - khong copy noi dung JPEG de giam CPU."""
	with frame_lock:
		return list(buffer)


def get_items_after(ts: float) -> List[Tuple[float, Any]]:
	"""
	Tra ve cac item (t, jpeg) co t > ts.
	Dung cho recorder drain theo timestamp, tranh thieu giay sau trigger.
	"""
	with frame_lock:
		return [(t, enc) for (t, enc) in buffer if t > ts]
