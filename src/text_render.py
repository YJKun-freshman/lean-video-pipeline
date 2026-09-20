# 文字轉圖片模組
#
# 背景：moviepy 的 TextClip 搭配 Windows 部分中文字型會出現文字鏡射反字的
# 已知相容性問題。改用 matplotlib 畫文字存成透明背景 PNG，再疊加進影片，
# 因為 matplotlib 渲染中文已經驗證正常（跟圖表用同一套）。

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patheffects as pe

import re
from bisect import bisect_right

import numpy as np
from moviepy import VideoClip
from PIL import Image, ImageColor, ImageDraw

from cache import get_cache_dir
from scenes import base
from scenes.hook import _font

plt.rcParams["font.sans-serif"] = ["Microsoft JhengHei", "SimHei", "Arial Unicode MS"]
plt.rcParams["axes.unicode_minus"] = False


def _wrap_text(text, max_chars=18):
    lines = [text[i:i + max_chars] for i in range(0, len(text), max_chars)]
    return "\n".join(lines)


def render_title_image(video_id, index, text, width, height):
    output_path = str(get_cache_dir(video_id) / f"segment_{index}_title.png")
    dpi = 100
    fig = plt.figure(figsize=(width / dpi, height / dpi), dpi=dpi)
    fig.patch.set_facecolor("#141826")
    ax = fig.add_axes([0, 0, 1, 1])
    ax.set_facecolor("#141826")
    ax.axis("off")
    ax.text(0.5, 0.5, _wrap_text(text, 12), ha="center", va="center",
             fontsize=40, color="white", multialignment="center")
    fig.savefig(output_path, dpi=dpi)
    plt.close(fig)
    return output_path


def render_subtitle_image(video_id, index, text, width, height=220):
    """產生字幕條圖片：深色不透明底、白字，放在畫面下方獨立區塊，不與圖表重疊。"""
    output_path = str(get_cache_dir(video_id) / f"segment_{index}_subtitle.png")
    dpi = 100
    fig = plt.figure(figsize=(width / dpi, height / dpi), dpi=dpi)
    fig.patch.set_facecolor("#141826")
    ax = fig.add_axes([0, 0, 1, 1])
    ax.set_facecolor("#141826")
    ax.axis("off")
    ax.text(0.5, 0.5, _wrap_text(text, 20), ha="center", va="center",
             fontsize=26, color="white", multialignment="center")
    fig.savefig(output_path, dpi=dpi)
    plt.close(fig)
    return output_path


# ---------------------------------------------------------------------------
# 逐句字幕（Scene 系統）
#
# 資料來源：scene["narration"]（與 TTS 唸的是同一段文字），不需要任何新欄位。
# 只加在資料型 Scene——hook / quote / ending 已經把旁白當主視覺文字，再加字幕會重複。
# 版面：底部安全區內、最多 2 行、置中、最後一行位置固定（1 行與 2 行的字幕不會上下跳動）。
# Keyword：純本地規則，只改「顏色」，字級與字重不變，所以 highlight 不會造成文字跳動；
#          換行時 keyword 與英數連續字元視為不可拆分，不會把 11.3 斷成兩行。
# 時間：tts.py 沒有逐句時間戳，改用「標點停頓 + 字數比例」把 Scene 實際時長分給每句，是估計值。
# ---------------------------------------------------------------------------

SUBTITLE_SCENE_TYPES = {"big_number", "ranking", "trend", "comparison", "timeline"}
SUBTITLE_MAX_LINES = 2
SUBTITLE_MAX_HIGHLIGHTS = 2               # 同一句字幕最多幾處 highlight，數字優先於變化詞
SUBTITLE_LINE_HEIGHT_RATIO = 1.4
SUBTITLE_BAND_PAD = 12
SUBTITLE_BASELINE_OFFSET = 0.35           # 基線到字形視覺中心的距離（單位：字級）
_SUB_MARGIN_X = int(base.CANVAS_WIDTH * base.SAFE_MARGIN_RATIO)
_SUB_LINE_WIDTH = base.CANVAS_WIDTH - 2 * _SUB_MARGIN_X

_SUB_END = "。！？!?…"
_SUB_MID = "，、；：,;:"
_SUB_NO_LINE_START = _SUB_END + _SUB_MID + "」』）)”’"
_SUB_PAUSE_WEIGHT = {**{c: 2.0 for c in _SUB_END}, **{c: 1.0 for c in _SUB_MID}}   # 其餘字元 1、空白 0

_CN_DIGITS = "零〇一二兩三四五六七八九十百千"
_UNITS = r"(?:萬元|億元|萬|億|元|成|倍|折|年|個月|月|坪|戶|人|字頭|%|％)"
_NUMBER_RE = re.compile("|".join((
    r"百分之[" + _CN_DIGITS + r"\d]+(?:點[" + _CN_DIGITS + r"\d]+)?",                       # 百分之二十五
    r"\d[\d,]*(?:\.\d+)?(?:\s?" + _UNITS + r")?",                                           # 11.3 倍、8%、1,200 元
    r"(?=[" + _CN_DIGITS + r"萬億])(?:[" + _CN_DIGITS + r"]+[萬億])*[" + _CN_DIGITS + r"]*"
    r"(?:、[" + _CN_DIGITS + r"]+)?(?:點[" + _CN_DIGITS + r"]+)?" + _UNITS,                  # 一萬五千元、六成、七、八十萬
)))
_CHANGE_WORDS = ("翻倍", "飆漲", "暴漲", "急漲", "狂飆", "大跌", "暴跌", "創新高", "創新低", "攀升", "突破")
_WORD_RE = re.compile("|".join(map(re.escape, _CHANGE_WORDS)))
_LATIN_RUN_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9.,%]*")


def _find_keywords(text):
    """回傳 [(start, end, kind)]，kind 為 "number" 或 "word"；兩者不重疊。"""
    spans = [(m.start(), m.end(), "number") for m in _NUMBER_RE.finditer(text)]
    taken = [(s, e) for s, e, _ in spans]
    for m in _WORD_RE.finditer(text):
        if not any(m.start() < e and s < m.end() for s, e in taken):
            spans.append((m.start(), m.end(), "word"))
    return sorted(spans)


def _to_atoms(text, spans):
    """把文字切成不可拆分的單位 [(文字, kind)]：keyword 與英數連續字元整段一個單位，其餘一字一個單位。"""
    bounds = {s: (e, kind) for s, e, kind in spans}
    covered = {i for s, e, _ in spans for i in range(s, e)}
    for m in _LATIN_RUN_RE.finditer(text):
        if m.start() not in covered:
            bounds[m.start()] = (m.end(), None)
    atoms, i = [], 0
    while i < len(text):
        if i in bounds:
            end, kind = bounds[i]
            atoms.append((text[i:end], kind))
            i = end
        else:
            atoms.append((text[i], None))
            i += 1
    return atoms


def _wrap_atoms(atoms, font, limit=_SUB_LINE_WIDTH):
    """依像素寬度換行；標點不落行首（把上一個單位一起帶下去）；行首空白略過。"""
    lines, cur = [], []
    for atom in atoms:
        text = atom[0]
        if not cur and text.isspace():
            continue
        if cur and font.getlength("".join(a[0] for a in cur) + text) > limit:
            if text[0] in _SUB_NO_LINE_START and len(cur) > 1:
                last = cur.pop()
                lines.append(cur)
                cur = [last]
            else:
                lines.append(cur)
                cur = []
        cur.append(atom)
    if cur:
        lines.append(cur)
    return lines


def _wrap_balanced(atoms, font):
    """行數與 _wrap_atoms 相同，但把各行寬度壓平均，避免「右。」這種單獨一兩個字的最後一行。"""
    n = len(_wrap_atoms(atoms, font))
    if n < 2:
        return _wrap_atoms(atoms, font)
    lo, hi = 1, _SUB_LINE_WIDTH                 # hi 一定可行；找行數仍為 n 的最小寬度上限
    while hi - lo > 2:
        mid = (lo + hi) // 2
        if len(_wrap_atoms(atoms, font, mid)) <= n:
            hi = mid
        else:
            lo = mid
    return _wrap_atoms(atoms, font, hi)


def _chunk_atoms(atoms, font):
    """切成一句一句的字幕：優先斷在標點後、每句最多 SUBTITLE_MAX_LINES 行；單一子句太長才強制斷。"""
    n = len(atoms)
    breaks = [i + 1 for i, a in enumerate(atoms) if a[0][-1] in _SUB_END + _SUB_MID]
    chunks, start = [], 0
    while start < n:
        fits = lambda e: len(_wrap_atoms(atoms[start:e], font)) <= SUBTITLE_MAX_LINES
        end = next((e for e in sorted({b for b in breaks if b > start} | {n}, reverse=True) if fits(e)), None)
        if end is None:                       # 連第一個子句都放不進 2 行 → 在單位邊界強制斷
            end = start + 1
            while end < n and fits(end + 1):
                end += 1
        chunks.append(atoms[start:end])
        start = end
    return [c for c in chunks if any(not a[0].isspace() for a in c)]


def _limit_highlights(chunk):
    """同一句最多 SUBTITLE_MAX_HIGHLIGHTS 處：數字優先、其次變化詞；回傳 [(文字, 是否 highlight)]。"""
    ranked = sorted((i for i, a in enumerate(chunk) if a[1]), key=lambda i: (chunk[i][1] != "number", i))
    keep = set(ranked[:SUBTITLE_MAX_HIGHLIGHTS])
    return [(a[0], i in keep) for i, a in enumerate(chunk)]


def _chunk_weight(chunk):
    return sum(_SUB_PAUSE_WEIGHT.get(ch, 0.0 if ch.isspace() else 1.0) for text, _ in chunk for ch in text)


def _render_subtitle_chunk(lines, font, px, band_h):
    """一句字幕 → (rgb 陣列, mask 陣列)：底部對齊，白字 + 青色 keyword。"""
    line_h = px * SUBTITLE_LINE_HEIGHT_RATIO
    white_img = Image.new("L", (base.CANVAS_WIDTH, band_h), 0)
    accent_img = Image.new("L", (base.CANVAS_WIDTH, band_h), 0)
    draws = {False: ImageDraw.Draw(white_img), True: ImageDraw.Draw(accent_img)}
    last_center = band_h - SUBTITLE_BAND_PAD - line_h / 2
    for k, line in enumerate(lines):
        baseline = last_center - (len(lines) - 1 - k) * line_h + SUBTITLE_BASELINE_OFFSET * px
        full = "".join(t for t, _ in line)
        x0 = (base.CANVAS_WIDTH - font.getlength(full)) / 2
        prefix = ""
        for text, highlighted in line:
            draws[highlighted].text((x0 + font.getlength(prefix), baseline), text, font=font, fill=255, anchor="ls")
            prefix += text
    white, accent = np.asarray(white_img), np.asarray(accent_img)
    rgb = np.empty((band_h, base.CANVAS_WIDTH, 3), np.uint8)
    rgb[:] = ImageColor.getrgb(base.TEXT_COLOR_PRIMARY)
    rgb[accent > 0] = ImageColor.getrgb(base.ACCENT_COLOR)
    return rgb, np.maximum(white, accent).astype(np.float32) / 255.0


def make_subtitle_clip(scene, duration):
    """為資料型 Scene 產生帶透明遮罩的字幕 clip（已設定位置）；不需要字幕的 Scene 回傳 None。"""
    if scene.get("type") not in SUBTITLE_SCENE_TYPES or duration <= 0:
        return None
    narration = scene.get("narration")
    text = " ".join(narration.split()) if isinstance(narration, str) else ""
    if not text:
        return None

    px = round(base.FONT_SIZE_SUBTITLE * 100 / 72)
    font = _font(px)
    chunks = _chunk_atoms(_to_atoms(text, _find_keywords(text)), font)
    if not chunks:
        return None

    band_h = int(SUBTITLE_MAX_LINES * px * SUBTITLE_LINE_HEIGHT_RATIO + 2 * SUBTITLE_BAND_PAD)
    frames = []
    for chunk in chunks:
        lines = _wrap_balanced(_limit_highlights(chunk), font)
        frames.append(_render_subtitle_chunk(lines, font, px, band_h))

    weights = [_chunk_weight(c) for c in chunks]
    total = sum(weights) or 1.0
    starts, acc = [], 0.0
    for w in weights:                         # 每句開始時間 = 時長 × 累計權重 / 總權重
        starts.append(duration * acc / total)
        acc += w

    def pick(t):
        return frames[max(0, bisect_right(starts, t) - 1)]

    video = VideoClip(lambda t: pick(t)[0], duration=duration)
    mask = VideoClip(lambda t: pick(t)[1], duration=duration, is_mask=True)
    return video.with_mask(mask).with_position((0, base.SAFE_BOTTOM_Y - band_h))


if __name__ == "__main__":
    title_path = render_title_image("test", 0, "測試段落：房貸負擔率比較", 1350, 1800)
    print(f"標題卡圖片已產生：{title_path}")

    subtitle_path = render_subtitle_image(
        "test", 0,
        "根據TVBS新聞報導指出，台北市的房貸負擔率高居全國之冠，年輕族群購屋壓力沉重。",
        1350,
    )
    print(f"字幕圖片已產生：{subtitle_path}")