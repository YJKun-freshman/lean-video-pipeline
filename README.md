# 財經影音內容自動化改寫流程

將一支財經 YouTube 影片，自動化改寫為多段合法重製的短影音。全程免費、無需付費 API。

## 流程概觀

YouTube 網址
→ Step1 下載音檔 (yt-dlp)
→ Step2 音檔轉逐字稿 (本地 faster-whisper，含長音檔前處理)
→ Step3 逐字稿改寫為多段腳本 + 評分篩選 (Google Gemini API)
→ Step4 生成短影音 (edge-tts + matplotlib + moviepy)


四個步驟由 `src/pipeline.py` 串接執行，從網址到產出短影音檔案全自動完成，
中間沒有任何人工介入的步驟。

## 事前準備

需要先在本機安裝以下工具：

1. **Python 3.12**（建議，其他 3.10+ 版本應也可行）
2. **ffmpeg**：Windows 上建議用 winget 安裝（會自動設定好環境變數）：
```cmd
   winget install "FFmpeg (Essentials Build)"
```
   安裝後**重新開一個 CMD 視窗**，執行 `ffmpeg -version` 確認安裝成功。
   非 Windows 系統可用對應套件管理器安裝（如 `brew install ffmpeg` / `apt install ffmpeg`）。

## 本機端執行步驟

### 1. 建立虛擬環境並安裝套件

```cmd
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

（macOS/Linux 啟用虛擬環境改用 `source .venv/bin/activate`）

### 2. 申請 API Key

本專案只需要 **1 支免費 API Key**（逐字稿改寫用），且不需要信用卡：

1. 前往 [Google AI Studio](https://aistudio.google.com/apikey)
2. 用 Google 帳號登入，點 **Create API Key**
3. 複製產生的 key

音檔轉錄使用本地端 faster-whisper 模型，不需要任何 API key。

### 3. 設定環境變數

```cmd
copy .env.example .env
```

打開 `.env`，把 `GOOGLE_API_KEY=your_google_api_key_here` 換成你申請到的真實 key。

### 4. 執行

```cmd
cd src
python pipeline.py
```

**首次執行注意事項：**
- Step2 第一次執行會自動下載 Whisper 模型檔案（base 模型約140MB），需要一點時間
- **Windows 使用者**：若下載模型時出現 `WinError 1314`（symlink 權限錯誤），這是 Windows
  預設不允許一般使用者建立符號連結所致。程式碼內已經自動處理（`transcribe.py` 開頭已
  設定 `HF_HUB_DISABLE_SYMLINKS=1`），正常情況下不會再遇到，若仍遇到請確認該行設定存在

跑完後，短影音會輸出在 `data/cache/{video_id}/segment_0.mp4`、`segment_1.mp4` ...
（實際支數依 Step3 篩選結果而定，上限由 `.env` 的 `MAX_SEGMENTS_TO_GENERATE` 控制）

### 5. 重複執行

因為有快取機制，重跑 `python pipeline.py` 時，已完成的步驟會直接讀取快取結果，
不會重複下載、重複轉錄、重複呼叫 Gemini API、重複生成已存在的影片。若要強制
重跑某個步驟，手動刪除 `data/cache/{video_id}/` 底下對應的檔案即可。

## 專案結構

```
├── src/
│ ├── pipeline.py # 主流程入口，串接 Step1-4
│ ├── config.py # 讀取 .env 環境變數
│ ├── cache.py # 快取機制核心
│ ├── download.py # Step1：下載音檔
│ ├── transcribe.py # Step2：本地端轉錄逐字稿
│ ├── rewrite.py # Step3：Gemini 改寫 + 評分篩選
│ ├── charts.py # 圖表生成（含成長動畫影格）
│ ├── tts.py # edge-tts 語音生成
│ ├── text_render.py # 標題卡 / 字幕條圖片生成
│ └── render.py # Step4：moviepy 影片組裝
├── data/
│ ├── cache/ # 各步驟輸出，依 video_id 分資料夾（.gitignore 排除）
│ └── output/
├── .env.example
├── requirements.txt
├── README.md
└── cost.md # 成本假設與決策說明
```

## 成本說明

詳見 [cost.md](./cost.md)，摘要：本專案全程使用免費工具與免費額度，
單支影片 demo 實際花費為 **$0**。

## 版權合規說明

- 逐字稿改寫階段的 Prompt 明確要求「不可逐字照抄，句子結構與用詞需與原文明顯不同」，
  實測結果可對照 `data/cache/{video_id}/transcript.json`（原逐字稿）與
  `selected_scripts.json`（改寫後腳本）
- 每段腳本開頭皆帶出處標示：「根據〔原始來源〕報導／統計指出...」
- 所有圖表皆用 matplotlib 程式化重製，未使用任何截圖或 Canva/Excel 等手動工具
- 圖表數據由 Gemini 直接從逐字稿內容中萃取真實數字，非程式端寫死的假資料

## 已知限制

- `google.generativeai` 套件官方已標示為 deprecated，建議未來遷移至 `google.genai`
  新版 SDK，此次為求穩定沿用舊版套件，功能不受影響
- 字幕採「依字數比例分配時間」的近似同步方式，非逐字精確對齊語音時間戳記
- 若 Gemini 針對某段內容找不到適合視覺化的數字，會退回用主題名稱本身作為
  佔位圖表，避免流程中斷
- 目前畫面呈現偏簡約（單一長條圖+字幕條+標題卡），未整合外部 AI 影片生成或
  Avatar 服務——評估後認為這類服務多數無真正免費方案，與本題「免費額度即可」
  及「成本意識優先於精緻度」的要求方向不符，因此未採用