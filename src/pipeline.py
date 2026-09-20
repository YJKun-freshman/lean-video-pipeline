# 主流程：依序執行 Step1 到 Step4，自動產生所有篩選段落的短影音
#
# 執行方式：python pipeline.py

from config import SOURCE_VIDEO_URL
from cache import extract_video_id, load_json
from download import download_audio
from transcribe import transcribe
from rewrite import rewrite_and_score, select_top_segments
from tts import generate_tts
from render import render_video


def main():
    video_id = extract_video_id(SOURCE_VIDEO_URL)
    print(f"=== 開始處理影片 {video_id} ===\n")

    print("--- Step1：下載音檔 ---")
    audio_path = download_audio(SOURCE_VIDEO_URL)

    print("\n--- Step2：轉錄逐字稿 ---")
    transcript = transcribe(video_id, audio_path)

    print("\n--- Step3：改寫腳本 + 評分篩選 ---")
    candidates = rewrite_and_score(video_id, transcript["text"])
    selected = select_top_segments(candidates, video_id)

    print(f"\n--- Step4：生成 {len(selected)} 支短影音 ---")
    output_paths = []
    for i, segment in enumerate(selected):
        print(f"\n處理第 {i + 1}/{len(selected)} 段：{segment['topic']}")

        audio_seg_path = generate_tts(video_id, i, segment["rewritten_script"])

        chart_data = segment.get("chart_data") or {}
        if not chart_data:
            chart_data = {segment["topic"]: 1}

        output_path = render_video(
            video_id, i,
            segment["topic"],
            segment["rewritten_script"],
            audio_seg_path,
            chart_data,
        )
        output_paths.append(output_path)

    print(f"\n=== 全部完成，共產生 {len(output_paths)} 支短影音 ===")
    for p in output_paths:
        print(f"  {p}")


if __name__ == "__main__":
    main()