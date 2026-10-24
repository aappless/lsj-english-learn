"""用 Claude 幫課程檔自動產生片語／句型／文法卡片（並重新對齊中文翻譯）。

用法：
    python tools/gen_cards.py lessons/xxx.json [--level 高中] [--keep-zh] [--restart]

- 需要 Anthropic API 金鑰：設定環境變數 ANTHROPIC_API_KEY
- 每次送 30 句給 Claude；每批完成就存檔，中斷後重跑會從上次的位置繼續
- 第一次執行會先備份成 xxx.json.bak
"""
import argparse
import json
import os
import shutil
import sys

import anthropic

MODEL = 'claude-opus-5-5'
BATCH = 30

SYSTEM = """你是台灣的英文老師，負責把影片逐字稿做成英文教材。學習者母語是繁體中文（台灣用語）。

對每一句英文：
1. zh：寫出自然、精準的繁體中文翻譯，只翻這一句，不要混入前後句的內容。
2. notes：挑出「值得教」的重點，做成教學卡片。不是每句都要有；平均每 2～3 句一張即可，寧缺勿濫。
   優先挑：母語人士常用但課本少教的詞塊、實用句型、容易誤用的文法、對學習者程度有挑戰的單字。
   不要挑：太基本的字（the, is, good）、專有名詞、和「已教過」清單重複的內容。

卡片欄位：
- type：chunk（詞塊／慣用語）、pattern（句型，用公式表示）、grammar（文法觀念）、word（單字）
- match：這句英文中要高亮的字串，必須逐字出現在英文原句裡
- zhMatch：你的中文翻譯中對應的字串，必須逐字出現在 zh 裡；找不到對應就給空字串
- title：卡片標題。chunk/word 用原字詞；pattern 用公式，例如 "one of the most + adj. + Ns"
- meaning：簡短中文意思，例如「說白了／直說吧」
- explain：一兩句中文說明用法、語氣或常見錯誤
- example：另造一個新的例句（en）與翻譯（zh），不要照抄原句"""

NOTE_SCHEMA = {
    'type': 'object',
    'properties': {
        'type': {'type': 'string', 'enum': ['chunk', 'pattern', 'grammar', 'word']},
        'match': {'type': 'string'},
        'zhMatch': {'type': 'string'},
        'title': {'type': 'string'},
        'meaning': {'type': 'string'},
        'explain': {'type': 'string'},
        'example': {
            'type': 'object',
            'properties': {'en': {'type': 'string'}, 'zh': {'type': 'string'}},
            'required': ['en', 'zh'],
            'additionalProperties': False,
        },
    },
    'required': ['type', 'match', 'zhMatch', 'title', 'meaning', 'explain', 'example'],
    'additionalProperties': False,
}

OUTPUT_SCHEMA = {
    'type': 'object',
    'properties': {
        'lines': {
            'type': 'array',
            'items': {
                'type': 'object',
                'properties': {
                    'i': {'type': 'integer'},
                    'zh': {'type': 'string'},
                    'notes': {'type': 'array', 'items': NOTE_SCHEMA},
                },
                'required': ['i', 'zh', 'notes'],
                'additionalProperties': False,
            },
        },
    },
    'required': ['lines'],
    'additionalProperties': False,
}


def build_prompt(lines, start, end, level, taught, keep_zh):
    ctx_before = lines[max(0, start - 3):start]
    parts = [f'學習者程度：{level}']
    if taught:
        parts.append('已教過（不要重複）：' + '；'.join(taught[-150:]))
    if ctx_before:
        parts.append('前文（只供理解，不用處理）：\n' + '\n'.join(ln['en'] for ln in ctx_before))
    items = []
    for i in range(start, end):
        ln = lines[i]
        item = {'i': i, 'en': ln['en']}
        if keep_zh:
            item['zh'] = ln.get('zh', '')
        items.append(item)
    if keep_zh:
        parts.append('這批句子已有中文翻譯，zh 請原樣輸出，zhMatch 也要從這個翻譯中取。')
    parts.append('請處理以下句子，每句都要輸出（i 照抄）：\n' + json.dumps(items, ensure_ascii=False, indent=1))
    return '\n\n'.join(parts)


def call_claude(client, prompt, effort):
    with client.beta.messages.stream(
        model=MODEL,
        max_tokens=64000,
        betas=['server-side-fallback-2026-07-01'],
        fallbacks='default',
        output_config={
            'effort': effort,
            'format': {'type': 'json_schema', 'schema': OUTPUT_SCHEMA},
        },
        system=SYSTEM,
        messages=[{'role': 'user', 'content': prompt}],
    ) as stream:
        msg = stream.get_final_message()
    if msg.stop_reason == 'refusal':
        raise RuntimeError('Claude 拒絕處理這批內容')
    if msg.stop_reason == 'max_tokens':
        raise RuntimeError('輸出超過長度上限，請調小每批句數（--batch）')
    text = next(b.text for b in msg.content if b.type == 'text')
    return json.loads(text), msg.usage


def clean_note(note, en, zh):
    """match 必須真的出現在英文句中，否則這張卡片無法高亮，丟掉；zhMatch 對不上就清空。"""
    if not note['match'] or note['match'].lower() not in en.lower():
        return None
    if note['zhMatch'] and note['zhMatch'] not in zh:
        note['zhMatch'] = ''
    return note


def save(path, lesson):
    tmp = path + '.tmp'
    with open(tmp, 'w', encoding='utf-8') as f:
        json.dump(lesson, f, ensure_ascii=False, indent=2)
        f.write('\n')
    os.replace(tmp, path)


def main():
    ap = argparse.ArgumentParser(description='用 Claude 產生片語／句型／文法卡片')
    ap.add_argument('lesson', help='課程 JSON 檔')
    ap.add_argument('--level', default='台灣高中到大學程度', help='學習者程度（例如：國中、高中、多益 700）')
    ap.add_argument('--keep-zh', action='store_true', help='保留現有中文翻譯，不重新翻譯')
    ap.add_argument('--restart', action='store_true', help='從頭重新產生（忽略上次進度）')
    ap.add_argument('--batch', type=int, default=BATCH, help=f'每次送幾句（預設 {BATCH}）')
    ap.add_argument('--effort', default='medium', choices=['low', 'medium', 'high', 'xhigh', 'max'],
                    help='Claude 思考深度（預設 medium）')
    args = ap.parse_args()

    if not os.environ.get('ANTHROPIC_API_KEY') and not os.environ.get('ANTHROPIC_AUTH_TOKEN'):
        sys.exit('找不到 API 金鑰：請先設定環境變數 ANTHROPIC_API_KEY')

    path = args.lesson
    with open(path, encoding='utf-8') as f:
        lesson = json.load(f)
    lines = lesson.get('lines') or []
    if not lines:
        sys.exit('課程檔沒有句子')

    if not os.path.exists(path + '.bak'):
        shutil.copyfile(path, path + '.bak')

    progress = lesson.setdefault('cards', {})
    start = 0 if args.restart else progress.get('done', 0)
    if start >= len(lines):
        print('這個課程已經全部產生過了；要重做請加 --restart')
        return
    if start:
        print(f'從第 {start + 1} 句繼續（共 {len(lines)} 句）')

    taught = [n['title'] for ln in lines[:start] for n in ln.get('notes') or []]
    client = anthropic.Anthropic()
    total_in = total_out = 0

    while start < len(lines):
        end = min(start + args.batch, len(lines))
        print(f'處理第 {start + 1}～{end} 句…', flush=True)
        try:
            result, usage = call_claude(
                client, build_prompt(lines, start, end, args.level, taught, args.keep_zh), args.effort)
        except anthropic.AuthenticationError:
            sys.exit('API 金鑰無效，請檢查 ANTHROPIC_API_KEY')
        except anthropic.RateLimitError:
            sys.exit('超過使用量限制，請稍後再執行（進度已保存）')
        except (anthropic.APIConnectionError, anthropic.APIStatusError, RuntimeError) as e:
            sys.exit(f'第 {start + 1}～{end} 句失敗：{e}（進度已保存，重新執行即可繼續）')
        total_in += usage.input_tokens
        total_out += usage.output_tokens

        by_index = {item['i']: item for item in result['lines']}
        count = 0
        for i in range(start, end):
            item = by_index.get(i)
            if not item:
                continue
            ln = lines[i]
            if not args.keep_zh and item['zh']:
                ln['zh'] = item['zh']
            notes = [clean_note(n, ln['en'], ln.get('zh', '')) for n in item['notes']]
            ln['notes'] = [n for n in notes if n]
            taught += [n['title'] for n in ln['notes']]
            count += len(ln['notes'])

        progress.update({'done': end, 'model': MODEL, 'level': args.level})
        save(path, lesson)
        print(f'  新增 {count} 張卡片，已存檔', flush=True)
        start = end

    cost = total_in / 1e6 * 4 + total_out / 1e6 * 20
    print(f'完成！共 {sum(len(ln.get("notes") or []) for ln in lines)} 張卡片')
    print(f'用量：輸入 {total_in:,} / 輸出 {total_out:,} tokens，約 US${cost:.2f}')


if __name__ == '__main__':
    main()
