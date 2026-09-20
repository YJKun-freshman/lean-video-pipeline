# 影片組裝模組（進階版）：標題卡 + 圖表成長動畫 + 逐句字幕 + 淡入淡出

import re

from moviepy import (
    AudioFileClip, ImageClip, ImageSequenceClip,
    CompositeVideoClip, concatenate_videoclips, vfx,
)

from cache import cache_file_path, cache_exists, log_step
from charts import generate_chart_frames
from text_render import render_title_image, render_subtitle_image

TITLE_DURATION = 1.2
FADE_DURATION = 0.3
SUBTITLE_HEIGHT = 220


def _split_sentences(text):
    parts = re.split(r"(?<=[。！？])", text)
    return [p.strip() for p in parts if p.strip()]


def render_video(video_id, index, topic, script_text, audio_path, data_points):
    filename = f"segment_{index}.mp4"
    output_path = str(cache_file_path(video_id, filename))

    if cache_exists(video_id, filename):
        log_step(f"Render(segment_{index})", video_id, hit=True)
        return output_path

    log_step(f"Render(segment_{index})", video_id, hit=False)

    audio_clip = AudioFileClip(audio_path)

    frames = generate_chart_frames(video_id, index, topic, data_points, n_frames=12)
    growth_clip = ImageSequenceClip(frames, fps=12)
    remaining = max(audio_clip.duration - growth_clip.duration, 0.1)
    still_clip = ImageClip(frames[-1]).with_duration(remaining)
    chart_clip = concatenate_videoclips([growth_clip, still_clip])
    chart_clip = chart_clip.with_effects([vfx.FadeIn(FADE_DURATION), vfx.FadeOut(FADE_DURATION)])

    chart_width, chart_height = chart_clip.size
    canvas_height = chart_height + SUBTITLE_HEIGHT

    sentences = _split_sentences(script_text)
    total_chars = sum(len(s) for s in sentences) or 1
    subtitle_clips = []
    cursor = 0.0
    for i, sentence in enumerate(sentences):
        duration = chart_clip.duration * (len(sentence) / total_chars)
        img_path = render_subtitle_image(video_id, f"{index}_s{i}", sentence, chart_width, SUBTITLE_HEIGHT)
        clip = (ImageClip(img_path)
                .with_start(cursor)
                .with_duration(duration)
                .with_position((0, chart_height)))
        subtitle_clips.append(clip)
        cursor += duration

    content_clip = CompositeVideoClip(
        [chart_clip.with_position((0, 0))] + subtitle_clips,
        size=(chart_width, canvas_height),
    )
    content_clip = content_clip.with_duration(chart_clip.duration)
    content_clip = content_clip.with_audio(audio_clip)

    title_img_path = render_title_image(video_id, index, topic, chart_width, canvas_height)
    title_clip = ImageClip(title_img_path).with_duration(TITLE_DURATION)
    title_clip = title_clip.with_effects([vfx.FadeIn(FADE_DURATION)])

    final_clip = concatenate_videoclips([title_clip, content_clip])

    final_clip.write_videofile(
        output_path,
        fps=24,
        codec="libx264",
        audio_codec="aac",
    )

    audio_clip.close()
    final_clip.close()

    return output_path


if __name__ == "__main__":
    from tts import generate_tts

    demo_topic = "測試段落：房貸負擔率比較"
    demo_script = "根據TVBS新聞報導指出，台北市的房貸負擔率高居全國之冠。年輕族群購屋壓力沉重，不容小覷。"
    demo_data = {"台北市": 60, "台中市": 45, "台南市": 40}

    audio_path = generate_tts("demo", 0, demo_script)
    output = render_video("demo", 0, demo_topic, demo_script, audio_path, demo_data)
    print(f"測試影片（逐句字幕版）已產生：{output}")