"""Middleware module"""
from app.middleware.auth import get_current_user_from_token

__all__ = ["get_current_user_from_token"]
