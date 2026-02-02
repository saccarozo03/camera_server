# app/samba_uploader.py
from smb.SMBConnection import SMBConnection
from pathlib import Path

SMB_SERVER_NAME = "rtcserver"
SMB_SERVER_IP = "192.168.5.10"
SMB_SHARE_NAME = "nhadeptraivl"

SMB_USERNAME = "rtcserver"
SMB_PASSWORD = "rtc@123"
SMB_PORT = 445


def upload_file_to_samba(local_path: Path, remote_path: str):
    """
    Upload 1 file MP4 lên Samba share trực tiếp (không mount)
    """

    conn = SMBConnection(
        SMB_USERNAME,
        SMB_PASSWORD,
        "camera-client",
        SMB_SERVER_NAME,
        use_ntlm_v2=True,
        is_direct_tcp=True,
    )

    ok = conn.connect(SMB_SERVER_IP, SMB_PORT)
    if not ok:
        raise ConnectionError("Cannot connect to Samba server")

    with open(local_path, "rb") as f:
        conn.storeFile(SMB_SHARE_NAME, remote_path, f)

    conn.close()
    return True
