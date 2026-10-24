"""把 YouTube 影片本身的 CC 字幕轉成課程 JSON。

用法：
    python tools/yt_cc.py <YouTube 網址或 ID> [-o lessons/xxx.json] [--title 標題] [--no-zh]

- 英文：優先用人工字幕，沒有才用自動產生字幕
- 中文：優先用影片本身的繁中/中文字幕，沒有就用 YouTube 自動翻譯成繁中
- 產生的課程檔 notes（片語／文法卡片）是空的，之後再補（手動或交給 Claude）
- 會自動把新課程加入 lessons/index.json
"""
import argparse
import json
import os
import re
import sys
import urllib.parse
import urllib.request

from youtube_transcript_api import YouTubeTranscriptApi

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LESSONS = os.path.join(ROOT, 'lessons')
ZH_CODES = ['zh-Hant', 'zh-TW', 'zh-HK', 'zh', 'zh-Hans', 'zh-CN']


def parse_video_id(s):
    s = s.strip()
    if re.fullmatch(r'[\w-]{11}', s):
        return s
    m = re.search(r'(?:youtu\.be/|[?&]v=|/embed/|/shorts/|/live/)([\w-]{11})', s)
    if not m:
        sys.exit(f'看不懂這個 YouTube 網址：{s}')
    return m.group(1)


def fetch_title(video_id):
    url = 'https://www.youtube.com/oembed?format=json&url=' + urllib.parse.quote(
        f'https://www.youtube.com/watch?v={video_id}')
    try:
        with urllib.request.urlopen(url, timeout=10) as r:
            return json.load(r).get('title') or video_id
    except Exception:
        return video_id


def pick(transcripts, codes, manual_first=True):
    """依語言代碼挑字幕；manual_first 時人工字幕優先於自動字幕。"""
    order = (False, True) if manual_first else (True, False)
    for generated in order:
        for code in codes:
            for t in transcripts:
                if t.is_generated == generated and t.language_code == code:
                    return t
    return None


def clean(text):
    return re.sub(r'\s+', ' ', text.replace('\n', ' ')).strip()


def strip_credits(text):
    """拿掉字幕裡「譯者: xxx」「審譯者: xxx」這類名單行。"""
    return '\n'.join(l for l in text.split('\n')
                     if not re.search(r'(譯者|译者|審譯|审译|校對|校对|翻譯|翻译)\s*[:：]', l))


def fix_ends(lines):
    # 結束時間不超過下一句開頭（自動字幕的片段常互相重疊）
    for a, b in zip(lines, lines[1:]):
        a['end'] = min(a['end'], b['start'])
    return lines


def merge_sentences(snippets, zh_texts=None, max_len=8.0, max_gap=1.2):
    """把零碎的字幕片段合併成句子：遇到句號／問號／驚嘆號、停頓太久或太長就斷句。
    zh_texts 是和 snippets 一對一的中文（YouTube 自動翻譯的情況）。"""
    lines, cur = [], None
    for i, sn in enumerate(snippets):
        text = clean(sn.text)
        if not text:
            continue
        zh = clean(zh_texts[i]) if zh_texts else ''
        start, end = sn.start, sn.start + sn.duration
        if cur and (start - cur['end'] > max_gap or end - cur['start'] > max_len):
            lines.append(cur)
            cur = None
        if cur is None:
            cur = {'start': start, 'end': end, 'en': text, 'zh': zh}
        else:
            cur['en'] += ' ' + text
            cur['zh'] += zh
            cur['end'] = max(cur['end'], end)
        if re.search(r'[.?!]["\')\]]?$', text):
            lines.append(cur)
            cur = None
    if cur:
        lines.append(cur)
    return fix_ends(lines)


def group_by_zh(en_snippets, zh_snippets):
    """中英字幕各自斷句時（例如 TED 人工翻譯），以中文的分段為準：
    每個英文片段歸到時間重疊最多的那段中文，同一段中文的英文合成一句。"""
    lines = []
    for sn in en_snippets:
        text = clean(sn.text)
        if not text:
            continue
        start, end = sn.start, sn.start + sn.duration
        best, best_ov = None, 0.0
        for j, z in enumerate(zh_snippets):
            ov = min(end, z.start + z.duration) - max(start, z.start)
            if ov > best_ov:
                best, best_ov = j, ov
        if lines and best is not None and lines[-1]['_z'] == best:
            lines[-1]['en'] += ' ' + text
            lines[-1]['end'] = max(lines[-1]['end'], end)
        else:
            lines.append({'start': start, 'end': end, 'en': text, '_z': best})
    used = set()
    for ln in lines:
        z = ln.pop('_z')
        ln['zh'] = ''
        if z is not None and z not in used:
            used.add(z)
            ln['zh'] = clean(strip_credits(zh_snippets[z].text))
    return fix_ends(lines)


def update_index(file_name, title):
    path = os.path.join(LESSONS, 'index.json')
    try:
        with open(path, encoding='utf-8') as f:
            index = json.load(f)
    except FileNotFoundError:
        index = []
    index = [it for it in index if it.get('file') != file_name]
    index.append({'file': file_name, 'title': title})
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(index, f, ensure_ascii=False, indent=2)
        f.write('\n')


def main():
    ap = argparse.ArgumentParser(description='YouTube CC 字幕 → 課程 JSON')
    ap.add_argument('video', help='YouTube 網址或 11 碼影片 ID')
    ap.add_argument('-o', '--out', help='輸出檔（預設 lessons/<影片ID>.json）')
    ap.add_argument('--title', help='課程標題（預設抓 YouTube 影片標題）')
    ap.add_argument('--no-zh', action='store_true', help='不要中文字幕')
    args = ap.parse_args()

    video_id = parse_video_id(args.video)
    try:
        transcripts = list(YouTubeTranscriptApi().list(video_id))
    except Exception as e:
        sys.exit(f'這支影片抓不到字幕：{type(e).__name__}\n'
                 '（沒有 CC、影片受限制，或 YouTube 暫時擋了這台電腦的請求）')

    print('可用字幕：', ', '.join(
        f"{t.language_code}{'(自動)' if t.is_generated else ''}" for t in transcripts))

    en = pick(transcripts, ['en', 'en-US', 'en-GB']) or next(
        (t for t in transcripts if t.language_code.startswith('en')), None)
    if not en:
        sys.exit('這支影片沒有英文字幕，請改用 Whisper 產生字幕')
    print(f"英文：{en.language_code}{'（自動產生，斷句可能不準）' if en.is_generated else '（人工字幕）'}")
    en_snippets = en.fetch().snippets
    zh = None if args.no_zh else pick(transcripts, ZH_CODES)

    if zh:
        print(f'中文：{zh.language_code}（影片本身字幕，依中文分段對齊）')
        lines = group_by_zh(en_snippets, zh.fetch().snippets)
    else:
        zh_texts = None
        if not args.no_zh and en.is_translatable:
            print('中文：YouTube 自動翻譯成繁中')
            try:
                tr = en.translate('zh-Hant').fetch().snippets
                if len(tr) == len(en_snippets):
                    zh_texts = [s.text for s in tr]
                else:
                    print('  翻譯分段和英文對不上，中文先留空')
            except Exception as e:
                print(f'  自動翻譯失敗（{type(e).__name__}），中文先留空')
        lines = merge_sentences(en_snippets, zh_texts)

    title = args.title or fetch_title(video_id)
    lesson = {
        'title': title,
        'source': {'type': 'youtube', 'id': video_id},
        'lines': [{'start': round(ln['start'], 2), 'end': round(ln['end'], 2),
                   'en': ln['en'], 'zh': ln['zh'], 'notes': []} for ln in lines],
    }

    out = args.out or os.path.join(LESSONS, f'{video_id}.json')
    os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
    with open(out, 'w', encoding='utf-8') as f:
        json.dump(lesson, f, ensure_ascii=False, indent=2)
        f.write('\n')
    if os.path.dirname(os.path.abspath(out)) == LESSONS:
        update_index(os.path.basename(out), title)
    print(f'完成：{len(lines)} 句 → {out}')


if __name__ == '__main__':
    main()
