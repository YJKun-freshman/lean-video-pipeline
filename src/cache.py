"""
快取機制：所有步驟共用，避免同一支影片被重複處理、重複產生費用。

設計邏輯：
- 以 YouTube video_id 當作 key，每支影片一個獨立資料夾：data/cache/{video_id}/
- 每個步驟輸出固定檔名，執行前先檢查檔案是否存在，存在就直接讀取跳過該步驟
"""

import re
import json
from pathlib import Path

CACHE_ROOT = Path(__file__).resolve().parent.parent / "data" / "cache"


def extract_video_id(url: str) -> str:
    """從 YouTube 網址取出 video_id，當作快取 key。"""
    match = re.search(r"(?:v=|youtu\.be/)([A-Za-z0-9_-]{11})", url)
    if not match:
        raise ValueError(f"無法從網址解析出 video_id: {url}")
    return match.group(1)


def get_cache_dir(video_id: str) -> Path:
    """取得該影片專屬的快取資料夾，不存在就建立。"""
    d = CACHE_ROOT / video_id
    d.mkdir(parents=True, exist_ok=True)
    return d


def cache_exists(video_id: str, filename: str) -> bool:
    return (get_cache_dir(video_id) / filename).exists()


def load_json(video_id: str, filename: str):
    path = get_cache_dir(video_id) / filename
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def save_json(video_id: str, filename: str, data) -> Path:
    path = get_cache_dir(video_id) / filename
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    return path


def cache_file_path(video_id: str, filename: str) -> Path:
    """回傳非 JSON 檔案（音檔、影片、圖片）該存放的路徑。"""
    return get_cache_dir(video_id) / filename


def log_step(step_name: str, video_id: str, hit: bool):
    status = "命中快取，跳過" if hit else "未命中，執行中"
    print(f"[{step_name}] video_id={video_id} -> {status}")
