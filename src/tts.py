"""
TTS 語音生成模組
"""

import asyncio
import edge_tts

from cache import cache_file_path, cache_exists, log_step

TTS_VOICE = "zh-TW-HsiaoChenNeural"


async def _generate_tts_async(text: str, output_path: str):
    communicate = edge_tts.Communicate(text, TTS_VOICE)
    await communicate.save(output_path)


def generate_tts(video_id: str, index: int, text: str) -> str:
    filename = f"segment_{index}_audio.mp3"
    output_path = str(cache_file_path(video_id, filename))

    if cache_exists(video_id, filename):
        log_step(f"TTS(segment_{index})", video_id, hit=True)
        return output_path

    log_step(f"TTS(segment_{index})", video_id, hit=False)
    asyncio.run(_generate_tts_async(text, output_path))
    return output_path


if __name__ == "__main__":
    test_text = "根據TVBS新聞報導指出，新青安政策雖然降低了購屋門檻，但也讓房價與房貸負擔同步攀升。"
    path = generate_tts("test", 0, test_text)
    print(f"測試語音已產生：{path}")