# Big Number Scene v2：label 淡入 → 數字淡入(0) → 緩出 Count Up + 短進度條 → 放大脈衝 → 定格
#
# 所有時間點都是「佔 Scene 實際時長的比例」，不管 TTS 唸多久，動畫節奏都等比例縮放。
# 每一幀由 make_frame(t) 即時合成，不再逐幀存 PNG。
# 數字用固定字寬排版（右對齊到單位），Count Up 時位數變化不會左右抖動。

import math
from functools import lru_cache

import numpy as np
from matplotlib import font_manager
from moviepy import VideoClip
from PIL import Image, ImageColor, ImageDraw, ImageFont

from scenes import base

# 時間軸（佔總時長比例）
LABEL_PHASE = (0.00, 0.10)    # label 淡入
NUMBER_PHASE = (0.06, 0.12)   # 數字（與進度條軌道）淡入，顯示 0
COUNT_PHASE = (0.10, 0.55)    # Count Up（緩出）＋進度條同步填滿
PULSE_PHASE = (0.55, 0.68)    # 數字放大脈衝
PULSE_PEAK = 1.10             # 之後 0.68~1.0 定格

MAX_GROUP_WIDTH = 0.80 * base.CANVAS_WIDTH   # 數字＋單位的最大寬度，太長就縮小字級
UNIT_SCALE = 0.5                             # 單位字級相對數字
UNIT_GAP = 0.06                              # 數字與單位的間距（單位：數字字級）
LABEL_SCALE = 1.3                            # label 字級相對 base.FONT_SIZE_LABEL（手機上放大一點好讀）
LABEL_MAX_WIDTH = 0.80 * base.CANVAS_WIDTH
LABEL_LINE_HEIGHT = 1.4
BASELINE_OFFSET = 0.35                       # 基線到字形視覺中心的距離（單位：字級）

NUMBER_BASELINE_Y = 0.47 * base.CANVAS_HEIGHT
BAR_GAP_BELOW_BASELINE = 95                  # 進度條中心 = 數字基線 + 這個距離
BAR_WIDTH = 560                              # 固定寬度的短進度條，不做滿版
BAR_HEIGHT = 16
LABEL_GAP_BELOW_BAR = 80                     # label 第一行中心 = 進度條中心 + 這個距離
TRACK_MIX_WHITE = 0.14                       # 軌道顏色 = 背景往白色混這個比例
PAD = 60


@lru_cache(maxsize=None)
def _font_path():
    # 沿用專案 base.FONT_FAMILY 的字型選擇，與其他 Scene 字型一致
    props = font_manager.FontProperties(family=base.FONT_FAMILY, weight="bold")
    return font_manager.findfont(props)


def _font(size_px):
    return ImageFont.truetype(_font_path(), max(1, int(round(size_px))))


def _blend(frame, mask, x, y, color, opacity):
    """把 alpha mask（uint8，H×W）以 color 疊到 frame 的 (x, y) 位置。"""
    if opacity <= 0.0:
        return
    h, w = mask.shape
    region = frame[y:y + h, x:x + w].astype(np.float32)
    alpha = mask.astype(np.float32)[..., None] * (opacity / 255.0)
    out = region * (1.0 - alpha) + np.asarray(color, np.float32) * alpha
    frame[y:y + h, x:x + w] = (out + 0.5).astype(np.uint8)


def _scale_mask(mask_img, s):
    """以區域中心為軸心縮放 alpha mask。"""
    if abs(s - 1.0) < 1e-4:
        return np.asarray(mask_img)
    w, h = mask_img.size
    inv = 1.0 / s
    out = mask_img.transform((w, h), Image.Transform.AFFINE,
                             (inv, 0, w / 2 * (1 - inv), 0, inv, h / 2 * (1 - inv)),
                             resample=Image.Resampling.BICUBIC)
    return np.asarray(out)


def _wrap_by_width(text, font, max_width):
    lines, cur = [], ""
    for ch in text:
        if cur and font.getlength(cur + ch) > max_width:
            lines.append(cur)
            cur = ""
        cur += ch
    if cur:
        lines.append(cur)
    return lines


def _parse_number(value_str):
    """回傳 (最終數值, 小數位數)；不是有限數字（含 1,130、3成 這類顯示字串）回傳 (None, 0)。"""
    try:
        number = float(value_str)
    except ValueError:
        return None, 0
    if not math.isfinite(number):
        return None, 0
    mantissa = value_str.lower().split("e")[0]
    decimals = len(mantissa.split(".")[1]) if "." in mantissa else 0
    return number, decimals


def _build_label_mask(label):
    """label 文字（可多行，位於進度條下方）→ (mask 圖, region_x, region_y)；label 為空回傳 (None, 0, 0)。"""
    bar_center_y = NUMBER_BASELINE_Y + BAR_GAP_BELOW_BASELINE
    if not label:
        return None, 0, 0
    px = base.FONT_SIZE_LABEL * 100 / 72 * LABEL_SCALE
    font = _font(px)
    lines = _wrap_by_width(label, font, LABEL_MAX_WIDTH)
    line_height = px * LABEL_LINE_HEIGHT
    first_center_y = bar_center_y + LABEL_GAP_BELOW_BAR
    region_w = base.CANVAS_WIDTH
    region_h = int(len(lines) * line_height + 2 * PAD) // 2 * 2
    region_y = int(first_center_y - line_height / 2 - PAD)
    img = Image.new("L", (region_w, region_h), 0)
    d = ImageDraw.Draw(img)
    for k, line in enumerate(lines):
        center_y = PAD + line_height / 2 + k * line_height
        x = (region_w - font.getlength(line)) / 2
        d.text((x, center_y + BASELINE_OFFSET * px), line, font=font, fill=255, anchor="ls")
    return img, 0, region_y


def render_big_number_scene(video_id, segment_index, scene, duration):
    value_str = str(scene.get("value", "")).strip()
    unit = scene.get("unit", "") or ""
    label = scene.get("label", "") or ""

    final_value, decimals = _parse_number(value_str)
    is_numeric = final_value is not None

    # --- 數字 + 單位的排版（右對齊到單位，數字用固定字寬）---
    px = base.FONT_SIZE_BIG_NUMBER * 100 / 72
    for _ in range(2):    # 第 2 次是太寬時依比例縮小後重排
        font_num, font_unit = _font(px), _font(px * UNIT_SCALE)
        digit_pitch = max(font_num.getlength(d) for d in "0123456789")

        def advance(ch, _font_num=font_num, _pitch=digit_pitch):
            return _pitch if ch.isdigit() else _font_num.getlength(ch)

        number_w = sum(advance(ch) for ch in value_str)
        unit_w = font_unit.getlength(unit) if unit else 0.0
        gap = px * UNIT_GAP if unit else 0.0
        group_w = number_w + gap + unit_w
        if group_w <= MAX_GROUP_WIDTH:
            break
        px *= MAX_GROUP_WIDTH / group_w

    region_w = int(group_w + 2 * max(PAD, 0.12 * group_w)) // 2 * 2
    region_h = int(1.3 * px + 2 * PAD) // 2 * 2
    region_x = (base.CANVAS_WIDTH - region_w) // 2
    region_y = int(NUMBER_BASELINE_Y - BASELINE_OFFSET * px - region_h / 2)
    local_baseline = region_h / 2 + BASELINE_OFFSET * px
    number_right = (region_w - group_w) / 2 + number_w

    def number_mask(text):
        img = Image.new("L", (region_w, region_h), 0)
        d = ImageDraw.Draw(img)
        x = number_right
        for ch in reversed(text):
            x -= advance(ch)
            d.text((x, local_baseline), ch, font=font_num, fill=255, anchor="ls")
        if unit:
            d.text((number_right + gap, local_baseline), unit, font=font_unit, fill=255, anchor="ls")
        return img

    label_img, label_x, label_y = _build_label_mask(label)
    label_mask = np.asarray(label_img) if label_img is not None else None

    # --- 進度條（固定寬度短條）---
    bar_x = (base.CANVAS_WIDTH - BAR_WIDTH) // 2
    bar_y = int(NUMBER_BASELINE_Y + BAR_GAP_BELOW_BASELINE - BAR_HEIGHT / 2)
    bar_radius = BAR_HEIGHT / 2
    track_img = Image.new("L", (BAR_WIDTH, BAR_HEIGHT), 0)
    ImageDraw.Draw(track_img).rounded_rectangle((0, 0, BAR_WIDTH - 1, BAR_HEIGHT - 1), radius=bar_radius, fill=255)
    track_mask = np.asarray(track_img)

    def fill_mask(u):
        width = BAR_WIDTH * u
        if width < 1.0:
            return None
        img = Image.new("L", (BAR_WIDTH, BAR_HEIGHT), 0)
        ImageDraw.Draw(img).rounded_rectangle((0, 0, max(width - 1, 1), BAR_HEIGHT - 1),
                                              radius=min(bar_radius, width / 2), fill=255)
        return np.asarray(img)

    bg = np.empty((base.CANVAS_HEIGHT, base.CANVAS_WIDTH, 3), np.uint8)
    bg[:] = ImageColor.getrgb(base.BG_COLOR)
    accent = ImageColor.getrgb(base.ACCENT_COLOR)
    white = ImageColor.getrgb(base.TEXT_COLOR_PRIMARY)
    track_color = tuple(c + (255 - c) * TRACK_MIX_WHITE for c in ImageColor.getrgb(base.BG_COLOR))

    def display_text(u):
        if not is_numeric:
            return value_str
        if u >= 1.0:
            return value_str                     # 最終畫面與原始字串完全一致
        text = f"{final_value * u:.{decimals}f}"
        return text.lstrip("-") if float(text) == 0 else text

    def make_frame(t):
        p = t / duration if duration > 0 else 1.0
        frame = bg.copy()

        label_alpha = base.ease_in_out_cubic(base.phase(p, *LABEL_PHASE))
        number_alpha = base.ease_in_out_cubic(base.phase(p, *NUMBER_PHASE))
        u = base.ease_out_cubic(base.phase(p, *COUNT_PHASE))
        s = base.pulse_scale(base.phase(p, *PULSE_PHASE), PULSE_PEAK)

        if label_mask is not None:
            _blend(frame, label_mask, label_x, label_y, white, label_alpha)

        if is_numeric:
            _blend(frame, track_mask, bar_x, bar_y, track_color, number_alpha)
            fill = fill_mask(u)
            if fill is not None:
                _blend(frame, fill, bar_x, bar_y, accent, number_alpha)

        _blend(frame, _scale_mask(number_mask(display_text(u)), s), region_x, region_y, accent, number_alpha)
        return frame

    return VideoClip(make_frame, duration=duration)


if __name__ == "__main__":
    test_scene = {"id": "scene_02", "value": "11.3", "unit": "倍", "label": "房價所得比"}
    clip = render_big_number_scene("test_scenes", "bignum", test_scene, duration=4.0)
    clip.write_videofile("../data/cache/test_scenes/big_number_test.mp4", fps=24)
    print("Big Number Scene 測試影片已產生：data/cache/test_scenes/big_number_test.mp4")
