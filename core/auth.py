import bcrypt

from core.config import Config
from core.db import get_admin_by_username, update_admin_last_login


def verify_admin_credentials(username: str, password: str) -> bool:
    if not username or not password:
        return False

    admin_row = get_admin_by_username(username)
    if admin_row and admin_row.get("password_hash"):
        try:
            return bcrypt.checkpw(password.encode("utf-8"), admin_row["password_hash"].encode("utf-8"))
        except Exception:
            return False

    if username != Config.ADMIN_USERNAME:
        return False

    if not Config.ADMIN_PASSWORD_HASH:
        # Default fallback for testing locally
        return password == "admin123"

    try:
        return bcrypt.checkpw(password.encode("utf-8"), Config.ADMIN_PASSWORD_HASH.encode("utf-8"))
    except Exception:
        return False


def record_admin_login(username: str) -> None:
    try:
        update_admin_last_login(username)
    except Exception:
        pass