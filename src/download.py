"""
Step 1：影片轉音檔

成本意識：
- 只下載音軌（bestaudio），不下載影像流，減少頻寬與轉檔時間
- 若快取中已有音檔，直接跳過，不重新下載
"""

import yt_dlp
from cache import extract_video_id, get_cache_dir, cache_exists, log_step


def download_audio(url: str) -> str:
    video_id = extract_video_id(url)
    audio_path = get_cache_dir(video_id) / "audio.mp3"

    if cache_exists(video_id, "audio.mp3"):
        log_step("Step1-DownloadAudio", video_id, hit=True)
        return str(audio_path)

    log_step("Step1-DownloadAudio", video_id, hit=False)

    ydl_opts = {
        "format": "bestaudio/best",
        "outtmpl": str(get_cache_dir(video_id) / "audio.%(ext)s"),
        "postprocessors": [{
            "key": "FFmpegExtractAudio",
            "preferredcodec": "mp3",
            "preferredquality": "128",
        }],
        "quiet": True,
    }

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        ydl.download([url])

    return str(audio_path)


if __name__ == "__main__":
    from config import SOURCE_VIDEO_URL
    path = download_audio(SOURCE_VIDEO_URL)
    print(f"音檔輸出：{path}")
