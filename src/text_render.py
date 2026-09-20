# 文字轉圖片模組
#
# 背景：moviepy 的 TextClip 搭配 Windows 部分中文字型會出現文字鏡射反字的
# 已知相容性問題。改用 matplotlib 畫文字存成透明背景 PNG，再疊加進影片，
# 因為 matplotlib 渲染中文已經驗證正常（跟圖表用同一套）。

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patheffects as pe

from cache import get_cache_dir

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


if __name__ == "__main__":
    title_path = render_title_image("test", 0, "測試段落：房貸負擔率比較", 1350, 1800)
    print(f"標題卡圖片已產生：{title_path}")

    subtitle_path = render_subtitle_image(
        "test", 0,
        "根據TVBS新聞報導指出，台北市的房貸負擔率高居全國之冠，年輕族群購屋壓力沉重。",
        1350,
    )
    print(f"字幕圖片已產生：{subtitle_path}")