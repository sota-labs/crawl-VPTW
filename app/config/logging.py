import logging
import os
from datetime import datetime, timedelta
from logging import FileHandler

LOG_DIR = "logs"
os.makedirs(LOG_DIR, exist_ok=True)


def setup_daily_logger(days_to_keep: int = 30):
    now = datetime.now()
    cutoff_date = now - timedelta(days=days_to_keep)

    for filename in os.listdir(LOG_DIR):
        if filename.endswith(".log"):
            try:
                file_date_str = filename.split(".")[0]
                file_date = datetime.strptime(file_date_str, "%d-%m-%Y")

                if file_date < cutoff_date:
                    file_path = os.path.join(LOG_DIR, filename)
                    os.remove(file_path)
                    print(f"[INFO] Removed log file: {filename}")
            except (ValueError, OSError):
                continue

    today_str = datetime.now().strftime("%d-%m-%Y")
    log_file_path = os.path.join(LOG_DIR, f"{today_str}.log")

    logger = logging.getLogger(__name__)
    logger.setLevel(logging.INFO)

    # Đảm bảo handler chỉ được thêm một lần
    if not logger.handlers:
        file_handler = FileHandler(log_file_path, encoding="utf-8")
        file_formatter = logging.Formatter(
            fmt="[%(asctime)s][%(levelname)s] %(message)s", datefmt="%d-%m-%Y %H:%M:%S"
        )
        file_handler.setFormatter(file_formatter)
        logger.addHandler(file_handler)

        stream_handler = logging.StreamHandler()
        stream_handler.setFormatter(file_formatter)
        logger.addHandler(stream_handler)

    return logger


log = setup_daily_logger(days_to_keep=30)
