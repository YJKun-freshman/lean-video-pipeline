# Scene 系統共用基礎設施

import math

CANVAS_WIDTH = 1080
CANVAS_HEIGHT = 1920

SAFE_MARGIN_RATIO = 0.10
SAFE_MARGIN_TOP = int(CANVAS_HEIGHT * SAFE_MARGIN_RATIO)
SAFE_MARGIN_BOTTOM = int(CANVAS_HEIGHT * SAFE_MARGIN_RATIO)
SAFE_TOP_Y = SAFE_MARGIN_TOP
SAFE_BOTTOM_Y = CANVAS_HEIGHT - SAFE_MARGIN_BOTTOM

SUBTITLE_Y_RATIO = 0.74

BG_COLOR = "#141826"
ACCENT_COLOR = "#4FD1C5"
ACCENT_COLOR_UP = "#FF6B6B"
ACCENT_COLOR_DOWN = "#4FD1C5"
TEXT_COLOR_PRIMARY = "#FFFFFF"
TEXT_COLOR_SECONDARY = "#AAAAAA"

FONT_FAMILY = ["Microsoft JhengHei", "SimHei", "Arial Unicode MS"]


def scaled_font_size(ratio_of_width):
    return int(CANVAS_WIDTH * ratio_of_width)


FONT_SIZE_HOOK = scaled_font_size(0.065)
FONT_SIZE_BIG_NUMBER = scaled_font_size(0.16)
FONT_SIZE_LABEL = scaled_font_size(0.032)
FONT_SIZE_SUBTITLE = scaled_font_size(0.036)
FONT_SIZE_SUBTITLE_KEYWORD = scaled_font_size(0.048)
FONT_SIZE_TITLE = scaled_font_size(0.052)


def apply_font_rcparams():
    import matplotlib.pyplot as plt
    plt.rcParams["font.sans-serif"] = FONT_FAMILY
    plt.rcParams["axes.unicode_minus"] = False


def new_figure(dpi=100):
    import matplotlib.pyplot as plt
    apply_font_rcparams()
    fig = plt.figure(figsize=(CANVAS_WIDTH / dpi, CANVAS_HEIGHT / dpi), dpi=dpi)
    fig.patch.set_facecolor(BG_COLOR)
    ax = fig.add_axes([0, 0, 1, 1])
    ax.set_facecolor(BG_COLOR)
    ax.axis("off")
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    return fig, ax


def y_to_axes_fraction(pixel_y_from_top):
    return 1 - (pixel_y_from_top / CANVAS_HEIGHT)


def wrap_text(text, max_chars=12):
    """中文沒有空白斷詞，簡單依字數手動換行，供各 Scene 共用。"""
    lines = [text[i:i + max_chars] for i in range(0, len(text), max_chars)]
    return "\n".join(lines)


# --- 動畫數學 helper（純數學，不含繪圖與 I/O；時間一律用「佔 Scene 時長的比例」）---

def clamp01(x):
    return max(0.0, min(1.0, x))


def phase(progress, start, end):
    """整體進度 progress(0~1) 換算成區間 [start, end] 內的局部進度 0~1，區間外夾在 0 或 1。"""
    if end <= start:
        return 1.0 if progress >= end else 0.0
    return clamp01((progress - start) / (end - start))


def ease_out_cubic(t):
    """先快後慢：越接近終點速度越慢，用於 count-up。"""
    t = clamp01(t)
    return 1.0 - (1.0 - t) ** 3


def ease_in_out_cubic(t):
    """起訖都平緩，用於淡入。"""
    t = clamp01(t)
    return 4.0 * t ** 3 if t < 0.5 else 1.0 - ((-2.0 * t + 2.0) ** 3) / 2.0


def pulse_scale(t, peak=1.08):
    """局部進度 t(0~1) 內縮放 1.0 → peak → 1.0；sin² 曲線，起訖速度為 0，不會突然彈跳。"""
    t = clamp01(t)
    return 1.0 + (peak - 1.0) * math.sin(math.pi * t) ** 2