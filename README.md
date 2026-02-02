# Camera Pre/Post Trigger Server

A lightweight **FastAPI-based camera server** designed to manage a persistent camera thread and record **short pre-trigger and post-trigger video clips**.

The system is optimized for **embedded / edge devices** (Raspberry Pi, RockPi, industrial PCs) and supports **HTTP triggering**, **background recording**, and **real-time log streaming** via **Server-Sent Events (SSE)**.

---

## Architecture Overview
```mermaid
flowchart TD

    %% ===== Adaptive Styles (No fixed background fill) =====
    classDef client stroke:#1565C0,stroke-width:2px,fill:none;
    classDef server stroke:#2E7D32,stroke-width:2px,fill:none;
    classDef camera stroke:#EF6C00,stroke-width:2px,fill:none;
    classDef output stroke:#AD1457,stroke-width:2px,fill:none;

    %% ===== Architecture Flow =====
    A["Client / AGV / App"] -->|HTTP Trigger| B["FastAPI Server"]
    B -->|Startup Event| C["Camera Thread<br/>OpenCV + Ring Buffer"]
    C -->|Encode + Save| D["Video Clips (.mp4)"]

    %% ===== Apply Styles =====
    class A client
    class B server
    class C camera
    class D output


```
---

## Features

- Persistent camera lifecycle managed by FastAPI lifespan
- Pre-trigger and post-trigger recording
- Background recording thread (non-blocking API)
- OpenCV-based capture and encoding
- HTTP trigger endpoint
- Real-time log streaming via Server-Sent Events (SSE)
- Minimal HTML log viewer
- Thread-safe logging using `queue.Queue`
- Clean startup and shutdown handling
- Suitable for headless devices and `systemd` deployment

---

## Project Structure
---
```mermaid
camera_server/
├── app/
│ ├── api.py # FastAPI routes and lifespan
│ ├── camera.py # Camera capture logic
│ ├── recorder.py # Background recording thread
│ ├── logging_utils.py # Thread-safe logging and SSE
│ └── config.py # Camera and recording parameters
├── main.py # FastAPI entrypoint
├── requirements.txt
└── README.md
```
---

## Requirements

- Python **3.10 – 3.11** (recommended)
- FastAPI
- Uvicorn
- OpenCV (`cv2`)

> ⚠️ Python 3.13 is not recommended yet due to OpenCV wheel compatibility.

---

## Quick Start (Windows / PowerShell)

### Create virtual environment

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
--- 
## Install dependencies
```powershell 
pip install -r requirements.txt
---


