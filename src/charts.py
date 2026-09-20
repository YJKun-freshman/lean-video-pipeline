"""
圖表生成模組
"""

import os
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

from cache import cache_file_path, get_cache_dir

plt.rcParams["font.sans-serif"] = ["Microsoft JhengHei", "SimHei", "Arial Unicode MS"]
plt.rcParams["axes.unicode_minus"] = False


def _draw_bar_chart(title, labels, values, growth_ratio, output_path):
    fig, ax = plt.subplots(figsize=(9, 12))
    scaled_values = [v * growth_ratio for v in values]
    bars = ax.bar(labels, scaled_values, color="#2E86AB")
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


if __name__ == "__main__":
    test_path = generate_chart(
        "test", 0, "測試圖表：房貸負擔率比較",
        {"台北市": 60, "台中市": 45, "台南市": 40}
    )
    print(f"靜態測試圖表已產生：{test_path}")

    frames = generate_chart_frames(
        "test", 0, "測試圖表：房貸負擔率比較",
        {"台北市": 60, "台中市": 45, "台南市": 40}
    )
    print(f"動畫影格共 {len(frames)} 張，存放於：{frames[0]} ...")