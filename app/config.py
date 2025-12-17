# app/config.py
import cv2

# ==========================
# CONFIG
# ==========================
PRE_SECONDS = 10
POST_SECONDS = 20
FPS_TARGET = 24

# MP4V encoder
FOURCC = cv2.VideoWriter_fourcc(*"mp4v")
