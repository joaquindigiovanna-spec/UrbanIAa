import os
from dotenv import load_dotenv

load_dotenv()


def _normalizar_url(url):
    """Render/Heroku/Aiven entregan URLs con esquemas que SQLAlchemy no acepta tal cual."""
    if url.startswith("postgres://"):
        url = url.replace("postgres://", "postgresql://", 1)
    if url.startswith("mysql://"):
        url = url.replace("mysql://", "mysql+pymysql://", 1)
    return url


class Config:
    SECRET_KEY = os.getenv("SECRET_KEY", "dev-inseguro-cambiar-en-produccion")
    SQLALCHEMY_DATABASE_URI = _normalizar_url(os.getenv("DATABASE_URL", "sqlite:///urbania.db"))
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_ENGINE_OPTIONS = {"pool_pre_ping": True, "pool_recycle": 280}
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    SESSION_COOKIE_SECURE = os.getenv("COOKIE_SECURE", "0") == "1"
    MAX_CONTENT_LENGTH = 2 * 1024 * 1024
    GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
    GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
