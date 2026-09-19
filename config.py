import os
from pathlib import Path
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")

BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
DEVELOPER_ID = os.getenv("DEVELOPER_ID", "").strip()
ADMIN_SECRET_KEY = os.getenv("ADMIN_SECRET_KEY", "shabah_admin_secret").strip()
_configured_webapp = os.getenv("WEBAPP_URL", "").strip().rstrip("/")
_railway_domain = os.getenv("RAILWAY_PUBLIC_DOMAIN", "").strip().strip("/")

# On Railway always prefer the public HTTPS domain. Telegram rejects localhost/http buttons.
if _railway_domain:
    WEBAPP_URL = _railway_domain if _railway_domain.startswith(("http://", "https://")) else f"https://{_railway_domain}"
elif _configured_webapp and not any(x in _configured_webapp.lower() for x in ("localhost", "127.0.0.1")):
    WEBAPP_URL = _configured_webapp if _configured_webapp.startswith(("http://", "https://")) else f"https://{_configured_webapp}"
else:
    WEBAPP_URL = ""
HOST = os.getenv("HOST", "0.0.0.0")
PORT = int(os.getenv("PORT", 8000))

UPLOAD_DIR = BASE_DIR / "uploads"
UPLOAD_DIR.mkdir(exist_ok=True)
STATIC_DIR = BASE_DIR / "static"

# Google STUN servers for WebRTC
ICE_SERVERS = [
    {"urls": "stun:stun.l.google.com:19302"},
    {"urls": "stun:stun1.l.google.com:19302"},
    {"urls": "stun:stun2.l.google.com:19302"}
]
