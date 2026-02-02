# app/samba_uploader.py
from pathlib import Path
from time import sleep

from smb.SMBConnection import SMBConnection

from .logging_utils import log

SMB_SERVER_NAME = "rtcserver"
SMB_SERVER_IP = "192.168.5.10"
SMB_SHARE_NAME = "nhadeptraivl"

SMB_USERNAME = "rtcserver"
SMB_PASSWORD = "rtc@123"
SMB_PORT = 445
SMB_CONNECT_TIMEOUT = 10
SMB_RETRY_ATTEMPTS = 3
SMB_RETRY_BACKOFF_BASE = 1.5


def _connect_with_timeout(conn: SMBConnection) -> bool:
    try:
        return conn.connect(SMB_SERVER_IP, SMB_PORT, timeout=SMB_CONNECT_TIMEOUT)
    except TypeError:
        return conn.connect(SMB_SERVER_IP, SMB_PORT)


def upload_file_to_samba(local_path: Path, remote_path: str) -> bool:
    """
    Upload 1 file MP4 lên Samba share trực tiếp (không mount)
    """
    for attempt in range(1, SMB_RETRY_ATTEMPTS + 1):
        conn = SMBConnection(
            SMB_USERNAME,
            SMB_PASSWORD,
            "camera-client",
            SMB_SERVER_NAME,
            use_ntlm_v2=True,
            is_direct_tcp=True,
        )

        try:
            ok = _connect_with_timeout(conn)
            if not ok:
                raise ConnectionError("Cannot connect to Samba server")

            with open(local_path, "rb") as f:
                conn.storeFile(SMB_SHARE_NAME, remote_path, f)

            return True
        except Exception as exc:
            log(f"[UPLOAD][WARN] Attempt {attempt}/{SMB_RETRY_ATTEMPTS} failed: {exc}")
            if attempt >= SMB_RETRY_ATTEMPTS:
                raise
            sleep(SMB_RETRY_BACKOFF_BASE ** (attempt - 1))
        finally:
            conn.close()

    return False
