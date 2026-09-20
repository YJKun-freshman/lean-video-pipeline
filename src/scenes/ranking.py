# Ranking Scene：一眼看懂「誰排第幾、數值多少」
#
# 輸入：scene["data"] = [{"label": 名稱, "value": 數值}, ...]，至少 3 筆。
#       順序就是排名（不重新排序），長條長度 = 數值 / 最大值，數值原樣顯示，不加單位。
# 動畫：各名次由上往下依序淡入，長條同時從左長出；第 1 名用青色強調，其餘降一階。
#       長條成長是唯一的動畫資訊，沒有脈衝、光暈。
# 資料不合法（planner 應已攔截）時不猜資料，改用旁白純文字卡（scenes.quote.render_text_card）。
# 時間軸全部是「佔 Scene 實際時長的比例」。

import math

import numpy as np
from moviepy import VideoClip
from PIL import Image, ImageColor, ImageDraw

from scenes import base
from scenes.hook import _blend, _font

MAX_ROWS = 8                      # 超過就只顯示前 8 筆（手機上再多就看不清）
MIN_ROWS = 3
ROW_HEIGHT = 190                  # 字級與長條的設計基準列高（k = 實際列高 / 190）
MAX_ROW_HEIGHT = 260              # 筆數少時把列撐高放大，手機上才好讀；筆數多時等比例縮小
AREA_HEIGHT = 1320                # 排名區可用高度
CENTER_Y_RATIO = 0.47             # 排名區垂直中心（佔畫面高度）
MARGIN_X = int(base.CANVAS_WIDTH * base.SAFE_MARGIN_RATIO)

RANK_COL = 120                    # 名次欄寬（k=1 時）
RANK_PX = 84
LABEL_PX = 50
VALUE_PX = 58
BAR_HEIGHT = 20
MIN_FONT_RATIO = 0.6              # 名稱太長時最多縮到 60%，再長就加「…」

ROW_FADE = 0.14                   # 單列淡入佔總時長比例
BAR_GROW = 0.28                   # 長條成長佔總時長比例
FIRST_ROW_START = 0.05
ROW_STEP_MAX = 0.09


def _display_value(raw):
    """數值的顯示字串：字串原樣，數字用最短表示，不補單位、不四捨五入。"""
    if isinstance(raw, str):
        return raw.strip()
    text = f"{raw:.10g}"
    return f"{raw:,.0f}" if "e" in text else text


def _parse_items(data, min_items=MIN_ROWS):
    """回傳 [(label, number, display)]；資料不足或不合法回傳 None（不猜、不補）。

    trend / comparison 的 data 格式相同，直接重用這個函式（各自傳入自己的最少筆數）。
    """
    if not isinstance(data, list) or len(data) < min_items:
        return None
    items = []
    for item in data:
        if not isinstance(item, dict):
            return None
        label = item.get("label")
        label = "" if label is None else str(label).strip()
        raw = item.get("value")
        if not label or isinstance(raw, bool):
            return None
        try:
            number = float(raw)
        except (TypeError, ValueError):
            return None
        if not math.isfinite(number):
            return None
        items.append((label, number, _display_value(raw)))
    return items


def _fit_label(label, px, max_width):
    """名稱過長時先縮小字級，還放不下才截斷加「…」。回傳 (font, 顯示文字)。"""
    font = _font(px)
    width = font.getlength(label)
    if width <= max_width:
        return font, label
    font = _font(max(px * max_width / width, px * MIN_FONT_RATIO))
    text = label
    while len(text) > 1 and font.getlength(text + "…") > max_width:
        text = text[:-1]
    return font, (label if font.getlength(label) <= max_width else text + "…")


def _fallback(video_id, segment_index, scene, duration, reason):
    """各資料型 Scene（ranking / trend / comparison / timeline）共用的資料不合法退路。"""
    print(f"[Render] segment={segment_index} scene={scene.get('id', '（無id）')} type={scene.get('type')} "
          f"{reason}，不猜資料，改用旁白純文字卡")
    from scenes.quote import render_text_card
    return render_text_card(scene, duration, show_mark=False)


def render_ranking_scene(video_id, segment_index, scene, duration):
    items = _parse_items(scene.get("data"))
    if items is None:
        return _fallback(video_id, segment_index, scene, duration, "資料不足或格式不正確")
    if len(items) > MAX_ROWS:
        print(f"[Render] segment={segment_index} scene={scene.get('id', '（無id）')} type=ranking "
              f"共 {len(items)} 筆，只顯示前 {MAX_ROWS} 筆")
        items = items[:MAX_ROWS]

    n = len(items)
    max_value = max(number for _, number, _ in items)
    draw_bars = all(number >= 0 for _, number, _ in items)   # 有負值時長條會誤導，只列名次與數值

    row_h = min(MAX_ROW_HEIGHT, AREA_HEIGHT / n)
    k = row_h / ROW_HEIGHT
    top = base.CANVAS_HEIGHT * CENTER_Y_RATIO - n * row_h / 2
    col_x = MARGIN_X + round(RANK_COL * k)
    right_x = base.CANVAS_WIDTH - MARGIN_X
    bar_max = right_x - col_x
    bar_h = max(8, round(BAR_HEIGHT * k))

    font_rank, font_value = _font(RANK_PX * k), _font(VALUE_PX * k)
    rows = []
    for i, (label, number, display) in enumerate(items):
        y = top + i * row_h
        label_font, label_text = _fit_label(label, LABEL_PX * k, bar_max - font_value.getlength(display) - 24)
        rows.append({
            "y": y, "rank": str(i + 1), "label_font": label_font, "label": label_text, "value": display,
            "ratio": (number / max_value) if (draw_bars and max_value > 0 and number > 0) else 0.0,
            "label_baseline": y + 0.36 * row_h + 0.35 * LABEL_PX * k,
            "rank_baseline": y + 0.50 * row_h + 0.35 * RANK_PX * k,
            "bar_center": y + 0.76 * row_h,
        })

    step = min(ROW_STEP_MAX, 0.42 / n)

    bg = np.empty((base.CANVAS_HEIGHT, base.CANVAS_WIDTH, 3), np.uint8)
    bg[:] = ImageColor.getrgb(base.BG_COLOR)
    bg_rgb = ImageColor.getrgb(base.BG_COLOR)
    accent = ImageColor.getrgb(base.ACCENT_COLOR)
    white = ImageColor.getrgb(base.TEXT_COLOR_PRIMARY)
    secondary = ImageColor.getrgb(base.TEXT_COLOR_SECONDARY)
    muted = tuple(a + (b - a) * 0.55 for a, b in zip(accent, bg_rgb))       # 第 2 名以後的長條
    track = tuple(b + (255 - b) * 0.12 for b in bg_rgb)                     # 長條底軌
    palette = (("track", track), ("muted", muted), ("accent", accent), ("secondary", secondary), ("white", white))
    size = (base.CANVAS_WIDTH, base.CANVAS_HEIGHT)

    def make_frame(t):
        p = t / duration if duration > 0 else 1.0
        layers = {name: Image.new("L", size, 0) for name, _ in palette}
        draws = {name: ImageDraw.Draw(img) for name, img in layers.items()}

        for i, row in enumerate(rows):
            start = FIRST_ROW_START + i * step
            alpha = base.ease_in_out_cubic(base.phase(p, start, start + ROW_FADE))
            if alpha <= 0:
                continue
            level = int(255 * alpha)
            first = i == 0

            draws["accent" if first else "secondary"].text(
                (MARGIN_X, row["rank_baseline"]), row["rank"], font=font_rank, fill=level, anchor="ls")
            draws["white"].text(
                (col_x, row["label_baseline"]), row["label"], font=row["label_font"], fill=level, anchor="ls")
            draws["accent" if first else "white"].text(
                (right_x, row["label_baseline"]), row["value"], font=font_value, fill=level, anchor="rs")

            if draw_bars:
                y0, y1 = row["bar_center"] - bar_h / 2, row["bar_center"] + bar_h / 2
                draws["track"].rounded_rectangle((col_x, y0, right_x, y1), radius=bar_h / 2, fill=level)
                grow = base.ease_out_cubic(base.phase(p, start + 0.02, start + 0.02 + BAR_GROW))
                width = max(bar_max * row["ratio"], bar_h if row["ratio"] > 0 else 0) * grow
                if width >= 2:
                    draws["accent" if first else "muted"].rounded_rectangle(
                        (col_x, y0, col_x + width, y1), radius=min(bar_h / 2, width / 2), fill=level)

        frame = bg.copy()
        for name, color in palette:
            box = layers[name].getbbox()
            if box:
                _blend(frame, np.asarray(layers[name].crop(box)), box[0], box[1], color, 1.0)
        return frame

    return VideoClip(make_frame, duration=duration)


if __name__ == "__main__":
    test_scene = {"id": "scene_02", "type": "ranking", "narration": "測試排名",
                  "data": [{"label": "台北市", "value": 60}, {"label": "台中市等都會區", "value": 45},
                           {"label": "其他主要都會", "value": 40}]}
    clip = render_ranking_scene("test_scenes", "ranking", test_scene, duration=5.0)
    clip.write_videofile("../data/cache/test_scenes/ranking_test.mp4", fps=24)
    print("Ranking Scene 測試影片已產生：data/cache/test_scenes/ranking_test.mp4")
