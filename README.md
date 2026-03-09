# Camera Pre/Post Trigger Server

Server camera nhẹ dựa trên **FastAPI**, quản lý luồng camera liên tục và ghi lại các **clip video trước/sau sự kiện (pre/post trigger)**.

Hệ thống được tối ưu cho **thiết bị nhúng / edge device** (Raspberry Pi, RockPi, PC công nghiệp) và hỗ trợ **kích hoạt qua HTTP**, **ghi hình nền**, **tự động trigger từ AGV**, và **stream log thời gian thực** qua **Server-Sent Events (SSE)**.

---

## Kiến trúc hệ thống

```
┌─────────────────────────┐
│   Client / AGV / App    │
└────────────┬────────────┘
             │  HTTP Trigger / AGV Poller
             ▼
┌────────────────────────────┐
│      FastAPI Server        │
│    (main.py / api.py)      │
└────────────┬───────────────┘
             │  Lifespan
             ▼
┌────────────────────────────┐
│      Camera Thread         │
│    (OpenCV / RTSP)         │
└────────────┬───────────────┘
             │  Frame Buffer (JPEG)
             ▼
┌────────────────────────────┐
│   Recorder Thread          │
│  (Pre + Post Buffer)       │
└────────────┬───────────────┘
             │
             ▼
┌────────────────────────────┐
│   Video Clips (.mp4)       │
│   + Sync to Remote         │
└────────────────────────────┘
```

---

## Tính năng

- Vòng đời camera được quản lý bởi FastAPI lifespan (tự động start/stop)
- Ghi hình pre-trigger và post-trigger vào file `.mp4`
- Buffer frame bằng JPEG in-memory, không ghi tạm ra disk
- Luồng ghi hình chạy nền, không chặn API
- Hỗ trợ camera USB (OpenCV) và camera IP/RTSP (Hikvision, v.v.)
- Endpoint HTTP để kích hoạt thủ công (`/trigger`)
- **Auto-trigger**: tự động kích hoạt khi AGV báo lỗi di chuyển
- Stream log thời gian thực qua SSE (`/logs`)
- Giao diện web xem log đơn giản (`/viewer`)
- Logging thread-safe bằng `queue.Queue`
- Đồng bộ video sang ổ đĩa/NAS từ xa theo định kỳ
- Phù hợp với thiết bị headless và triển khai qua `systemd`

---

## Cấu trúc dự án

```
camera_server/
├── app/
│   ├── api.py           # FastAPI routes, lifespan, auto-trigger poller
│   ├── camera.py        # Luồng capture camera (OpenCV / RTSP)
│   ├── recorder.py      # Luồng ghi hình nền (pre/post buffer)
│   ├── logging_utils.py # Logging thread-safe và SSE
│   └── config.py        # Tất cả tham số cấu hình
├── main.py              # Entry point (uvicorn)
├── requirements.txt
└── README.md
```

---

## Cấu hình (`app/config.py`)

Tất cả tham số quan trọng được tập trung tại `app/config.py`:

| Nhóm | Tham số | Mô tả |
|---|---|---|
| **Cửa sổ ghi** | `PRE_SECONDS`, `POST_SECONDS` | Số giây ghi trước/sau trigger |
| **Camera input** | `CAMERA_SOURCE` | URL RTSP hoặc index thiết bị USB |
| | `CAMERA_BACKEND`, `CAMERA_CODEC` | Backend và codec OpenCV |
| **Frame** | `FPS_TARGET`, `FRAME_WIDTH`, `FRAME_HEIGHT` | Thông số capture |
| **Buffer** | `BUFFER_SECONDS_HEADROOM` | Headroom để tránh overwrite buffer |
| **Lưu trữ** | `LOCAL_VIDEO_DIR`, `REMOTE_ROOT_DIR` | Thư mục video local và remote |
| **Sync** | `SYNC_INTERVAL_SEC`, `SYNC_SCAN_DAYS_BACK` | Cấu hình đồng bộ định kỳ |
| **Auto-trigger** | `MOVES_URL`, `POLL_INTERVAL_SEC` | URL và chu kỳ poll AGV |
| | `MOVE_FAIL_REASONS` | Tập mã lỗi AGV sẽ kích hoạt trigger |

### Ví dụ: dùng camera RTSP Hikvision

```python
# app/config.py
CAMERA_SOURCE = "rtsp://admin:password@192.168.0.69:554/Streaming/Channels/101"
```

### Ví dụ: dùng camera USB

```python
# app/config.py
CAMERA_SOURCE = 0  # hoặc index thiết bị /dev/video0
```

---

## Yêu cầu

- Python **3.10 – 3.12** (khuyến nghị)
- FastAPI, Uvicorn
- OpenCV (`opencv-python` hoặc `opencv-python-headless`)

> **Lưu ý:** Python 3.13 chưa được khuyến nghị do vấn đề tương thích wheel của OpenCV.

---

## Cài đặt và chạy

### 1. Tạo môi trường ảo

**Linux / macOS:**
```bash
python -m venv .venv
source .venv/bin/activate
```

**Windows (PowerShell):**
```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
```

### 2. Cài đặt dependencies

```bash
pip install -r requirements.txt
```

### 3. Chạy server

```bash
python main.py
```

Server sẽ khởi động tại `http://0.0.0.0:8080`.

---

## API Endpoints

| Method | Endpoint | Mô tả |
|---|---|---|
| `GET` | `/` | Kiểm tra trạng thái server |
| `GET` | `/trigger` | Kích hoạt ghi hình thủ công |
| `GET` | `/logs` | Stream log thời gian thực (SSE) |
| `GET` | `/viewer` | Giao diện web xem log |

### Ví dụ kích hoạt trigger

```bash
curl http://localhost:8080/trigger
```

Phản hồi:
```json
{"success": true, "message": "Recording started"}
```

---

## Luồng hoạt động

### Ghi hình Pre/Post Trigger

1. Camera thread liên tục capture frame và đẩy vào **circular buffer** (JPEG in-memory).
2. Khi nhận trigger (thủ công hoặc auto), recorder thread bắt đầu:
   - **Pre**: xuất `PRE_SECONDS` giây frame từ buffer.
   - **Post**: tiếp tục capture thêm `POST_SECONDS` giây.
3. Clip `.mp4` được lưu vào `LOCAL_VIDEO_DIR`.
4. Sync thread định kỳ copy video sang `REMOTE_ROOT_DIR`.

### Auto-Trigger từ AGV

Server poll định kỳ endpoint `MOVES_URL` (AGV chassis API). Khi lệnh di chuyển mới nhất có `fail_reason` nằm trong `MOVE_FAIL_REASONS` và trạng thái là `cancelled`, trigger được kích hoạt tự động — mỗi sự cố chỉ trigger **một lần** cho đến khi AGV phục hồi (`fail_reason == 0`).

---

## Triển khai với systemd (Linux)

Tạo file `/etc/systemd/system/camera_server.service`:

```ini
[Unit]
Description=Camera Pre/Post Trigger Server
After=network.target

[Service]
User=your_user
WorkingDirectory=/path/to/camera_server
ExecStart=/path/to/camera_server/.venv/bin/python main.py
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
```

Kích hoạt và khởi động:

```bash
sudo systemctl daemon-reload
sudo systemctl enable camera_server
sudo systemctl start camera_server
sudo systemctl status camera_server
```

---

## Xem log

Truy cập giao diện web:
```
http://<server-ip>:8080/viewer
```

Hoặc stream log bằng `curl`:
```bash
curl http://localhost:8080/logs
```
