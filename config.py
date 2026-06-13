import os
from dotenv import load_dotenv

load_dotenv()

SECRET_KEY = os.getenv("SECRET_KEY", "dev-only-change-me")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "admin")
DB_PATH = os.getenv("DB_PATH", os.path.join(os.path.dirname(__file__), "gmm_media.db"))
