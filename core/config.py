import os
from dotenv import load_dotenv

# ── Silence Chroma telemetry ───────────────────────────────────────────────────
os.environ["CHROMA_TELEMETRY_IMPL"] = "None"
os.environ["ANONYMIZED_TELEMETRY"] = "False"

# ── Load .env for local development ───────────────────────────────────────────
env_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), '.env')
load_dotenv(env_path, override=False)   # Don't override env vars already set


def _load_streamlit_secrets():
    """
    Inject Streamlit Cloud secrets into os.environ so the rest of the code
    can read them with os.getenv() as usual.

    Handles two formats:
      Flat   →  OPENAI_API_KEY = "..."
      Nested →  [api_keys]
                OPENAI_API_KEY = "..."  (as shown in the Cloud UI)
    """
    try:
        import streamlit as st
        import os
        
        # Prevent Streamlit from throwing the red warning if there are no secrets
        if not os.path.exists(".streamlit/secrets.toml") and not os.environ.get("STREAMLIT_SERVER_ENVIRONMENT"):
            return
            
        secrets = st.secrets

        # ── Flat keys (top-level) ──────────────────────────────────────────────
        flat_keys = [
            "OPENAI_API_KEY",
            "GOOGLE_DOC_ID",
            "GOOGLE_SERVICE_ACCOUNT_JSON",
            "ADMIN_USERNAME",
            "ADMIN_PASSWORD_HASH",
            "SUPABASE_URL",
            "SUPABASE_KEY",
        ]
        for key in flat_keys:
            if key in secrets and not os.environ.get(key):
                os.environ[key] = str(secrets[key])

        # ── Nested [api_keys] section ─────────────────────────────────────────
        if "api_keys" in secrets:
            for key in flat_keys:
                if key in secrets["api_keys"] and not os.environ.get(key):
                    os.environ[key] = str(secrets["api_keys"][key])

        # ── Nested [google] section ───────────────────────────────────────────
        if "google" in secrets:
            google_map = {
                "GOOGLE_DOC_ID": "GOOGLE_DOC_ID",
                "GOOGLE_SERVICE_ACCOUNT_JSON": "GOOGLE_SERVICE_ACCOUNT_JSON",
            }
            for secret_key, env_key in google_map.items():
                if secret_key in secrets["google"] and not os.environ.get(env_key):
                    os.environ[env_key] = str(secrets["google"][secret_key])

        # ── Nested [admin] section ────────────────────────────────────────────
        if "admin" in secrets:
            for key in ("ADMIN_USERNAME", "ADMIN_PASSWORD_HASH"):
                if key in secrets["admin"] and not os.environ.get(key):
                    os.environ[key] = str(secrets["admin"][key])

    except FileNotFoundError:
        pass
    except Exception:
        # Not running in Streamlit (e.g., during unit tests), silently skip.
        pass


# Run secret injection before Config is read
_load_streamlit_secrets()


class Config:
    ADMIN_USERNAME             = os.getenv("ADMIN_USERNAME", "admin")
    OPENAI_API_KEY             = os.getenv("OPENAI_API_KEY")
    GOOGLE_SERVICE_ACCOUNT_JSON = os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON")
    GOOGLE_DOC_ID              = os.getenv("GOOGLE_DOC_ID")
    GOOGLE_DOC_URL             = (
        f"https://docs.google.com/document/d/{GOOGLE_DOC_ID}/export?format=txt"
        if GOOGLE_DOC_ID else None
    )
    ADMIN_PASSWORD_HASH        = os.getenv("ADMIN_PASSWORD_HASH")

    # Supabase Database Keys
    SUPABASE_URL               = os.getenv("SUPABASE_URL")
    SUPABASE_KEY               = os.getenv("SUPABASE_KEY")

    # Model
    MODEL_NAME = "gpt-5"

    @staticmethod
    def validate():
        if not Config.OPENAI_API_KEY:
            print("WARNING: OPENAI_API_KEY not set — AI evaluation will fail.")
        return Config.OPENAI_API_KEY is not None


# Validate on import
Config.validate()
