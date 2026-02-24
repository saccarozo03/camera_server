import cv2
from pathlib import Path

# ==========================
# RECORD WINDOW
# ==========================
PRE_SECONDS = 10
POST_SECONDS = 20

# ==========================
# CAMERA INPUT CONFIG
# ==========================
CAMERA_DEVICE_INDEX = 0
CAMERA_BACKEND = cv2.CAP_FFMPEG
CAMERA_CODEC = "MJPG"
CAMERA_ENABLE_DRIVER_BUFFER_TUNING = True
CAMERA_DRIVER_BUFFER_SIZE = 1

# RTSP URL cho camera Hikvision
CAMERA_SOURCE = "rtsp://admin:Rtc%401234@192.168.0.69:554/Streaming/Channels/101"

# ==========================
# CAMERA FRAME CONFIG
# ==========================
FPS_TARGET = 25
FRAME_WIDTH = 1280
FRAME_HEIGHT = 720
FPS_LOG_INTERVAL_SEC = 15.0

# ==========================
# JPEG BUFFER CONFIG
# ==========================
JPEG_QUALITY = 100
JPEG_ENCODE_EXT = ".jpg"

# Buffer headroom:
# du lon de trong luc recorder dang ghi PRE thi POST van khong bi overwrite.
BUFFER_SECONDS_HEADROOM = PRE_SECONDS + POST_SECONDS + 15


def get_buffer_maxlen() -> int:
	return int(BUFFER_SECONDS_HEADROOM * FPS_TARGET)


# ==========================
# VIDEO WRITER CONFIG
# ==========================
VIDEO_FILE_EXTENSION = "mp4"
VIDEO_FILENAME_PREFIX = "video"
VIDEO_FOURCC = cv2.VideoWriter_fourcc(*"mp4v")

# ==========================
# STORAGE / SYNC CONFIG
# ==========================
# --- Linux ---
LOCAL_VIDEO_DIR = Path("/mnt/ssd/camera_videos")
REMOTE_ROOT_DIR = Path("/mnt/vision_new1")

# --- Windows ---
# LOCAL_VIDEO_DIR = Path("D:/RTC_PROJECT/Denso.25.007/video")
# REMOTE_ROOT_DIR = Path("D:/RTC_PROJECT/Denso.25.007/video_remote")
SYNC_INTERVAL_SEC = 60
SYNC_SCAN_DAYS_BACK = 1
SYNC_SKIP_RECENT_FILE_SEC = 3

# ==========================
# AUTO-TRIGGER POLLER CONFIG
# ==========================
MOVES_URL = "http://saccarozo04-ThinkBook-16-G8-IRL.local:8090/chassis/moves"
POLL_INTERVAL_SEC = 0.5
POLL_REQUEST_TIMEOUT_SEC = 3
POLL_ERROR_RETRY_DELAY_SEC = 1.0
TRIGGER_ONLY_WHEN_CANCELLED = True
MOVE_FAIL_REASONS = {
	2,
	3,
	4,
	5,
	6,
	7,
	8,
	9,
	10,
	11,
	12,
	13,
	14,
	15,
	16,
	18,
	701,
}
