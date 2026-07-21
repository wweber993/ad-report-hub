"""
AD Report Hub — Configuration
"""

import os
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(os.path.dirname(__file__)), ".env"))


class Config:
    SECRET_KEY: str = os.getenv("SECRET_KEY", "adreporthub-secret-key-change-in-production")
    FLASK_ENV: str  = os.getenv("FLASK_ENV", "production")
    DEBUG: bool     = os.getenv("FLASK_DEBUG", "false").lower() == "true"
    HOST: str       = os.getenv("HOST", "0.0.0.0")
    PORT: int       = int(os.getenv("PORT", "8090"))

    # SSL
    SSL_CERT: str = os.getenv("SSL_CERT", "")
    SSL_KEY: str  = os.getenv("SSL_KEY",  "")

    # Database
    BASE_DIR: str = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    DATA_DIR: str = os.path.join(BASE_DIR, "data")
    os.makedirs(DATA_DIR, exist_ok=True)
    SQLALCHEMY_DATABASE_URI: str = "sqlite:///" + os.path.join(DATA_DIR, "adreporthub.db").replace("\\", "/")
    SQLALCHEMY_TRACK_MODIFICATIONS: bool = False


    # Logging
    LOG_DIR: str  = os.path.join(BASE_DIR, "logs")
    LOG_FILE: str = os.path.join(LOG_DIR, "adreporthub.log")
    LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO").upper()

    # Report AD
    AD_DATA_DIR: str   = os.getenv("AD_DATA_DIR", os.path.join(BASE_DIR, "data", "ad"))
    INGEST_TOKEN: str  = os.getenv("INGEST_TOKEN", "")

    # Flask-Caching
    CACHE_TYPE: str            = "SimpleCache"
    CACHE_DEFAULT_TIMEOUT: int = 300

