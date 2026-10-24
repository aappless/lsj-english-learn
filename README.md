# LSJ English Learn

上面播影片（YouTube 或本機影片），中間是同步的中英字幕和高亮片語，下面是片語、句型、文法卡片。

## 啟動

雙擊 `start.bat`（需要 Python），瀏覽器會自動開啟 http://127.0.0.1:8000/

> 不要直接雙擊 `index.html`：YouTube 會拒絕在 `file://` 頁面中嵌入播放。

## 影片來源

| 來源 | 做法 |
|---|---|
| YouTube | 上方貼網址按「載入 YT」，或在課程檔寫 `"source": {"type": "youtube", "id": "影片ID"}` |
| 本機影片 | 按「本機影片」選擇檔案；或把影片放在 `videos/`，課程檔寫 `"source": {"type": "local", "file": "videos/xxx.mp4"}` |

## 製作新課程：課程製作室（最簡單的方法）

雙擊 `start.bat` 開啟**本機版**，影片下方會出現「🛠 課程製作室」，照 A → D 做：

| 步驟 | 做什麼 |
|---|---|
| **A. 加入課程** | 顯示目前課程。做新課程從 B 開始；幫已有課程加卡片，在最上方選單選課程後跳到 D |
| **B. 設定 YouTube 網址** | 貼上網址，可按「▶ 先播放看看」確認 |
| **C. 製作字幕** | 按 **🛠 製作字幕**，10～30 秒後新課程自動出現在選單（影片要有英文 CC 字幕） |
| **D. 片語、單字卡片** | D1：選範圍（每次 50 句），按 **📋 複製提示詞** 或 **⬇ 下載提示詞**，貼到 Claude（claude.ai）或 ChatGPT<br>D2：把 AI 的回答貼回框框按 **📥 匯入卡片**，或用 **📂 從檔案匯入** |

做完後用 Git 小幫手按「💾⬆ 存檔並上傳」，網站上就會出現。

- 課程製作室只在本機版出現，GitHub 網站上不會有
- **不需要 API 金鑰**：卡片用網頁版 Claude 或 ChatGPT 做即可
- 匯入時會自動檢查：英文對不上的卡片會略過並說明原因；同一句同一個片語不會重複匯入
- 第一次匯入會把原課程檔備份成 `.json.bak`
- 卡片格式與提示詞範本：[docs/卡片格式說明.md](docs/卡片格式說明.md)（可以整份交給任何 AI）
- 「▶ 載入 YT」（最上方）只會播放影片，**不會**產生字幕
- 有設定 `ANTHROPIC_API_KEY` 時，C 旁邊會多出「同時用 Claude 做卡片」的選項

## 用 YouTube 的 CC 產生課程（指令版）

```
python tools/yt_cc.py https://www.youtube.com/watch?v=影片ID
```

- 英文：人工字幕優先，沒有才用自動字幕
- 中文：影片本身的繁中/中文字幕優先，沒有就用 YouTube 自動翻譯
- 結果會存到 `lessons/影片ID.json`，並加入課程選單
- 片語／文法卡片（`notes`）是空的，需要另外補上

第一次使用要先安裝套件：`python -m pip install youtube-transcript-api`

## 用 Claude 產生片語／句型／文法卡片

```
python tools/gen_cards.py lessons/影片ID.json
```

- 需要 Anthropic API 金鑰：到 https://platform.claude.com 申請，設定成環境變數 `ANTHROPIC_API_KEY`
- Claude 會逐句重新翻譯中文（對齊得比 YouTube 字幕準），並挑出值得教的詞塊、句型、文法、單字
- 每 30 句存檔一次；中途中斷再執行同一個指令，會從上次的位置繼續
- 第一次執行會先把原檔備份成 `.json.bak`
- 選項：
  - `--level 國中`：依學習者程度挑重點（預設「台灣高中到大學程度」）
  - `--keep-zh`：保留原本的中文翻譯
  - `--restart`：從頭重新產生
  - `--effort high`：讓 Claude 想得更仔細（較慢、較貴）
- 使用模型 `claude-opus-5-5`，跑完會顯示用量和大約的費用

第一次使用要先安裝套件：`python -m pip install anthropic`

## 課程檔格式（lessons/*.json）

```json
{
  "title": "課程標題",
  "source": { "type": "youtube", "id": "iG9CE55wbtY" },
  "lines": [
    {
      "start": 4.2, "end": 8.0,
      "en": "It's like one of the most complex pieces of hardware on the planet.",
      "zh": "可說是地球上最複雜的硬體之一。",
      "notes": [
        {
          "type": "pattern",
          "match": "one of the most complex pieces of hardware",
          "zhMatch": "最複雜的硬體之一",
          "title": "one of the most + adj. + Ns",
          "meaning": "最…的之一（N 用複數）",
          "explain": "名詞要用複數……",
          "example": { "en": "...", "zh": "..." }
        }
      ]
    }
  ]
}
```

- `type`：`chunk` 詞塊、`pattern` 句型、`grammar` 文法、`word` 單字（顏色不同）
- `match` / `zhMatch`：要在英文／中文字幕中高亮的字串
- 新課程要加進 `lessons/index.json` 才會出現在選單（`yt_cc.py` 會自動加）

## 快捷鍵

空白鍵 播放／暫停 · ← → 上一句／下一句 · R 單句循環 · P 逐句暫停
