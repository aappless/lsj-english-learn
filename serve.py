"""本機伺服器：python serve.py [port] [--no-browser]

用伺服器開啟（而不是雙擊 index.html）YouTube 才能嵌入播放；
另外支援 HTTP Range，讓 videos/ 裡的本機影片可以拖曳進度。
網頁上的「製作課程」按鈕也靠這裡執行 tools/ 裡的工具（只有本機版有）。
"""
import http.server
import json
import os
import re
import subprocess
import sys
import threading
import webbrowser

ROOT = os.path.dirname(os.path.abspath(__file__))
args = [a for a in sys.argv[1:] if not a.startswith('--')]
PORT = int(args[0]) if args else 8000
NO_WINDOW = getattr(subprocess, 'CREATE_NO_WINDOW', 0)
YT_ID = re.compile(r'(?:youtu\.be/|[?&]v=|/embed/|/shorts/|/live/)([\w-]{11})|^([\w-]{11})$')


def run_tool(name, *tool_args):
    """執行 tools/ 裡的程式，回傳 (成功與否, 輸出文字, 錯誤訊息)。"""
    p = subprocess.run([sys.executable, os.path.join(ROOT, 'tools', name), *tool_args], cwd=ROOT,
                       capture_output=True, creationflags=NO_WINDOW,
                       env=dict(os.environ, PYTHONIOENCODING='utf-8'))
    out = p.stdout.decode('utf-8', 'replace').strip()
    err = p.stderr.decode('utf-8', 'replace').strip()
    return p.returncode == 0, out, err


class Handler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *a, **k):
        super().__init__(*a, directory=ROOT, **k)

    def end_headers(self):
        self.send_header('Accept-Ranges', 'bytes')
        self.send_header('Cache-Control', 'no-store')
        super().end_headers()

    def send_json(self, obj, code=200):
        body = json.dumps(obj, ensure_ascii=False).encode('utf-8')
        self.send_response(code)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path.split('?')[0] == '/api/status':
            return self.send_json({'local': True, 'hasKey': bool(os.environ.get('ANTHROPIC_API_KEY'))})
        return super().do_GET()

    def do_POST(self):
        if self.path != '/api/make':
            return self.send_json({'error': '找不到這個功能'}, 404)
        # 只接受 JSON：其他網站無法在沒有預檢的情況下送這種請求，避免被別的網頁亂呼叫
        if self.headers.get('Content-Type', '').split(';')[0].strip() != 'application/json':
            return self.send_json({'error': '格式錯誤'}, 400)
        try:
            req = json.loads(self.rfile.read(int(self.headers.get('Content-Length') or 0)) or b'{}')
        except ValueError:
            return self.send_json({'error': '格式錯誤'}, 400)
        m = YT_ID.search(str(req.get('url') or '').strip())
        if not m:
            return self.send_json({'error': '看不懂這個 YouTube 網址'}, 400)
        video_id = m.group(1) or m.group(2)

        ok, out, err = run_tool('yt_cc.py', video_id)
        if not ok:
            return self.send_json({'error': err or '抓字幕失敗', 'log': out}, 500)
        result = {'ok': True, 'file': f'{video_id}.json', 'log': out}
        if req.get('cards'):
            ok, out, err = run_tool('gen_cards.py', os.path.join('lessons', f'{video_id}.json'))
            result['log'] += '\n' + out
            if not ok:
                result['cardsError'] = err or '產生卡片失敗'
        self.send_json(result)

    def send_head(self):
        self._remaining = None
        rng = self.headers.get('Range')
        path = self.translate_path(self.path)
        m = re.match(r'bytes=(\d*)-(\d*)$', (rng or '').strip())
        if not m or not os.path.isfile(path):
            return super().send_head()

        size = os.path.getsize(path)
        s, e = m.groups()
        if s == '':
            start, end = max(0, size - int(e or 0)), size - 1
        else:
            start, end = int(s), min(int(e) if e else size - 1, size - 1)
        if start > end or start >= size:
            self.send_response(416)
            self.send_header('Content-Range', f'bytes */{size}')
            self.end_headers()
            return None

        f = open(path, 'rb')
        f.seek(start)
        self.send_response(206)
        self.send_header('Content-Type', self.guess_type(path))
        self.send_header('Content-Range', f'bytes {start}-{end}/{size}')
        self.send_header('Content-Length', str(end - start + 1))
        self.end_headers()
        self._remaining = end - start + 1
        return f

    def copyfile(self, source, outputfile):
        remaining = self._remaining
        try:
            if remaining is None:
                return super().copyfile(source, outputfile)
            while remaining > 0:
                buf = source.read(min(64 * 1024, remaining))
                if not buf:
                    break
                outputfile.write(buf)
                remaining -= len(buf)
        except (ConnectionResetError, ConnectionAbortedError, BrokenPipeError):
            pass  # 瀏覽器拖曳進度時會中斷舊連線，屬正常


if __name__ == '__main__':
    server = http.server.ThreadingHTTPServer(('127.0.0.1', PORT), Handler)
    url = f'http://127.0.0.1:{PORT}/'
    print(f'LSJ English Learn: {url}  (Ctrl+C 結束)')
    if '--no-browser' not in sys.argv:
        threading.Timer(0.8, lambda: webbrowser.open(url)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
