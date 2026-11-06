
import os
from pathlib import Path

import gdown


BASE_DIR = Path(__file__).resolve().parents[2]

DATA_FILE = (
    BASE_DIR
    / "data"
    / "processed"
    / "m5_processed_features.csv"
)


def download_m5_dataset() -> None:
    file_id = os.getenv("M5_DATA_FILE_ID")

    if not file_id:
        raise RuntimeError(
            "M5_DATA_FILE_ID environment variable is not configured."
        )

    if DATA_FILE.exists() and DATA_FILE.stat().st_size > 0:
        print(f"[DATA] Dataset already exists: {DATA_FILE}")
        return

    DATA_FILE.parent.mkdir(parents=True, exist_ok=True)

    print("[DATA] Downloading M5 dataset from Google Drive...")

    downloaded_file = gdown.download(
        id=file_id,
        output=str(DATA_FILE),
        quiet=False,
    )

    if not downloaded_file or not DATA_FILE.exists():
        raise RuntimeError(
            "Failed to download M5 dataset from Google Drive."
        )

    if DATA_FILE.stat().st_size == 0:
        DATA_FILE.unlink(missing_ok=True)
        raise RuntimeError("Downloaded M5 dataset is empty.")

    print(
        f"[DATA] Dataset downloaded successfully. "
        f"Size: {DATA_FILE.stat().st_size / (1024 * 1024):.2f} MB"
    )
