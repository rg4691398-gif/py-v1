import os

def get_config():
    return {
        "SECRET_KEY": os.environ.get("SECRET_KEY", "change-me"),
        "DB_PATH": os.environ.get("DB_PATH", os.path.join(os.getcwd(), "instance", "vouchers.db")),
        "BOOTSTRAP_ADMIN_USER": os.environ.get("BOOTSTRAP_ADMIN_USER", "admin"),
        "BOOTSTRAP_ADMIN_PASS": os.environ.get("BOOTSTRAP_ADMIN_PASS", "change-me"),
        "MAX_CLOCK_SKEW_SECONDS": int(os.environ.get("MAX_CLOCK_SKEW_SECONDS", "300")),
        "NONCE_TTL_SECONDS": int(os.environ.get("NONCE_TTL_SECONDS", "600")),
        "PRINT_BRAND": os.environ.get("PRINT_BRAND", "Hotspot"),
        "DB_BUSY_TIMEOUT_MS": int(os.environ.get("DB_BUSY_TIMEOUT_MS", "5000")),
    }
