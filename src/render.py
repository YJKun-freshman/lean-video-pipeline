# Step 4：Scene Orchestrator

from moviepy import CompositeVideoClip, concatenate_videoclips

from cache import cache_file_path, cache_exists, log_step
from tts import generate_tts_for_scene
from text_render import make_subtitle_clip
from transitions import apply_transitions
from scenes.hook import render_hook_scene
from scenes.big_number import render_big_number_scene
from scenes.ranking import render_ranking_scene
from scenes.trend import render_trend_scene
from scenes.comparison import render_comparison_scene
from scenes.quote import render_quote_scene
from scenes.timeline import render_timeline_scene
from scenes.ending import render_ending_scene

SUPPORTED_SCENE_RENDERERS = {
    "hook": render_hook_scene,
    "big_number": render_big_number_scene,
    "ranking": render_ranking_scene,
    "trend": render_trend_scene,
    "comparison": render_comparison_scene,
    "quote": render_quote_scene,
    "timeline": render_timeline_scene,
    "ending": render_ending_scene,
}


def render_segment_video(video_id, segment_index, segment):
    filename = f"segment_{segment_index}.mp4"
    output_path = str(cache_file_path(video_id, filename))
    topic = segment.get("topic", "（無主題）")

    if cache_exists(video_id, filename):
        log_step(f"Render(segment_{segment_index})", video_id, hit=True)
        return output_path

    clips = []
    types = []
    for scene in segment.get("scenes", []):
        scene_type = scene.get("type")
        scene_id = scene.get("id", "（無id）")

        renderer = SUPPORTED_SCENE_RENDERERS.get(scene_type)
        if renderer is None:
            print(f"[Render] segment={segment_index} topic='{topic}' "
                  f"scene={scene_id} type={scene_type} 尚未支援此Scene type，暫時跳過")
            continue

        audio_path, duration = generate_tts_for_scene(video_id, segment_index, scene)
        clip = renderer(video_id, segment_index, scene, duration)

        subtitle = make_subtitle_clip(scene, duration)
        if subtitle is not None:
            clip = CompositeVideoClip([clip, subtitle]).with_duration(duration)

        from moviepy import AudioFileClip
        clip = clip.with_audio(AudioFileClip(audio_path))
        clips.append(clip)
        types.append(scene_type)

    if not clips:
        print(f"[Render] segment={segment_index} topic='{topic}' "
              f"沒有任何支援的Scene，跳過此segment的影片產出")
        return None

    log_step(f"Render(segment_{segment_index})", video_id, hit=False)

    final_clip = concatenate_videoclips(apply_transitions(clips, types))
    final_clip.write_videofile(
        output_path,
        fps=24,
        codec="libx264",
        audio_codec="aac",
    )
    final_clip.close()

    return output_path


if __name__ == "__main__":
    test_segment = {
        "topic": "測試段落",
        "scenes": [
            {"id": "scene_01", "type": "hook", "narration": "台北買房，到底有多難？"},
            {"id": "scene_02", "type": "comparison", "narration": "這個應該被跳過",
             "data": [{"label": "A", "value": 1}, {"label": "B", "value": 2}]},
            {"id": "scene_03", "type": "big_number", "narration": "房價所得比來到11.3倍",
             "value": "11.3", "unit": "倍", "label": "房價所得比"},
        ]
    }
    output = render_segment_video("test_scenes", "orchestrator", test_segment)
    print(f"\n測試影片已產生：{output}")