# Timeline Scene：事件依時間順序發生
#
# 輸入：scene["data"] = [{"time": 時間點, "event": 事件描述}, ...]，至少 3 筆，順序即時間順序
#       （不重新排序，因為 time 是自由文字，無法可靠比較先後）。
# 畫面：手機直式的垂直時間軸——左側一條線串起節點，右側每個節點上方是青色時間、下方是白色事件文字。
# 動畫：節點由上往下依序出現，節點之間的連線隨閱讀順序往下延伸；這個順序本身就是資訊。
#       時間或事件文字過長會換行、整體過高會等比例縮小；超過 8 筆只顯示前 8 筆。
# 資料不合法（planner 應已攔截）時不猜資料，改用旁白純文字卡。
# 時間軸全部是「佔 Scene 實際時長的比例」。

import numpy as np
from moviepy import VideoClip
from PIL import Image, ImageColor, ImageDraw

from scenes import base
from scenes.hook import _blend, _font, _wrap_lines
from scenes.ranking import _fallback

MIN_ITEMS = 3
MAX_ITEMS = 8
MARGIN_X = int(base.CANVAS_WIDTH * base.SAFE_MARGIN_RATIO)
LINE_X = MARGIN_X + 40
TEXT_X = LINE_X + 72
TEXT_WIDTH = base.CANVAS_WIDTH - MARGIN_X - TEXT_X
TIME_PX = 54
EVENT_PX = 50
LINE_HEIGHT_RATIO = 1.45
ITEM_GAP = 64                     # 相鄰兩筆之間的空白
DOT_RADIUS = 15
LINE_WIDTH = 6
AREA_HEIGHT = 1400
CENTER_Y_RATIO = 0.47
SCALES = (1.7, 1.5, 1.3, 1.15, 1.0, 0.9, 0.8, 0.7, 0.6)   # 由大往小找第一個放得進的：筆數少時放大、筆數多時縮小
BASELINE_OFFSET = 0.35

# 時間軸（佔總時長比例）
FIRST_ITEM_START = 0.05
STEP_MAX = 0.12
ITEM_FADE = 0.10                  # 單一節點與文字淡入佔總時長比例


def _parse_items(data):
    """回傳 [(time_text, event_text)]；資料不足或不合法回傳 None（不猜、不補）。"""
    if not isinstance(data, list) or len(data) < MIN_ITEMS:
        return None
    items = []
    for item in data:
        if not isinstance(item, dict):
            return None
        time_text, event_text = item.get("time"), item.get("event")
        if isinstance(time_text, bool) or isinstance(event_text, bool):
            return None
        time_text = "" if time_text is None else str(time_text).strip()
        event_text = "" if event_text is None else str(event_text).strip()
        if not time_text or not event_text:
            return None
        items.append((time_text, event_text))
    return items


def _layout(items):
    """挑一個放得進畫面的縮放比例，回傳 (rows, font_time, font_event, px_time, px_event, scale)。

    rows: 每一筆的 {time_lines, event_lines, top, dot_y}，top 是該筆區塊頂端的 Y。
    """
    for scale in SCALES:
        px_t, px_e = round(TIME_PX * scale), round(EVENT_PX * scale)
        lh_t, lh_e = px_t * LINE_HEIGHT_RATIO, px_e * LINE_HEIGHT_RATIO
        gap = ITEM_GAP * scale
        rows, total = [], 0.0
        for time_text, event_text in items:
            t_lines = _wrap_lines(time_text, max(1, int(TEXT_WIDTH / px_t)))
            e_lines = _wrap_lines(event_text, max(1, int(TEXT_WIDTH / px_e)))
            height = len(t_lines) * lh_t + len(e_lines) * lh_e
            rows.append({"time_lines": t_lines, "event_lines": e_lines, "height": height, "lh_t": lh_t, "lh_e": lh_e})
            total += height + gap
        total -= gap
        if total <= AREA_HEIGHT:
            break
    y = base.CANVAS_HEIGHT * CENTER_Y_RATIO - total / 2
    for row in rows:
        row["top"] = y
        row["dot_y"] = y + row["lh_t"] / 2
        y += row["height"] + gap
    return rows, _font(px_t), _font(px_e), px_t, px_e, scale


def render_timeline_scene(video_id, segment_index, scene, duration):
    items = _parse_items(scene.get("data"))
    if items is None:
        return _fallback(video_id, segment_index, scene, duration, "資料不足或格式不正確")
    if len(items) > MAX_ITEMS:
        print(f"[Render] segment={segment_index} scene={scene.get('id', '（無id）')} type=timeline "
              f"共 {len(items)} 筆，只顯示前 {MAX_ITEMS} 筆")
        items = items[:MAX_ITEMS]

    n = len(items)
    rows, font_time, font_event, px_t, px_e, scale = _layout(items)
    dot_r = DOT_RADIUS * min(scale, 1.5)
    line_w = LINE_WIDTH * min(scale, 1.5)
    step = min(STEP_MAX, 0.55 / n)
    starts = [FIRST_ITEM_START + i * step for i in range(n)]

    bg = np.empty((base.CANVAS_HEIGHT, base.CANVAS_WIDTH, 3), np.uint8)
    bg[:] = ImageColor.getrgb(base.BG_COLOR)
    bg_rgb = ImageColor.getrgb(base.BG_COLOR)
    accent = ImageColor.getrgb(base.ACCENT_COLOR)
    muted = tuple(a + (b - a) * 0.55 for a, b in zip(accent, bg_rgb))
    palette = (("muted", muted), ("accent", accent), ("white", ImageColor.getrgb(base.TEXT_COLOR_PRIMARY)))
    size = (base.CANVAS_WIDTH, base.CANVAS_HEIGHT)

    def make_frame(t):
        p = t / duration if duration > 0 else 1.0
        layers = {name: Image.new("L", size, 0) for name, _ in palette}
        draws = {name: ImageDraw.Draw(img) for name, img in layers.items()}

        for i, row in enumerate(rows):
            alpha = base.ease_in_out_cubic(base.phase(p, starts[i], starts[i] + ITEM_FADE))
            if alpha <= 0:
                continue
            level = int(255 * alpha)

            draws["accent"].ellipse((LINE_X - dot_r, row["dot_y"] - dot_r,
                                     LINE_X + dot_r, row["dot_y"] + dot_r), fill=level)
            y = row["top"]
            for line in row["time_lines"]:
                draws["accent"].text((TEXT_X, y + row["lh_t"] / 2 + BASELINE_OFFSET * px_t), line,
                                     font=font_time, fill=level, anchor="ls")
                y += row["lh_t"]
            for line in row["event_lines"]:
                draws["white"].text((TEXT_X, y + row["lh_e"] / 2 + BASELINE_OFFSET * px_e), line,
                                    font=font_event, fill=level, anchor="ls")
                y += row["lh_e"]

            if i + 1 < n:      # 連到下一個節點的線，隨下一筆出現的節奏往下延伸
                grow = base.ease_in_out_cubic(base.phase(p, starts[i] + ITEM_FADE * 0.6, starts[i + 1] + ITEM_FADE * 0.4))
                y0 = row["dot_y"] + dot_r
                y1 = rows[i + 1]["dot_y"] - dot_r
                if grow > 0 and y1 > y0:
                    draws["muted"].rectangle((LINE_X - line_w / 2, y0, LINE_X + line_w / 2, y0 + (y1 - y0) * grow),
                                             fill=255)

        frame = bg.copy()
        for name, color in palette:
            box = layers[name].getbbox()
            if box:
                _blend(frame, np.asarray(layers[name].crop(box)), box[0], box[1], color, 1.0)
        return frame

    return VideoClip(make_frame, duration=duration)


if __name__ == "__main__":
    test_scene = {"id": "scene_04", "type": "timeline", "narration": "測試時間軸",
                  "data": [{"time": "2024", "event": "政策宣布"}, {"time": "2025", "event": "試行"},
                           {"time": "2026", "event": "正式實施"}]}
    clip = render_timeline_scene("test_scenes", "timeline", test_scene, duration=6.0)
    clip.write_videofile("../data/cache/test_scenes/timeline_test.mp4", fps=24)
    print("Timeline Scene 測試影片已產生：data/cache/test_scenes/timeline_test.mp4")
