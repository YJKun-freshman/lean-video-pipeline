# Step 3：逐字稿改寫為多段短影音腳本（Scene 系統版）

import json
import google.generativeai as genai

from cache import extract_video_id, cache_exists, load_json, save_json, log_step
from config import GOOGLE_API_KEY, GEMINI_MODEL, MAX_SEGMENTS_TO_GENERATE, SOURCE_VIDEO_URL

REWRITE_PROMPT_TEMPLATE = """你是財經短影音的內容編輯與導演。你會收到一份影片逐字稿，任務如下：

## 第一步：切分主題段落

把逐字稿切分成數個獨立主題段落，每段標記：
- topic：主題摘要（10字內）
- score：適合做成短影音的分數（1-10，考量資訊密度與獨立完整性）
- source_note：出處標示句，格式為「根據〔原始來源〕報導／統計指出...」
- rewritten_script：整段改寫後的完整口白文字（60-90秒長度），保留備用參考

## 第二步：把每段拆解成 Scene（畫面段落）

這是最重要的部分。針對每個主題段落，把內容拆解成一至數個 Scene，每個 Scene 是
影片的一段獨立畫面，會搭配對應的視覺呈現方式。

**Scene 拆解的核心原則（務必遵守）：**
- Scene 數量由內容決定，內容豐富就多切幾個，內容單薄就少切，不需要用滿所有種類
- 一段話語意連貫、適合連續講完，就保持在同一個 Scene，不要為了畫面切換硬拆斷一句話
- 只有當「資訊內容真的發生變化」或「需要換一種視覺化方式才能表達清楚」時，
  才切換到下一個 Scene
- 目標是讓觀眾感覺「這段資訊被自然地視覺化」，而不是「每幾秒就換一次動畫」

**每個 Scene 都要有的共同欄位：**
- id：段落內從 "scene_01" 開始依序編號（不用管其他段落是否重複用同樣編號）
- type：見下方可用類型
- narration：這個 Scene 的旁白文字
- visual_note（可選）：給畫面呈現方式的建議，例如「這個數字是全片重點，可以停留久一點」，
  這只是建議不是硬性指令，沒有想法可以省略這個欄位

**可用的 Scene type（依內容選用）：**

1. `hook`：開場吸睛句，通常是疑問句或引起好奇的一句話。無其他必要欄位。

2. `big_number`：單一關鍵數字特寫，適合百分比/金額/倍數/年增率。額外必要欄位：
   - value：數字本身（字串，例如"11.3"）
   - unit：單位（例如"倍"、"%"、"元"，沒有則空字串）
   - label：這個數字代表什麼（例如"房價所得比"）

3. `ranking`：3個以上項目的排名比較。額外必要欄位：
   - data：陣列，**至少3筆**，每筆 {{"label": "項目名稱", "value": 數值}}

4. `trend`：3個以上時間點的趨勢變化。額外必要欄位：
   - data：陣列，**至少3筆**，每筆 {{"label": "時間點", "value": 數值}}，依時間順序排列

5. `comparison`：2個項目的對比（例如前後差異、A vs B）。額外必要欄位：
   - data：陣列，**必須剛好2筆**，每筆 {{"label": "項目名稱", "value": 數值}}

6. `quote`：內容沒有適合的具體數據時使用，純文字重點句，不硬做圖表。無其他必要欄位。

7. `timeline`：3個以上有時間序列的事件/政策變化。額外必要欄位：
   - data：陣列，**至少3筆**，每筆 {{"time": "時間點", "event": "事件描述（簡短）"}}

8. `ending`：影片結尾的自然收尾句，根據前面內容延伸的總結，不要空泛套話。如果這段
   內容真的收不出合理結論，可以整段不產生 ending，程式端會自動補上中性收尾。

## 改寫規則（務必遵守，適用所有文字內容）
- 禁止逐字照抄原文，句子結構與用詞需與原文明顯不同
- 保留原意與數據正確性，僅重新組織表達方式
- Scene 中的數字必須是逐字稿中實際提到的真實數字，不可虛構
- ranking/trend 未滿3筆、comparison 不是剛好2筆時，請改用其他更適合的 Scene type
  （例如改成 quote 或併入 big_number），不要硬湊筆數或硬用該類型

## 輸出格式

僅回傳 JSON 陣列，不要有其他文字、不要用 markdown code block 包裹：

[
  {{
    "topic": "...",
    "score": 0-10,
    "source_note": "...",
    "rewritten_script": "...",
    "scenes": [
      {{"id": "scene_01", "type": "hook", "narration": "..."}},
      {{"id": "scene_02", "type": "big_number", "narration": "...", "value": "...", "unit": "...", "label": "...", "visual_note": "..."}},
      {{"id": "scene_03", "type": "ending", "narration": "..."}}
    ]
  }}
]

逐字稿內容：
{transcript}
"""


def _clean_json_text(raw_text):
    text = raw_text.strip()
    if text.startswith("```"):
        lines = text.split("\n")
        lines = [l for l in lines if not l.strip().startswith("```")]
        text = "\n".join(lines)
    return text.strip()


def rewrite_and_score(video_id, transcript_text):
    if cache_exists(video_id, "script_candidates.json"):
        log_step("Step3-Rewrite(候選)", video_id, hit=True)
        return load_json(video_id, "script_candidates.json")

    log_step("Step3-Rewrite(候選)", video_id, hit=False)

    genai.configure(api_key=GOOGLE_API_KEY)
    model = genai.GenerativeModel(GEMINI_MODEL)

    prompt = REWRITE_PROMPT_TEMPLATE.format(transcript=transcript_text)
    print("呼叫 Gemini API 進行改寫、評分與 Scene 拆解...")
    response = model.generate_content(prompt)

    cleaned = _clean_json_text(response.text)
    try:
        candidates = json.loads(cleaned)
    except json.JSONDecodeError as e:
        print("JSON 解析失敗，原始回傳內容如下，供除錯：")
        print(response.text)
        raise e

    save_json(video_id, "script_candidates.json", candidates)
    return candidates


def select_top_segments(candidates, video_id):
    if cache_exists(video_id, "selected_scripts.json"):
        log_step("Step3-Select(篩選)", video_id, hit=True)
        return load_json(video_id, "selected_scripts.json")

    log_step("Step3-Select(篩選)", video_id, hit=False)

    sorted_candidates = sorted(candidates, key=lambda c: c["score"], reverse=True)
    selected = sorted_candidates[:MAX_SEGMENTS_TO_GENERATE]

    save_json(video_id, "selected_scripts.json", selected)
    print(f"候選 {len(candidates)} 段，篩選出 {len(selected)} 段進入影片生成")
    return selected


if __name__ == "__main__":
    vid = extract_video_id(SOURCE_VIDEO_URL)
    transcript = load_json(vid, "transcript.json")
    candidates = rewrite_and_score(vid, transcript["text"])

    print(f"\n候選段落共 {len(candidates)} 段（尚未正規化，原始 Gemini 輸出）：")
    for c in candidates:
        print(f"\n[{c.get('score')}] {c.get('topic')}")
        for s in c.get("scenes", []):
            print(f"  {s.get('id')} ({s.get('type')}): {s.get('narration', '')[:30]}...")

    selected = select_top_segments(candidates, vid)
    print(f"\n篩選後段落數：{len(selected)}")