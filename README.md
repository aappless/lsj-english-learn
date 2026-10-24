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

## 用 YouTube 的 CC 產生課程

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
