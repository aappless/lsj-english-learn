"""本機伺服器：python serve.py [port] [--no-browser]

用伺服器開啟（而不是雙擊 index.html）YouTube 才能嵌入播放；
另外支援 HTTP Range，讓 videos/ 裡的本機影片可以拖曳進度。
"""
import http.server
import os
import re
import sys
import threading
import webbrowser

ROOT = os.path.dirname(os.path.abspath(__file__))
args = [a for a in sys.argv[1:] if not a.startswith('--')]
PORT = int(args[0]) if args else 8000


class Handler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *a, **k):
        super().__init__(*a, directory=ROOT, **k)

    def end_headers(self):
        self.send_header('Accept-Ranges', 'bytes')
        self.send_header('Cache-Control', 'no-store')
        super().end_headers()

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
