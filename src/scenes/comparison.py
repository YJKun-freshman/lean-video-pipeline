# Comparison Scene：A 與 B 的差異
#
# 輸入：scene["data"] = [{"label": 名稱, "value": 數值}, ...]，剛好 2 筆。
# 畫面：左右兩根直條，數值標在條上方、名稱在下方，較大者用青色、較小者降一階；
#       兩根條長度 = 數值 / 較大值。上方的「差距」由兩個數值直接算出（差、倍數），
#       倍數只在兩者都 > 0 時才顯示。不產生任何資料裡沒有的比較數據。
# 有負值時直條會誤導，只列名稱與數值、不畫直條。
# 資料不合法（planner 應已攔截）時不猜資料，改用旁白純文字卡。
# 時間軸全部是「佔 Scene 實際時長的比例」。

import numpy as np
from moviepy import VideoClip
from PIL import Image, ImageColor, ImageDraw

from scenes import base
from scenes.hook import _blend, _font
from scenes.ranking import _fallback, _fit_label, _parse_items
from scenes.trend import _decimals

ITEM_COUNT = 2
MARGIN_X = int(base.CANVAS_WIDTH * base.SAFE_MARGIN_RATIO)
COLUMN_CENTER_RATIO = (0.29, 0.71)
BAR_WIDTH = 240
BAR_MAX_HEIGHT = 560
BAR_MIN_HEIGHT = 10
BASE_Y = 1330                     # 兩根條共用的底線
VALUE_PX = 110
MIN_VALUE_PX = 48
VALUE_MAX_WIDTH = 420             # 單一數值最大寬度（兩欄中心相距約 450）
VALUE_GAP = 70                    # 數值中心在條頂上方多遠
LABEL_PX = 56
LABEL_CENTER_Y = BASE_Y + 90
LABEL_MAX_WIDTH = 420
VS_PX = 48
PILL_CENTER_Y = 450
PILL_TEXT_PX = 88
PILL_PAD_X = 64
PILL_HEIGHT = 140
RATIO_CENTER_Y = 585
RATIO_PX = 48
RULE_HEIGHT = 4
BASELINE_OFFSET = 0.35

# 時間軸（佔總時長比例）
LABEL_PHASE = (0.02, 0.14)        # 名稱、底線、vs 淡入
VALUE_PHASE = (0.10, 0.24)        # 數值淡入
BAR_PHASE = (0.08, 0.46)          # 兩根條同時從底線長出
DIFF_PHASE = (0.52, 0.66)         # 差距淡入，之後定格


def render_comparison_scene(video_id, segment_index, scene, duration):
    items = _parse_items(scene.get("data"), min_items=ITEM_COUNT)
    if items is None or len(items) != ITEM_COUNT:
        return _fallback(video_id, segment_index, scene, duration, "資料必須剛好 2 筆且格式正確")

    numbers = [number for _, number, _ in items]
    displays = [display for _, _, display in items]
    draw_bars = all(number >= 0 for number in numbers)
    top_value = max(numbers)
    equal = numbers[0] == numbers[1]
    centers = [base.CANVAS_WIDTH * r for r in COLUMN_CENTER_RATIO]
    heights = [
        max(BAR_MAX_HEIGHT * number / top_value, BAR_MIN_HEIGHT if number > 0 else 0)
        if (draw_bars and top_value > 0) else 0.0
        for number in numbers
    ]
    is_top = [equal or number == top_value for number in numbers]   # 較大者（相同時兩者都算）

    # --- 差距文字：由兩個數值直接算 ---
    diff = abs(numbers[0] - numbers[1])
    pill_text = "兩者相同" if equal else f"差 {diff:.{_decimals(displays)}f}"
    lo = min(numbers)
    ratio_text = None
    if not equal and lo > 0 and round(top_value / lo, 1) > 1.0:    # 四捨五入後仍是 1.0 倍沒有資訊量
        ratio_text = f"約 {top_value / lo:.1f} 倍"

    # 數值字級：兩個數字都放得進各自的欄位；只縮小、絕不截斷（截斷數字等於改資料）
    value_px = VALUE_PX
    while value_px > MIN_VALUE_PX and max(_font(value_px).getlength(d) for d in displays) > VALUE_MAX_WIDTH:
        value_px = max(MIN_VALUE_PX, value_px * 0.92)
    font_value, font_pill, font_vs = _font(value_px), _font(PILL_TEXT_PX), _font(VS_PX)
    font_ratio = _font(RATIO_PX)
    label_fonts, label_texts = zip(*(_fit_label(label, LABEL_PX, LABEL_MAX_WIDTH) for label, _, _ in items))
    pill_w = font_pill.getlength(pill_text) + 2 * PILL_PAD_X

    bg = np.empty((base.CANVAS_HEIGHT, base.CANVAS_WIDTH, 3), np.uint8)
    bg[:] = ImageColor.getrgb(base.BG_COLOR)
    bg_rgb = ImageColor.getrgb(base.BG_COLOR)
    accent = ImageColor.getrgb(base.ACCENT_COLOR)
    muted = tuple(a + (b - a) * 0.55 for a, b in zip(accent, bg_rgb))
    track = tuple(b + (255 - b) * 0.12 for b in bg_rgb)
    palette = (("track", track), ("muted", muted), ("secondary", ImageColor.getrgb(base.TEXT_COLOR_SECONDARY)),
               ("accent", accent), ("white", ImageColor.getrgb(base.TEXT_COLOR_PRIMARY)))
    size = (base.CANVAS_WIDTH, base.CANVAS_HEIGHT)

    def make_frame(t):
        p = t / duration if duration > 0 else 1.0
        layers = {name: Image.new("L", size, 0) for name, _ in palette}
        draws = {name: ImageDraw.Draw(img) for name, img in layers.items()}

        label_level = int(255 * base.ease_in_out_cubic(base.phase(p, *LABEL_PHASE)))
        value_level = int(255 * base.ease_in_out_cubic(base.phase(p, *VALUE_PHASE)))
        grow = base.ease_out_cubic(base.phase(p, *BAR_PHASE))
        diff_level = int(255 * base.ease_in_out_cubic(base.phase(p, *DIFF_PHASE)))

        if label_level > 0:
            draws["track"].rectangle((MARGIN_X, BASE_Y, base.CANVAS_WIDTH - MARGIN_X, BASE_Y + RULE_HEIGHT),
                                     fill=label_level)
            draws["secondary"].text((base.CANVAS_WIDTH / 2, BASE_Y - 60 + BASELINE_OFFSET * VS_PX), "vs",
                                    font=font_vs, fill=label_level, anchor="ms")
            for i in range(ITEM_COUNT):
                draws["white"].text((centers[i], LABEL_CENTER_Y + BASELINE_OFFSET * LABEL_PX), label_texts[i],
                                    font=label_fonts[i], fill=label_level, anchor="ms")

        for i in range(ITEM_COUNT):
            if draw_bars:
                h = heights[i] * grow
                if h >= 2:
                    draws["accent" if is_top[i] else "muted"].rounded_rectangle(
                        (centers[i] - BAR_WIDTH / 2, BASE_Y - h, centers[i] + BAR_WIDTH / 2, BASE_Y),
                        radius=min(16, h / 2), fill=255, corners=(True, True, False, False))
                value_center = BASE_Y - heights[i] - VALUE_GAP
            else:
                value_center = BASE_Y - 200
            if value_level > 0:
                draws["accent" if is_top[i] else "white"].text(
                    (centers[i], value_center + BASELINE_OFFSET * value_px), displays[i],
                    font=font_value, fill=value_level, anchor="ms")

        if diff_level > 0:
            cx = base.CANVAS_WIDTH / 2
            draws["accent"].rounded_rectangle(
                (cx - pill_w / 2, PILL_CENTER_Y - PILL_HEIGHT / 2, cx + pill_w / 2, PILL_CENTER_Y + PILL_HEIGHT / 2),
                radius=PILL_HEIGHT / 2, outline=diff_level, width=5)
            draws["accent"].text((cx, PILL_CENTER_Y + BASELINE_OFFSET * PILL_TEXT_PX), pill_text,
                                 font=font_pill, fill=diff_level, anchor="ms")
            if ratio_text:
                draws["secondary"].text((cx, RATIO_CENTER_Y + BASELINE_OFFSET * RATIO_PX), ratio_text,
                                        font=font_ratio, fill=diff_level, anchor="ms")

        frame = bg.copy()
        for name, color in palette:
            box = layers[name].getbbox()
            if box:
                _blend(frame, np.asarray(layers[name].crop(box)), box[0], box[1], color, 1.0)
        return frame

    return VideoClip(make_frame, duration=duration)


if __name__ == "__main__":
    test_scene = {"id": "scene_04", "type": "comparison", "narration": "測試比較",
                  "data": [{"label": "台北", "value": 11.3}, {"label": "高雄", "value": 7.2}]}
    clip = render_comparison_scene("test_scenes", "comparison", test_scene, duration=6.0)
    clip.write_videofile("../data/cache/test_scenes/comparison_test.mp4", fps=24)
    print("Comparison Scene 測試影片已產生：data/cache/test_scenes/comparison_test.mp4")
