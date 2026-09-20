"""
Step 2：音檔轉逐字稿（本地端執行，完全免費）
"""
import os
os.environ["HF_HUB_DISABLE_SYMLINKS"] = "1"
import subprocess
from pathlib import Path
from faster_whisper import WhisperModel

from cache import extract_video_id, get_cache_dir, cache_exists, load_json, save_json, log_step
from config import WHISPER_MODEL_SIZE, MAX_AUDIO_MINUTES

_model = None


def get_model() -> WhisperModel:
    global _model
    if _model is None:
        print(f"載入本地 Whisper 模型：{WHISPER_MODEL_SIZE}（首次執行會下載模型檔案，之後會快取在本機）")
        _model = WhisperModel(WHISPER_MODEL_SIZE, device="cpu", compute_type="int8")
    return _model


def get_audio_duration_minutes(audio_path: str) -> float:
    result = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", audio_path],
        capture_output=True, text=True,
    )
    return float(result.stdout.strip()) / 60


def trim_silence(audio_path: str, output_path: str):
    subprocess.run([
        "ffmpeg", "-y", "-i", audio_path,
        "-af", "silenceremove=stop_periods=-1:stop_duration=1:stop_threshold=-35dB",
        output_path,
    ], check=True)


def transcribe(video_id: str, audio_path: str) -> dict:
    if cache_exists(video_id, "transcript.json"):
        log_step("Step2-Transcribe", video_id, hit=True)
        return load_json(video_id, "transcript.json")

    log_step("Step2-Transcribe", video_id, hit=False)

    duration = get_audio_duration_minutes(audio_path)
    print(f"原始音檔長度：{duration:.1f} 分鐘")

    send_path = audio_path
    if duration > MAX_AUDIO_MINUTES:
        print(f"超過門檻 {MAX_AUDIO_MINUTES} 分鐘，執行靜音前處理以縮短本地運算時間...")
        trimmed_path = str(Path(audio_path).with_name("audio_trimmed.mp3"))
        trim_silence(audio_path, trimmed_path)
        send_path = trimmed_path
        print(f"前處理後長度：{get_audio_duration_minutes(send_path):.1f} 分鐘")

    print("開始轉錄，第一次執行需下載模型檔案，請耐心等候...")
    model = get_model()
    segments_gen, info = model.transcribe(send_path, language="zh")

    segments = []
    full_text_parts = []
    for seg in segments_gen:
        segments.append({"start": seg.start, "end": seg.end, "text": seg.text})
        full_text_parts.append(seg.text)
        print(f"  [{seg.start:.1f}s -> {seg.end:.1f}s] {seg.text}")

    transcript_data = {
        "text": "".join(full_text_parts),
        "segments": segments,
    }
    save_json(video_id, "transcript.json", transcript_data)
    return transcript_data


if __name__ == "__main__":
    from config import SOURCE_VIDEO_URL
    from cache import get_cache_dir

    vid = extract_video_id(SOURCE_VIDEO_URL)
    audio_file = get_cache_dir(vid) / "audio.mp3"
    result = transcribe(vid, str(audio_file))
    print(f"\n逐字稿字數：{len(result['text'])}")