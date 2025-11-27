# app/config.py

import os
from dotenv import load_dotenv

# Load variables from .env file into the environment
load_dotenv()


class Config:
    # 1. Secret Key: Used for session security and cryptographic signing
    SECRET_KEY = os.environ.get("SECRET_KEY") or "fallback-secret-key-for-dev"

    # 2. JWT Secret Key (can reuse SECRET_KEY if you want)
    JWT_SECRET_KEY = os.environ.get("JWT_SECRET_KEY") or SECRET_KEY

    # 3. Database URL
    uri = os.environ.get("DATABASE_URL")
    if uri and uri.startswith("postgres://"):
        uri = uri.replace("postgres://", "postgresql://", 1)

    SQLALCHEMY_DATABASE_URI = uri
    SQLALCHEMY_TRACK_MODIFICATIONS = False
