# Scene transitions：只有兩種情況淡出到底色，其餘一律硬切（沒有 crossfade）
#
# 每個 Scene 本來就從空白底色開始自己的進場動畫，所以「前一段淡出到底色」的視覺效果
# 就等於交叉溶接；而且淡出不重疊、不改長度、不動音訊，Scene 時長仍然 = TTS 時長。
#
#   → ending            淡出 0.35 秒（柔和收尾）
#   同類型 Scene 連續   淡出 0.2 秒（版面相同只換內容，硬切像跳針）
#   其他                硬切

import numpy as np
from PIL import ImageColor

from scenes import base

FADE_INTO_ENDING = 0.35
FADE_SAME_TYPE = 0.2
MAX_FADE_RATIO = 0.5          # 淡出最長不超過該 Scene 自己時長的一半
END_HOLD = 0.05               # 淡出提前這麼久完成，讓最後 1~2 格就是純底色


def pick_transition(prev_type, next_type):
    """兩個相鄰 Scene 之間的淡出秒數；0 代表硬切。"""
    if next_type == "ending":
        return FADE_INTO_ENDING
    if prev_type == next_type:
        return FADE_SAME_TYPE
    return 0.0


def _fade_out_to_color(clip, seconds, color):
    """最後 seconds 秒（不含 END_HOLD）線性淡出到 color。

    不用 vfx.FadeOut：它要到 t = 總長才完全到色，但那一刻不會被輸出（最後一格在 1/fps 之前），
    Scene 交界會殘留一格沒淡完的畫面。
    """
    end = clip.duration - END_HOLD
    color = np.asarray(color, np.float32)

    def fade(get_frame, t):
        k = min(1.0, max(0.0, (end - t) / seconds))      # 1 = 原畫面，0 = 純底色
        if k >= 1.0:
            return get_frame(t)
        return (get_frame(t).astype(np.float32) * k + color * (1.0 - k) + 0.5).astype(np.uint8)

    return clip.transform(fade)


def apply_transitions(clips, types):
    """對需要淡出的邊界，把前一個 clip 淡出到底色；回傳新的 clip 列表（長度、順序、音訊都不變）。"""
    bg = ImageColor.getrgb(base.BG_COLOR)
    result = list(clips)
    for i in range(len(clips) - 1):
        fade = min(pick_transition(types[i], types[i + 1]), clips[i].duration * MAX_FADE_RATIO)
        if fade > 0:
            result[i] = _fade_out_to_color(clips[i], fade, bg)
    return result
