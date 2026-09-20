# Hook Scene v2：背景柔光 → 兩段文字（第二段強調色）→ 放大脈衝 → 定格
#
# 所有時間點都是「佔 Scene 實際時長的比例」，TTS 唸 2 秒或 7 秒，動畫節奏都等比例縮放。
# 每一幀由 make_frame(t) 即時合成，不再逐幀存 PNG。

from functools import lru_cache

import numpy as np
from matplotlib import font_manager
from moviepy import VideoClip
from PIL import Image, ImageColor, ImageDraw, ImageFont

from scenes import base

# 時間軸（佔總時長比例）
GLOW_PHASE = (0.00, 0.12)     # 背景柔光浮現
PART1_PHASE = (0.08, 0.28)    # 第一段文字淡入
PART2_PHASE = (0.30, 0.50)    # 第二段文字淡入（強調色）
PULSE_PHASE = (0.55, 0.68)    # 整段文字放大脈衝
PULSE_PEAK = 1.08             # 之後 0.68~1.0 定格

GLOW_MAX_MIX = 0.20           # 光暈中心最多往青色混多少
GLOW_RADIUS_X = 0.75 * base.CANVAS_WIDTH
GLOW_RADIUS_Y = 0.42 * base.CANVAS_HEIGHT

LINE_WIDTH = 0.72 * base.CANVAS_WIDTH        # 單行最大寬度，留出脈衝放大後仍在安全區內的空間
LINE_HEIGHT_RATIO = 1.45
MAX_BLOCK_HEIGHT = 0.60 * base.CANVAS_HEIGHT
FONT_SCALES = (1.0, 0.85, 0.72, 0.60)        # 文字太長時逐級縮小字級
REGION_PAD = 100                             # 文字區域外的緩衝，容納脈衝放大
BASELINE_OFFSET = 0.35                       # 基線到字形視覺中心的距離（單位：字級）

MIN_PART_CHARS = 3
_MID_PUNCT = "，、；：,;:"
_END_PUNCT = "。！？!?…"
_SPLIT_PUNCT = _MID_PUNCT + _END_PUNCT
_NO_LINE_START = _SPLIT_PUNCT + "」』）)”’"
_CLOSERS = "」』）)”’"
_IGNORED_FOR_LENGTH = _SPLIT_PUNCT + "「」『』（）()《》〈〉“”‘’\"' "


@lru_cache(maxsize=None)
def _font_path():
    # 沿用專案 base.FONT_FAMILY 的字型選擇，與其他 Scene 字型一致
    props = font_manager.FontProperties(family=base.FONT_FAMILY, weight="bold")
    return font_manager.findfont(props)


def _font(size_px):
    return ImageFont.truetype(_font_path(), int(size_px))


def _body_len(s):
    return sum(1 for ch in s if ch not in _IGNORED_FOR_LENGTH)


def _split_hook_text(text):
    """依標點把旁白切成 (part1, part2)；找不到合理切點就整句當 part1、part2 為空。

    合理切點：標點後面切、兩段去掉標點後都至少 MIN_PART_CHARS 字、不從連續標點
    （？！、……）中間切、不切在數字中間（1,130、10:30）。多個候選取兩段長度最平均的一個。
    """
    text = text.strip()
    best = None
    for i in range(len(text) - 1):
        ch = text[i]
        if ch not in _SPLIT_PUNCT:
            continue
        nxt = text[i + 1]
        if nxt in _SPLIT_PUNCT:
            continue
        if ch in ",;:" and i > 0 and text[i - 1].isdigit() and nxt.isdigit():
            continue
        part1, part2 = text[:i + 1].strip(), text[i + 1:].strip()
        while part2 and part2[0] in _CLOSERS:      # 右引號／右括號留在前一段
            part1, part2 = part1 + part2[0], part2[1:]
        if _body_len(part1) < MIN_PART_CHARS or _body_len(part2) < MIN_PART_CHARS:
            continue
        score = abs(len(part1) - len(part2))
        if best is None or score <= best[0]:
            best = (score, part1, part2)
    return (best[1], best[2]) if best else (text, "")


def _wrap_lines(text, max_chars):
    """換行：各行字數盡量平均，目標斷點附近有標點就優先斷在標點後，標點不落在行首。"""
    n = len(text)
    if n <= max_chars:
        return [text]
    target = -(-n // -(-n // max_chars))      # 行數 = ceil(n / max_chars)；target = 每行平均字數
    lines, start = [], 0
    while n - start > max_chars:
        end = start + target
        for e in (end, end + 1, end - 1, end - 2):
            if start + 2 <= e <= start + max_chars and text[e - 1] in _SPLIT_PUNCT and text[e] not in _NO_LINE_START:
                end = e
                break
        else:
            while end - start > 1 and text[end] in _NO_LINE_START:
                end -= 1                        # 標點不落在行首：把上一行最後一字一起帶下去
        lines.append(text[start:end])
        start = end
    lines.append(text[start:])
    return lines


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


def _layout_text(part1, part2):
    """決定字級與換行，回傳 (font, px, lines1, lines2, line_height)。文字過長時逐級縮小字級。"""
    base_px = base.FONT_SIZE_HOOK * 100 / 72
    for scale in FONT_SCALES:
        px = round(base_px * scale)
        max_chars = max(1, int(LINE_WIDTH / px))
        lines1 = _wrap_lines(part1, max_chars)
        lines2 = _wrap_lines(part2, max_chars) if part2 else []
        line_height = px * LINE_HEIGHT_RATIO
        if (len(lines1) + len(lines2)) * line_height <= MAX_BLOCK_HEIGHT:
            break
    return _font(px), px, lines1, lines2, line_height


def _build_text_masks(part1, part2):
    """把兩段文字各畫成一張 alpha mask（只涵蓋文字區域），回傳 (mask1, mask2, region_x, region_y)。"""
    font, px, lines1, lines2, line_height = _layout_text(part1, part2)
    n_lines = len(lines1) + len(lines2)
    if n_lines == 0:
        return None, None, 0, 0

    region_w = int(LINE_WIDTH + 2 * REGION_PAD) // 2 * 2
    region_h = min(int(n_lines * line_height + 2 * REGION_PAD), base.CANVAS_HEIGHT) // 2 * 2
    region_x = (base.CANVAS_WIDTH - region_w) // 2
    region_y = (base.CANVAS_HEIGHT - region_h) // 2

    def draw(lines, first_index):
        img = Image.new("L", (region_w, region_h), 0)
        d = ImageDraw.Draw(img)
        for k, line in enumerate(lines):
            center_y = region_h / 2 + (first_index + k - (n_lines - 1) / 2) * line_height
            x = (region_w - font.getlength(line)) / 2
            d.text((x, center_y + BASELINE_OFFSET * px), line, font=font, fill=255, anchor="ls")
        return img

    mask1 = draw(lines1, 0)
    mask2 = draw(lines2, len(lines1)) if lines2 else None
    return mask1, mask2, region_x, region_y


def _glow_field():
    """柔光強度場（0~1，中心最亮的橢圓高斯），純色塊漸層，不是圖片。"""
    ys = np.arange(base.CANVAS_HEIGHT, dtype=np.float32)[:, None]
    xs = np.arange(base.CANVAS_WIDTH, dtype=np.float32)[None, :]
    cx, cy = base.CANVAS_WIDTH / 2, base.CANVAS_HEIGHT / 2
    d2 = ((xs - cx) / GLOW_RADIUS_X) ** 2 + ((ys - cy) / GLOW_RADIUS_Y) ** 2
    return np.exp(-2.2 * d2).astype(np.float32)


def render_hook_scene(video_id, segment_index, scene, duration):
    text = scene.get("narration", "").strip()
    part1, part2 = _split_hook_text(text)
    mask1, mask2, region_x, region_y = _build_text_masks(part1, part2)

    bg_color = np.asarray(ImageColor.getrgb(base.BG_COLOR), np.float32)
    accent = ImageColor.getrgb(base.ACCENT_COLOR)
    white = ImageColor.getrgb(base.TEXT_COLOR_PRIMARY)
    field = _glow_field()
    glow_delta = (np.asarray(accent, np.float32) - bg_color)

    def background(g):
        mix = field * (GLOW_MAX_MIX * g)
        return (bg_color + glow_delta * mix[..., None] + 0.5).astype(np.uint8)

    static_background = background(1.0)

    def make_frame(t):
        p = t / duration if duration > 0 else 1.0
        g = base.ease_out_cubic(base.phase(p, *GLOW_PHASE))
        frame = static_background.copy() if g >= 1.0 else background(g)

        s = base.pulse_scale(base.phase(p, *PULSE_PHASE), PULSE_PEAK)
        if mask1 is not None:
            a1 = base.ease_in_out_cubic(base.phase(p, *PART1_PHASE))
            _blend(frame, _scale_mask(mask1, s), region_x, region_y, white, a1)
        if mask2 is not None:
            a2 = base.ease_in_out_cubic(base.phase(p, *PART2_PHASE))
            _blend(frame, _scale_mask(mask2, s), region_x, region_y, accent, a2)
        return frame

    return VideoClip(make_frame, duration=duration)


if __name__ == "__main__":
    test_scene = {"id": "scene_01", "narration": "台北買房，到底有多難？"}
    clip = render_hook_scene("test_scenes", "hook", test_scene, duration=3.0)
    clip.write_videofile("../data/cache/test_scenes/hook_test.mp4", fps=24)
    print("Hook Scene 測試影片已產生：data/cache/test_scenes/hook_test.mp4")
