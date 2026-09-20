# Scene Planner：把 Gemini 的原始輸出正規化成可靠的 Scene 清單

ENDING_FALLBACK_TEXT = "以上內容整理自本次新聞資料。"

MIN_RANKING_ITEMS = 3
MIN_TREND_ITEMS = 3
COMPARISON_ITEMS = 2


def _is_valid_data_item_numeric(item):
    if not isinstance(item, dict):
        return False
    if "label" not in item or "value" not in item:
        return False
    try:
        float(item["value"])
    except (TypeError, ValueError):
        return False
    return True


def _is_valid_data_item_timeline(item):
    if not isinstance(item, dict):
        return False
    return bool(item.get("time")) and bool(item.get("event"))


def _validate_scene(scene, topic_for_log, original_index):
    if not isinstance(scene, dict):
        return False, "scene 不是合法的物件格式"

    scene_type = scene.get("type")
    narration = scene.get("narration", "").strip()

    if scene_type not in {"hook", "big_number", "ranking", "trend",
                           "comparison", "quote", "timeline", "ending"}:
        return False, f"不合法的 type：{scene_type}"

    if not narration:
        return False, "缺少必要欄位 narration"

    if scene_type == "big_number":
        if not str(scene.get("value", "")).strip():
            return False, "big_number 缺少必要欄位 value"

    elif scene_type == "ranking":
        data = scene.get("data")
        if not isinstance(data, list) or len(data) < MIN_RANKING_ITEMS:
            return False, f"ranking 資料筆數不足（需至少{MIN_RANKING_ITEMS}筆）"
        if not all(_is_valid_data_item_numeric(item) for item in data):
            return False, "ranking 資料格式不正確（缺 label/value 或 value 非數字）"

    elif scene_type == "trend":
        data = scene.get("data")
        if not isinstance(data, list) or len(data) < MIN_TREND_ITEMS:
            return False, f"trend 資料筆數不足（需至少{MIN_TREND_ITEMS}筆）"
        if not all(_is_valid_data_item_numeric(item) for item in data):
            return False, "trend 資料格式不正確（缺 label/value 或 value 非數字）"

    elif scene_type == "comparison":
        data = scene.get("data")
        if not isinstance(data, list) or len(data) != COMPARISON_ITEMS:
            return False, f"comparison 資料筆數必須剛好{COMPARISON_ITEMS}筆"
        if not all(_is_valid_data_item_numeric(item) for item in data):
            return False, "comparison 資料格式不正確（缺 label/value 或 value 非數字）"

    elif scene_type == "timeline":
        data = scene.get("data")
        if not isinstance(data, list) or len(data) < MIN_TREND_ITEMS:
            return False, f"timeline 資料筆數不足（需至少{MIN_TREND_ITEMS}筆）"
        if not all(_is_valid_data_item_timeline(item) for item in data):
            return False, "timeline 資料格式不正確（缺 time/event）"

    return True, ""


def normalize_scenes(candidate):
    topic = candidate.get("topic", "（無主題）")
    raw_scenes = candidate.get("scenes", [])

    kept_scenes = []
    for i, scene in enumerate(raw_scenes, start=1):
        is_valid, reason = _validate_scene(scene, topic, i)
        if is_valid:
            scene.setdefault("visual_note", "")
            kept_scenes.append(scene)
        else:
            scene_type = scene.get("type", "未知") if isinstance(scene, dict) else "未知"
            print(f"[ScenePlanner] segment='{topic}' 捨棄 scene（原type={scene_type}, 原順位={i}）：{reason}")

    for i, scene in enumerate(kept_scenes, start=1):
        scene["id"] = f"scene_{i:02d}"

    has_ending = any(s.get("type") == "ending" for s in kept_scenes)
    if not has_ending:
        print(f"[ScenePlanner] segment='{topic}' 未包含ending，補上fallback收尾")
        kept_scenes.append({
            "id": f"scene_{len(kept_scenes) + 1:02d}",
            "type": "ending",
            "narration": ENDING_FALLBACK_TEXT,
            "visual_note": "",
        })

    scene_types_summary = ", ".join(s["type"] for s in kept_scenes)
    print(f"[ScenePlanner] segment='{topic}' 最終保留 {len(kept_scenes)} 個Scene：{scene_types_summary}")

    candidate["scenes"] = kept_scenes
    return candidate


def normalize_candidates(candidates):
    return [normalize_scenes(c) for c in candidates]


if __name__ == "__main__":
    test_candidate = {
        "topic": "測試段落",
        "scenes": [
            {"id": "scene_01", "type": "hook", "narration": "這是開場句"},
            {"id": "scene_02", "type": "big_number", "narration": "缺少數字的場景"},
            {"id": "scene_03", "type": "ranking", "narration": "只有兩筆的排名",
             "data": [{"label": "A", "value": 1}, {"label": "B", "value": 2}]},
            {"id": "scene_04", "type": "trend", "narration": "三年趨勢",
             "data": [{"label": "2023", "value": 9.2}, {"label": "2024", "value": 10.1},
                      {"label": "2025", "value": 11.3}]},
        ]
    }
    result = normalize_scenes(test_candidate)
    print("\n最終結果：")
    for s in result["scenes"]:
        print(f"  {s['id']} ({s['type']})")