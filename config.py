import os
from pathlib import Path
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")

BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
DEVELOPER_ID = os.getenv("DEVELOPER_ID", "").strip()
ADMIN_SECRET_KEY = os.getenv("ADMIN_SECRET_KEY", "shabah_admin_secret").strip()
def _resolve_webapp_url():
    # Prefer an explicitly configured public HTTPS URL.
    explicit = os.getenv("WEBAPP_URL", "").strip().rstrip("/")
    railway_domain = os.getenv("RAILWAY_PUBLIC_DOMAIN", "").strip().strip("/")
    render_url = os.getenv("RENDER_EXTERNAL_URL", "").strip().rstrip("/")

    # On Railway, never allow an old localhost WEBAPP_URL to override the public domain.
    if railway_domain:
        return f"https://{railway_domain}"
    if render_url:
        return render_url if render_url.startswith(("https://", "http://")) else f"https://{render_url}"
    if explicit:
        if explicit.startswith(("https://", "http://")):
            return explicit
        return f"https://{explicit}"
    # Local development only. Telegram buttons will not expose this URL.
    return f"http://localhost:{os.getenv('PORT', '8000')}"

WEBAPP_URL = _resolve_webapp_url()
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
