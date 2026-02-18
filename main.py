# main.py
import uvicorn

from app.api import app

if __name__ == "__main__":
	# Chay FastAPI + camera thread da duoc start trong on_startup
	uvicorn.run(app, host="0.0.0.0", port=8080)
