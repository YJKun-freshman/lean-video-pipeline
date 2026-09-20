# Step 3：逐字稿改寫為多段短影音腳本
#
# 自動化程度：
# - chart_data 由 Gemini 直接從逐字稿內容抓出這段實際提到的數字，
#   不是程式端寫死的假資料，確保不同主題的逐字稿都能自動產生對應圖表

import json
import google.generativeai as genai

from cache import extract_video_id, cache_exists, load_json, save_json, log_step
from config import GOOGLE_API_KEY, GEMINI_MODEL, MAX_SEGMENTS_TO_GENERATE, SOURCE_VIDEO_URL

REWRITE_PROMPT_TEMPLATE = """你是財經內容編輯。你會收到一份影片逐字稿，任務分兩步：

1. 將逐字稿切分成數個獨立主題段落，每段標記：
   - topic：主題摘要（10字內）
   - score：適合做成短影音的分數（1-10，考量資訊密度與獨立完整性）
   - rewritten_script：改寫後的短影音腳本（口語化、適合旁白唸讀，60-90秒長度）
   - source_note：出處標示句，格式為「根據〔原始來源〕報導／統計指出...」
   - chart_data：從這段內容中找出2-4個適合視覺化比較的數字，格式為
     {{"標籤1": 數值1, "標籤2": 數值2}}。標籤用簡短中文詞（例如城市名、年限、
     方案名稱），數值只填數字本身（不含單位文字）。如果這段內容真的找不到
     適合比較的具體數字，回傳空物件 {{}}。

2. 改寫規則（務必遵守）：
   - 禁止逐字照抄原文，句子結構與用詞需與原文明顯不同
   - 保留原意與數據正確性，僅重新組織表達方式
   - 每段腳本開頭需帶出處標示句
   - chart_data 的數字必須是逐字稿中實際提到的真實數字，不可虛構

僅回傳 JSON 陣列，不要有其他文字、不要用 markdown code block 包裹，格式：
[{{"topic": "...", "score": 0-10, "rewritten_script": "...", "source_note": "...",
   "chart_data": {{"標籤1": 數值1, "標籤2": 數值2}}}}]

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
    print("呼叫 Gemini API 進行改寫、評分與圖表數據萃取...")
    response = model.generate_content(prompt)

    cleaned = _clean_json_text(response.text)
    try:
        candidates = json.loads(cleaned)
    except json.JSONDecodeError as e:
        print("JSON 解析失敗，原始回傳內容如下，供除錯：")
        print(response.text)
        raise e

    for c in candidates:
        if "chart_data" not in c or not isinstance(c["chart_data"], dict):
            c["chart_data"] = {}

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
    print(f"\n候選段落共 {len(candidates)} 段：")
    for c in candidates:
        print(f"  [{c['score']}] {c['topic']}  圖表數據：{c['chart_data']}")

    selected = select_top_segments(candidates, vid)
    print(f"\n篩選後段落：")
    for s in selected:
        print(f"  [{s['score']}] {s['topic']}")
        print(f"    {s['source_note']}")
        print(f"    圖表數據：{s['chart_data']}")
        print(f"    {s['rewritten_script'][:60]}...")