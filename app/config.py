# app/config.py
import cv2

# ==========================
# CONFIG
# ==========================
PRE_SECONDS = 10
POST_SECONDS = 20

# FPS mục tiêu để set cho camera; FPS thực tế sẽ đo lại (thường ~21 với webcam của bạn)
FPS_TARGET = 30

# Độ phân giải capture
FRAME_WIDTH = 1280
FRAME_HEIGHT = 720

# Encoder MP4
FOURCC = cv2.VideoWriter_fourcc(*"mp4v")

# JPEG buffer settings (giảm RAM)
JPEG_QUALITY = 80

# Buffer headroom:
# cần lớn để trong lúc recorder đang ghi PRE (mất vài giây) thì POST vẫn không bị overwrite
# Ví dụ: giữ ~ (PRE + POST + 15) giây theo FPS_TARGET
BUFFER_SECONDS_HEADROOM = PRE_SECONDS + POST_SECONDS + 15
