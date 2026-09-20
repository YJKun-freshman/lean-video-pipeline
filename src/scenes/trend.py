# Trend Scene：往上還是往下、變化多少
#
# 輸入：scene["data"] = [{"label": 時間點, "value": 數值}, ...]，至少 3 筆，依時間順序（不重新排序）。
# 畫面：折線由左畫到右，每個點標示原始數值；折線畫完後出現「變化摘要」——
#       上升/下降箭頭 + 末期減首期的差 + 百分比，以及「首期 → 末期」。
#       差值與百分比都由資料直接算出，沒有的資料不補；只有 0 的首期不算百分比。
# 顏色沿用 base：上升 ACCENT_COLOR_UP、下降 ACCENT_COLOR_DOWN；持平不畫箭頭。
# 折線的 Y 軸是「最小值到最大值」拉滿，用來看走勢；實際數字都標在點上。
# 資料不合法（planner 應已攔截）時不猜資料，改用旁白純文字卡。
# 時間軸全部是「佔 Scene 實際時長的比例」。

import math

import numpy as np
from moviepy import VideoClip
from PIL import Image, ImageColor, ImageDraw

from scenes import base
from scenes.hook import _blend, _font
from scenes.ranking import _display_value, _fallback, _fit_label, _parse_items

MIN_POINTS = 3
MARGIN_X = int(base.CANVAS_WIDTH * base.SAFE_MARGIN_RATIO)
PLOT_INSET = 40
PLOT_LEFT = MARGIN_X + PLOT_INSET
PLOT_RIGHT = base.CANVAS_WIDTH - MARGIN_X - PLOT_INSET
PLOT_TOP = 860                     # 最大值所在的 Y
PLOT_BOTTOM = 1400                 # 最小值所在的 Y
X_LABEL_CENTER_Y = 1495

LINE_WIDTH = 10
DOT_RADIUS = 13
LAST_DOT_RADIUS = 19
VALUE_PX = 44
LAST_VALUE_PX = 58
X_LABEL_PX = 38
MIN_X_LABEL_PX = 32                # 再小手機上就看不清，寧可疏化也不再縮
VALUE_LABEL_GAP = 56               # 數值標籤中心在點上方多遠

HEAD_ARROW_W = 84
HEAD_ARROW_H = 76
HEAD_GAP = 28
HEAD_NUMBER_PX = 150
HEAD_PCT_PX = 64
HEAD_CAPTION_PX = 42
HEAD_NUMBER_CY = 470
HEAD_PCT_CY = 610
HEAD_CAPTION_CY = 705
BASELINE_OFFSET = 0.35

# 時間軸（佔總時長比例）
X_LABEL_PHASE = (0.02, 0.14)       # X 軸標籤淡入
LINE_PHASE = (0.08, 0.50)          # 折線由左畫到右
LAST_POINT_PHASE = (0.47, 0.57)    # 折線畫到終點後，末期的圓點與數值淡入
HEADLINE_PHASE = (0.58, 0.70)      # 變化摘要淡入，之後定格


def _decimals(displays):
    """顯示字串中最多的小數位數，讓差值的精度和資料一致。"""
    best = 0
    for text in displays:
        mantissa = text.lower().split("e")[0]
        if "." in mantissa:
            best = max(best, min(len(mantissa.split(".")[1]), 4))
    return best


def _signed(value, decimals):
    sign = "+" if value > 0 else "-"
    return f"{sign}{abs(value):.{decimals}f}"


def _clamp_x(x, width):
    """標籤置中在 x，但不超出左右安全邊界（首尾的長標籤會被往內推）。"""
    half = width / 2
    return min(max(x, MARGIN_X + half), base.CANVAS_WIDTH - MARGIN_X - half)


def _fit_x_labels(labels):
    """X 軸標籤：先縮小字級，縮到底還擠才疏化（由末期往前等間隔取，保證含末期）。

    以「安全區寬度 ÷ 顯示的標籤數」當每個標籤可用的寬度，首尾標籤被往內推時也不會互相疊到。
    回傳 (font, 要顯示的索引集合)。
    """
    n = len(labels)
    usable = base.CANVAS_WIDTH - 2 * MARGIN_X
    for step in range(1, n + 1):
        shown = {i for i in range(n) if (n - 1 - i) % step == 0}
        px = X_LABEL_PX
        while True:
            font = _font(px)
            if max(font.getlength(labels[i]) for i in shown) <= 0.95 * usable / len(shown):
                return font, shown
            if px <= MIN_X_LABEL_PX:
                break
            px = max(MIN_X_LABEL_PX, px * 0.92)
    return font, shown


def render_trend_scene(video_id, segment_index, scene, duration):
    items = _parse_items(scene.get("data"), min_items=MIN_POINTS)
    if items is None:
        return _fallback(video_id, segment_index, scene, duration, "資料不足或格式不正確")

    n = len(items)
    labels = [label for label, _, _ in items]
    numbers = [number for _, number, _ in items]
    displays = [display for _, _, display in items]

    # --- 折線幾何 ---
    spacing = (PLOT_RIGHT - PLOT_LEFT) / (n - 1)
    xs = [PLOT_LEFT + i * spacing for i in range(n)]
    vmin, vmax = min(numbers), max(numbers)
    if vmax == vmin:
        ys = [(PLOT_TOP + PLOT_BOTTOM) / 2] * n
    else:
        ys = [PLOT_BOTTOM - (v - vmin) / (vmax - vmin) * (PLOT_BOTTOM - PLOT_TOP) for v in numbers]
    points = list(zip(xs, ys))
    cum = [0.0]
    for (x0, y0), (x1, y1) in zip(points, points[1:]):
        cum.append(cum[-1] + math.hypot(x1 - x0, y1 - y0))
    total = cum[-1]
    dot_r = max(4, min(DOT_RADIUS, spacing * 0.4))
    last_r = max(dot_r + 2, min(LAST_DOT_RADIUS, spacing * 0.55))

    # --- 標籤（太擠就只留必要的）---
    font_value, font_last = _font(VALUE_PX), _font(LAST_VALUE_PX)
    value_widths = [font_value.getlength(d) for d in displays]
    if max(value_widths) <= spacing * 0.9:
        value_idx = set(range(n))
    else:
        value_idx = {0, n - 1, numbers.index(vmin), numbers.index(vmax)}
    font_x, x_idx = _fit_x_labels(labels)

    # --- 變化摘要（由資料直接算）---
    change = numbers[-1] - numbers[0]
    direction = (change > 0) - (change < 0)
    decimals = _decimals(displays)
    pct_text = None
    if direction != 0 and numbers[0] != 0:
        pct = change / abs(numbers[0]) * 100
        pct_text = f"{'+' if change > 0 else '-'}{abs(pct):.0f}%" if abs(pct) >= 1000 else \
                   f"{'+' if change > 0 else '-'}{abs(pct):.1f}%"
    head_text = "持平" if direction == 0 else _signed(change, decimals)
    head_px = HEAD_NUMBER_PX
    while True:                                  # 數字太長時縮小，讓「箭頭＋數字」不超出安全區
        font_head = _font(head_px)
        arrow_w = HEAD_ARROW_W if direction else 0
        group_w = arrow_w + (HEAD_GAP if direction else 0) + font_head.getlength(head_text)
        if group_w <= base.CANVAS_WIDTH - 2 * MARGIN_X or head_px <= 60:
            break
        head_px *= 0.9
    font_pct = _font(HEAD_PCT_PX)
    font_caption, caption = _fit_label(f"{labels[0]} → {labels[-1]}", HEAD_CAPTION_PX,
                                       base.CANVAS_WIDTH - 2 * MARGIN_X)

    bg = np.empty((base.CANVAS_HEIGHT, base.CANVAS_WIDTH, 3), np.uint8)
    bg[:] = ImageColor.getrgb(base.BG_COLOR)
    up_color = ImageColor.getrgb(base.ACCENT_COLOR_UP)
    down_color = ImageColor.getrgb(base.ACCENT_COLOR_DOWN)
    palette = (("secondary", ImageColor.getrgb(base.TEXT_COLOR_SECONDARY)),
               ("accent", ImageColor.getrgb(base.ACCENT_COLOR)),
               ("dir", up_color if direction > 0 else down_color),
               ("white", ImageColor.getrgb(base.TEXT_COLOR_PRIMARY)))
    size = (base.CANVAS_WIDTH, base.CANVAS_HEIGHT)

    def partial_polyline(s):
        pts = [points[0]]
        for i in range(1, n):
            if s >= cum[i]:
                pts.append(points[i])
            else:
                f = (s - cum[i - 1]) / (cum[i] - cum[i - 1]) if cum[i] > cum[i - 1] else 0.0
                (x0, y0), (x1, y1) = points[i - 1], points[i]
                pts.append((x0 + (x1 - x0) * f, y0 + (y1 - y0) * f))
                break
        return pts

    def circle(draw, center, r, level):
        draw.ellipse((center[0] - r, center[1] - r, center[0] + r, center[1] + r), fill=level)

    def make_frame(t):
        p = t / duration if duration > 0 else 1.0
        layers = {name: Image.new("L", size, 0) for name, _ in palette}
        draws = {name: ImageDraw.Draw(img) for name, img in layers.items()}

        x_level = int(255 * base.ease_in_out_cubic(base.phase(p, *X_LABEL_PHASE)))
        if x_level > 0:
            for i in x_idx:
                draws["secondary"].text((_clamp_x(xs[i], font_x.getlength(labels[i])),
                                         X_LABEL_CENTER_Y + BASELINE_OFFSET * X_LABEL_PX),
                                        labels[i], font=font_x, fill=x_level, anchor="ms")

        u = base.ease_in_out_cubic(base.phase(p, *LINE_PHASE))
        if u > 0:
            s = total * u
            pts = partial_polyline(s)
            draws["accent"].line(pts, fill=255, width=LINE_WIDTH, joint="curve")
            circle(draws["accent"], pts[0], LINE_WIDTH / 2, 255)
            circle(draws["accent"], pts[-1], LINE_WIDTH / 2, 255)
            # 折線剛好結束在末期那點，所以點與數值的淡入用「折線長度 + 終點後的淡入量」來算，
            # 末期才不會永遠卡在 0
            ramp = max(total * 0.12, 1.0)
            s_ext = s + ramp * base.phase(p, *LAST_POINT_PHASE)
            for i in range(n):
                if s_ext < cum[i]:
                    continue
                reached = base.clamp01((s_ext - cum[i]) / ramp)
                level = int(255 * min(1.0, (s_ext - cum[i] + 6) / 30))
                last = i == n - 1
                circle(draws["white" if last else "accent"], points[i], last_r if last else dot_r, level)
                if i in value_idx:
                    font = font_last if last else font_value
                    px = LAST_VALUE_PX if last else VALUE_PX
                    draws["accent" if last else "white"].text(
                        (_clamp_x(xs[i], font.getlength(displays[i])),
                         ys[i] - VALUE_LABEL_GAP - (last_r - dot_r if last else 0) + BASELINE_OFFSET * px),
                        displays[i], font=font, fill=int(255 * base.ease_in_out_cubic(reached)), anchor="ms")

        h_level = int(255 * base.ease_in_out_cubic(base.phase(p, *HEADLINE_PHASE)))
        if h_level > 0:
            left = (base.CANVAS_WIDTH - group_w) / 2
            text_x = left + (arrow_w + HEAD_GAP if direction else 0)
            baseline = HEAD_NUMBER_CY + BASELINE_OFFSET * head_px
            draws["dir" if direction else "white"].text(
                (text_x, baseline), head_text, font=font_head, fill=h_level, anchor="ls")
            if direction:
                top, bottom = HEAD_NUMBER_CY - HEAD_ARROW_H / 2, HEAD_NUMBER_CY + HEAD_ARROW_H / 2
                cx = left + HEAD_ARROW_W / 2
                tri = ([(cx, top), (cx + HEAD_ARROW_W / 2, bottom), (cx - HEAD_ARROW_W / 2, bottom)]
                       if direction > 0 else
                       [(cx, bottom), (cx + HEAD_ARROW_W / 2, top), (cx - HEAD_ARROW_W / 2, top)])
                draws["dir"].polygon(tri, fill=h_level)
            if pct_text:
                draws["white"].text((base.CANVAS_WIDTH / 2, HEAD_PCT_CY + BASELINE_OFFSET * HEAD_PCT_PX),
                                    pct_text, font=font_pct, fill=h_level, anchor="ms")
            draws["secondary"].text((base.CANVAS_WIDTH / 2, HEAD_CAPTION_CY + BASELINE_OFFSET * HEAD_CAPTION_PX),
                                    caption, font=font_caption, fill=h_level, anchor="ms")

        frame = bg.copy()
        for name, color in palette:
            box = layers[name].getbbox()
            if box:
                _blend(frame, np.asarray(layers[name].crop(box)), box[0], box[1], color, 1.0)
        return frame

    return VideoClip(make_frame, duration=duration)


if __name__ == "__main__":
    test_scene = {"id": "scene_02", "type": "trend", "narration": "測試趨勢",
                  "data": [{"label": "2023", "value": 9.2}, {"label": "2024", "value": 10.1},
                           {"label": "2025", "value": 11.3}]}
    clip = render_trend_scene("test_scenes", "trend", test_scene, duration=6.0)
    clip.write_videofile("../data/cache/test_scenes/trend_test.mp4", fps=24)
    print("Trend Scene 測試影片已產生：data/cache/test_scenes/trend_test.mp4")
