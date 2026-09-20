# Quote Scene：一句值得被看見的話，文字本身是主角
#
# 輸入：顯示文字 = scene["text"]（若有），否則 scene["narration"]。
#       rewrite.py 對 quote 的定義是「純文字重點句，無其他必要欄位」，沒有發言者／出處欄位，
#       所以畫面上不出現任何署名，也不補寫、不改寫原文。
# 畫面：靠左的 editorial 版面——青色大引號 + 白色大字。文字自動換行、太長自動縮小字級。
# 動畫：只有淡入（引號先、文字後），之後定格。沒有脈衝、光暈、位移。
#
# render_text_card 是共用的「純文字卡」：Quote 用它（帶引號），
# ranking / trend / comparison / timeline 遇到資料不合法時也用它（不帶引號、改用青色短線），
# 顯示的永遠只有旁白本身，不猜資料。
# 時間軸全部是「佔 Scene 實際時長的比例」。

import numpy as np
from moviepy import VideoClip
from PIL import Image, ImageColor, ImageDraw

from scenes import base
from scenes.hook import _blend, _font, _wrap_lines

MARGIN_X = int(base.CANVAS_WIDTH * base.SAFE_MARGIN_RATIO)
TEXT_WIDTH = base.CANVAS_WIDTH - 2 * MARGIN_X
TEXT_PX = 68
LINE_HEIGHT_RATIO = 1.5
FONT_SCALES = (1.0, 0.85, 0.72, 0.60)        # 文字太長時逐級縮小字級
MAX_BLOCK_HEIGHT = 0.50 * base.CANVAS_HEIGHT
CENTER_Y_RATIO = 0.47
MARK_PX = 300
MARK_GLYPH = "“"
MARK_GAP = 30                                # 引號墨跡底部到文字區塊頂部的距離
RULE_WIDTH = 96                              # 無引號時的青色短線
RULE_HEIGHT = 8
RULE_GAP = 56
BASELINE_OFFSET = 0.35

# 時間軸（佔總時長比例）
MARK_PHASE = (0.00, 0.14)         # 引號 / 短線先淡入
TEXT_PHASE = (0.06, 0.26)         # 文字淡入，之後定格


def _card_text(scene):
    for key in ("text", "narration"):
        value = scene.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def render_text_card(scene, duration, show_mark=True):
    text = _card_text(scene)

    for scale in FONT_SCALES:
        px = round(TEXT_PX * scale)
        lines = _wrap_lines(text, max(1, int(TEXT_WIDTH / px))) if text else []
        line_height = px * LINE_HEIGHT_RATIO
        if len(lines) * line_height <= MAX_BLOCK_HEIGHT:
            break
    font = _font(px)
    block_h = len(lines) * line_height
    block_top = base.CANVAS_HEIGHT * CENTER_Y_RATIO - block_h / 2

    # 引號字元在全形字框內有很大的留白，font.getbbox 不代表實際墨跡，所以先畫一次量出真正的墨跡範圍，
    # 再讓墨跡左緣對齊文字左邊界、墨跡底緣離文字區塊頂部 MARK_GAP。
    font_mark = _font(MARK_PX)
    probe = Image.new("L", (MARK_PX * 3, MARK_PX * 3), 0)
    ImageDraw.Draw(probe).text((MARK_PX, MARK_PX * 2), MARK_GLYPH, font=font_mark, fill=255, anchor="ls")
    ink_left, _, _, ink_bottom = probe.getbbox()
    mark_xy = (MARGIN_X - (ink_left - MARK_PX), block_top - MARK_GAP - (ink_bottom - MARK_PX * 2))

    bg = np.empty((base.CANVAS_HEIGHT, base.CANVAS_WIDTH, 3), np.uint8)
    bg[:] = ImageColor.getrgb(base.BG_COLOR)
    accent = ImageColor.getrgb(base.ACCENT_COLOR)
    white = ImageColor.getrgb(base.TEXT_COLOR_PRIMARY)
    size = (base.CANVAS_WIDTH, base.CANVAS_HEIGHT)

    def make_frame(t):
        p = t / duration if duration > 0 else 1.0
        accent_layer, white_layer = Image.new("L", size, 0), Image.new("L", size, 0)
        mark_level = int(255 * base.ease_in_out_cubic(base.phase(p, *MARK_PHASE)))
        text_level = int(255 * base.ease_in_out_cubic(base.phase(p, *TEXT_PHASE)))

        if lines:
            da = ImageDraw.Draw(accent_layer)
            if show_mark:
                da.text(mark_xy, MARK_GLYPH, font=font_mark, fill=mark_level, anchor="ls")
            else:
                y = block_top - RULE_GAP
                da.rectangle((MARGIN_X, y, MARGIN_X + RULE_WIDTH, y + RULE_HEIGHT), fill=mark_level)
            dw = ImageDraw.Draw(white_layer)
            for k, line in enumerate(lines):
                center_y = block_top + (k + 0.5) * line_height
                dw.text((MARGIN_X, center_y + BASELINE_OFFSET * px), line, font=font, fill=text_level, anchor="ls")

        frame = bg.copy()
        for layer, color in ((accent_layer, accent), (white_layer, white)):
            box = layer.getbbox()
            if box:
                _blend(frame, np.asarray(layer.crop(box)), box[0], box[1], color, 1.0)
        return frame

    return VideoClip(make_frame, duration=duration)


def render_quote_scene(video_id, segment_index, scene, duration):
    return render_text_card(scene, duration, show_mark=True)


if __name__ == "__main__":
    test_scene = {"id": "scene_03", "type": "quote",
                  "narration": "台中精華重劃區如水湳經貿園區與十四期，新案單價更是站上七、八十萬。"}
    clip = render_quote_scene("test_scenes", "quote", test_scene, duration=5.0)
    clip.write_videofile("../data/cache/test_scenes/quote_test.mp4", fps=24)
    print("Quote Scene 測試影片已產生：data/cache/test_scenes/quote_test.mp4")
