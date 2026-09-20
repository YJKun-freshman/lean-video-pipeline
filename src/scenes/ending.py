# Ending Scene：合理收尾，不是華麗動畫
#
# 輸入：顯示文字 = scene["text"]（若有），否則 scene["narration"]。
#       Gemini 給了合理的收尾句 → 原樣顯示；整段沒有 ending → scene_planner 已補上固定的中性句
#       （ENDING_FALLBACK_TEXT），這裡照樣渲染，不再自行加任何結論、數據、行動呼籲或「感謝觀看」。
# 畫面：置中的白色文字 + 上方一小段青色短線。fallback 那句只是資料來源說明、不是內容摘要，
#       所以用較小的灰色字，視覺上不搶戲。
# 動畫：短線由中間向兩側展開、文字淡入，定格；最後 10% 整體淡出，讓整支影片自然收在深色底。
# 時間軸全部是「佔 Scene 實際時長的比例」。

import numpy as np
from moviepy import VideoClip
from PIL import Image, ImageColor, ImageDraw

from scene_planner import ENDING_FALLBACK_TEXT
from scenes import base
from scenes.hook import _blend, _font, _wrap_lines

TEXT_WIDTH = 0.80 * base.CANVAS_WIDTH
TEXT_PX = 64
FALLBACK_TEXT_PX = 50
LINE_HEIGHT_RATIO = 1.5
FONT_SCALES = (1.0, 0.85, 0.72, 0.60)        # 文字太長時逐級縮小字級
MAX_BLOCK_HEIGHT = 0.50 * base.CANVAS_HEIGHT
CENTER_Y_RATIO = 0.47
RULE_WIDTH = 120
RULE_HEIGHT = 8
RULE_GAP = 64
BASELINE_OFFSET = 0.35

# 時間軸（佔總時長比例）
RULE_PHASE = (0.00, 0.20)         # 短線由中間向兩側展開
TEXT_PHASE = (0.06, 0.30)         # 文字淡入，之後定格
FADE_OUT_PHASE = (0.90, 1.00)     # 收尾淡出


def _ending_text(scene):
    for key in ("text", "narration"):
        value = scene.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def render_ending_scene(video_id, segment_index, scene, duration):
    text = _ending_text(scene)
    is_fallback = text == ENDING_FALLBACK_TEXT

    base_px = FALLBACK_TEXT_PX if is_fallback else TEXT_PX
    for scale in FONT_SCALES:
        px = round(base_px * scale)
        lines = _wrap_lines(text, max(1, int(TEXT_WIDTH / px))) if text else []
        line_height = px * LINE_HEIGHT_RATIO
        if len(lines) * line_height <= MAX_BLOCK_HEIGHT:
            break
    font = _font(px)
    block_top = base.CANVAS_HEIGHT * CENTER_Y_RATIO - len(lines) * line_height / 2
    rule_y = block_top - RULE_GAP
    cx = base.CANVAS_WIDTH / 2

    bg = np.empty((base.CANVAS_HEIGHT, base.CANVAS_WIDTH, 3), np.uint8)
    bg[:] = ImageColor.getrgb(base.BG_COLOR)
    accent = ImageColor.getrgb(base.ACCENT_COLOR)
    text_color = ImageColor.getrgb(base.TEXT_COLOR_SECONDARY if is_fallback else base.TEXT_COLOR_PRIMARY)
    size = (base.CANVAS_WIDTH, base.CANVAS_HEIGHT)

    def make_frame(t):
        p = t / duration if duration > 0 else 1.0
        fade_out = 1.0 - base.ease_in_out_cubic(base.phase(p, *FADE_OUT_PHASE))
        accent_layer, text_layer = Image.new("L", size, 0), Image.new("L", size, 0)

        if lines and fade_out > 0:
            half = RULE_WIDTH / 2 * base.ease_out_cubic(base.phase(p, *RULE_PHASE))
            if half >= 1:
                ImageDraw.Draw(accent_layer).rectangle((cx - half, rule_y, cx + half, rule_y + RULE_HEIGHT),
                                                       fill=int(255 * fade_out))
            level = int(255 * base.ease_in_out_cubic(base.phase(p, *TEXT_PHASE)) * fade_out)
            dt = ImageDraw.Draw(text_layer)
            for k, line in enumerate(lines):
                center_y = block_top + (k + 0.5) * line_height
                dt.text((cx, center_y + BASELINE_OFFSET * px), line, font=font, fill=level, anchor="ms")

        frame = bg.copy()
        for layer, color in ((accent_layer, accent), (text_layer, text_color)):
            box = layer.getbbox()
            if box:
                _blend(frame, np.asarray(layer.crop(box)), box[0], box[1], color, 1.0)
        return frame

    return VideoClip(make_frame, duration=duration)


if __name__ == "__main__":
    test_scene = {"id": "scene_05", "type": "ending",
                  "narration": "政策降低了買房門檻，卻也把本金償還的時間往後挪。當寬限期結束，你真的有把握負擔翻倍的房貸嗎？"}
    clip = render_ending_scene("test_scenes", "ending", test_scene, duration=6.0)
    clip.write_videofile("../data/cache/test_scenes/ending_test.mp4", fps=24)
    print("Ending Scene 測試影片已產生：data/cache/test_scenes/ending_test.mp4")
