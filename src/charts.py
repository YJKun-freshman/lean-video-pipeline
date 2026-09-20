# 圖表生成模組

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

from cache import cache_file_path, get_cache_dir

plt.rcParams["font.sans-serif"] = ["Microsoft JhengHei", "SimHei", "Arial Unicode MS"]
plt.rcParams["axes.unicode_minus"] = False

BG_COLOR = "#141826"
ACCENT_COLOR = "#4FD1C5"
BAR_COLOR = "#2E86AB"


def _draw_bar_chart(title, labels, values, growth_ratio, output_path):
    fig, ax = plt.subplots(figsize=(9, 12))
    scaled_values = [v * growth_ratio for v in values]
    bars = ax.bar(labels, scaled_values, color=BAR_COLOR)
    ax.set_title(title, fontsize=24, pad=20)
    ax.set_ylim(0, max(values) * 1.15)
    ax.tick_params(axis="x", labelsize=16)
    ax.tick_params(axis="y", labelsize=14)

    for bar, final_value in zip(bars, values):
        height = bar.get_height()
        if growth_ratio > 0.95:
            ax.annotate(f"{final_value}",
                        xy=(bar.get_x() + bar.get_width() / 2, height),
                        xytext=(0, 5), textcoords="offset points",
                        ha="center", fontsize=14)

    fig.tight_layout()
    fig.savefig(output_path, dpi=150)
    plt.close(fig)


def generate_chart(video_id, index, title, data_points):
    output_path = str(cache_file_path(video_id, f"segment_{index}_chart.png"))
    _draw_bar_chart(title, list(data_points.keys()), list(data_points.values()), 1.0, output_path)
    return output_path


def generate_chart_frames(video_id, index, title, data_points, n_frames=12):
    frames_dir = get_cache_dir(video_id) / f"segment_{index}_frames"
    frames_dir.mkdir(parents=True, exist_ok=True)

    labels = list(data_points.keys())
    values = list(data_points.values())
    frame_paths = []

    for i in range(1, n_frames + 1):
        ratio = i / n_frames
        frame_path = str(frames_dir / f"frame_{i:03d}.png")
        _draw_bar_chart(title, labels, values, ratio, frame_path)
        frame_paths.append(frame_path)

    return frame_paths


def render_highlight_card(video_id, index, label, value, width, height):
    output_path = str(get_cache_dir(video_id) / f"segment_{index}_highlight.png")
    dpi = 100
    fig = plt.figure(figsize=(width / dpi, height / dpi), dpi=dpi)
    fig.patch.set_facecolor(BG_COLOR)
    ax = fig.add_axes([0, 0, 1, 1])
    ax.set_facecolor(BG_COLOR)
    ax.axis("off")
    ax.text(0.5, 0.58, f"{value}", ha="center", va="center",
             fontsize=130, color=ACCENT_COLOR, fontweight="bold")
    ax.text(0.5, 0.40, label, ha="center", va="center",
             fontsize=34, color="white")
    fig.savefig(output_path, dpi=dpi)
    plt.close(fig)
    return output_path


def render_comparison_chart(video_id, index, title, data_points, width, height):
    output_path = str(cache_file_path(video_id, f"segment_{index}_chart.png"))
    labels = list(data_points.keys())
    values = list(data_points.values())

    dpi = 100
    fig = plt.figure(figsize=(width / dpi, height / dpi), dpi=dpi)
    fig.patch.set_facecolor(BG_COLOR)
    ax = fig.add_axes([0, 0, 1, 1])
    ax.set_facecolor(BG_COLOR)
    ax.axis("off")

    arrow_color = "#FF6B6B" if values[1] > values[0] else "#4FD1C5"

    ax.text(0.5, 0.80, title, ha="center", va="center", fontsize=30, color="white")

    ax.text(0.22, 0.52, f"{values[0]}", ha="center", va="center",
             fontsize=68, color="white", fontweight="bold")
    ax.text(0.22, 0.44, labels[0], ha="center", va="center", fontsize=22, color="#AAAAAA")

    ax.annotate("", xy=(0.66, 0.52), xytext=(0.38, 0.52),
                arrowprops=dict(arrowstyle="-|>", color=arrow_color, lw=6))

    if values[0] != 0:
        pct_change = (values[1] - values[0]) / values[0] * 100
        sign = "+" if pct_change >= 0 else ""
        ax.text(0.52, 0.58, f"{sign}{pct_change:.0f}%", ha="center", va="center",
                 fontsize=26, color=arrow_color, fontweight="bold")

    ax.text(0.80, 0.52, f"{values[1]}", ha="center", va="center",
             fontsize=68, color=arrow_color, fontweight="bold")
    ax.text(0.80, 0.44, labels[1], ha="center", va="center", fontsize=22, color="#AAAAAA")

    fig.savefig(output_path, dpi=dpi)
    plt.close(fig)
    return output_path


if __name__ == "__main__":
    test_path = generate_chart(
        "test", 0, "測試圖表：房貸負擔率比較",
        {"台北市": 60, "台中市": 45, "台南市": 40}
    )
    print(f"靜態長條圖已產生：{test_path}")

    highlight_path = render_highlight_card("test", 0, "全國最高房貸負擔率", "60%", 1350, 1800)
    print(f"重點數字卡已產生：{highlight_path}")

    comparison_path = render_comparison_chart(
        "test", 1, "寬限期前後月付對比",
        {"寬限期內": 15000, "寬限期後": 32000}, 1350, 1800
    )
    print(f"前後對比圖已產生：{comparison_path}")