"""Loopback-only HTTP entry point; Python standard library, no public deployment."""
import argparse
import hmac
import json
import os
import re
import secrets
import sys
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit

from .chat import ChatError, ChatService
from .cli import PROJECT_ROOT, read
from .model_client import load_env


class ChatHTTPServer(ThreadingHTTPServer):
    daemon_threads = True


class ChatHandler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        pass

    def setup(self):
        super().setup()
        self.connection.settimeout(10)

    def respond(self, status, body, html=False):
        data = body.encode('utf-8') if html else json.dumps(body, ensure_ascii=False, allow_nan=False).encode('utf-8')
        self.send_response(status)
        self.send_header('Content-Type', 'text/html; charset=utf-8' if html else 'application/json; charset=utf-8')
        self.send_header('Content-Length', str(len(data)))
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('X-Frame-Options', 'DENY')
        self.send_header('Referrer-Policy', 'no-referrer')
        self.send_header('Content-Security-Policy', "default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; connect-src 'self'; img-src 'self' data:; frame-ancestors 'none'; base-uri 'none'")
        self.end_headers()
        self.wfile.write(data)

    def authorize(self, api=True):
        port = self.server.server_address[1]
        hosts = {f'127.0.0.1:{port}', f'localhost:{port}'}
        if self.headers.get('Host') not in hosts:
            raise ChatError('forbidden_host', '只接受本机地址。', 403)
        origin = self.headers.get('Origin')
        if origin and origin not in {'http://' + host for host in hosts}:
            raise ChatError('forbidden_origin', '请求来源不匹配，请从本地页面操作。', 403)
        token = self.headers.get('X-Agent-Token', '')
        if api and (not re.fullmatch(r'[a-f0-9]{64}', token)
                    or not hmac.compare_digest(token, self.server.api_token)):
            raise ChatError('forbidden_token', '页面连接已失效，请刷新。', 403)

    def body(self):
        try:
            size = int(self.headers.get('Content-Length', '-1'))
        except ValueError:
            raise ChatError('invalid_body', '请求格式不正确。') from None
        if size > 65536:
            raise ChatError('body_too_large', '请求过大，请缩短文本或分次补充素材。', 413)
        if size <= 0:
            raise ChatError('invalid_body', '请求不能为空。')
        try:
            value = json.loads(self.rfile.read(size).decode('utf-8'), parse_constant=lambda value: None)
            if not isinstance(value, dict):
                raise ValueError()
            return value
        except (ValueError, UnicodeError):
            raise ChatError('invalid_body', '请求必须是 JSON 对象。') from None

    def do_GET(self):
        self.dispatch('GET')

    def do_POST(self):
        self.dispatch('POST')

    def dispatch(self, method):
        try:
            path = urlsplit(self.path).path
            self.authorize(api=path != '/')
            if path == '/' and method == 'GET':
                page = Path(__file__).with_name('web').joinpath('index.html').read_text(encoding='utf-8')
                return self.respond(200, page.replace('__API_TOKEN__', self.server.api_token), html=True)
            if path == '/api/config' and method == 'GET':
                return self.respond(200, {'default_mode':self.server.default_mode,
                    'has_api_key':bool(os.getenv('VIDEO_API_KEY') or os.getenv('DASHSCOPE_API_KEY')),
                    'model':os.getenv('VIDEO_MODEL', 'qwen-plus'),
                    'products':sorted({m['product'] for m in self.server.service.materials})})
            if path == '/api/sessions' and method == 'POST':
                data = self.body()
                if set(data) - {'mode'}:
                    raise ChatError('invalid_body', '新会话参数不正确。')
                return self.respond(201, self.server.service.create_session(data.get('mode', self.server.default_mode)))
            match = re.fullmatch(r'/api/sessions/([a-f0-9]{32})(/messages)?', path)
            if match:
                ident, messages = match.groups()
                if method == 'GET' and not messages:
                    return self.respond(200, self.server.service.get_session(ident))
                if method == 'POST' and messages:
                    data = self.body()
                    if set(data) - {'message','attachments'}:
                        raise ChatError('invalid_body', '消息参数不正确。')
                    return self.respond(200, self.server.service.send(ident, data.get('message'), data.get('attachments')))
            raise ChatError('not_found', '未找到页面或会话。', 404)
        except ChatError as exc:
            self.respond(exc.status, {'error':exc.code, 'message':str(exc)})
        except (BrokenPipeError, ConnectionResetError):
            pass
        except OSError:
            self.respond(500, {'error':'storage_error', 'message':'读取或保存本地文件失败，请检查运行窗口。'})
        except Exception as exc:
            print('Chat request failed: ' + type(exc).__name__, file=sys.stderr)
            self.respond(500, {'error':'internal_error', 'message':'本轮出现程序错误，请查看运行窗口。'})


def create_server(service, port=8765, mode='mock'):
    if mode not in {'mock','real'}:
        raise ValueError('invalid mode')
    server = ChatHTTPServer(('127.0.0.1', port), ChatHandler)
    server.service, server.default_mode = service, mode
    server.api_token = secrets.token_hex(32)
    return server


def main():
    parser = argparse.ArgumentParser(description='本地短视频脚本对话页面')
    parser.add_argument('--port', type=int, default=8765)
    parser.add_argument('--mode', choices=['mock','real'], default='mock')
    parser.add_argument('--env-file', default=str(PROJECT_ROOT/'.env'))
    parser.add_argument('--no-browser', action='store_true')
    args = parser.parse_args()
    if not 0 <= args.port <= 65535:
        parser.error('port must be in [0, 65535]')
    try:
        if Path(args.env_file).is_file():
            load_env(args.env_file)
        service = ChatService(PROJECT_ROOT/'runs/chat', read(PROJECT_ROOT/'data/materials.json'),
                              read(PROJECT_ROOT/'data/brand_rules.json'))
        server = create_server(service, args.port, args.mode)
    except (OSError, ValueError) as exc:
        print('Chat startup error: ' + str(exc), file=sys.stderr)
        print('端口被占用时可在脚本参数中填写 --port 8766。', file=sys.stderr)
        return 1
    url = f'http://127.0.0.1:{server.server_address[1]}/'
    print('Short video script chat: ' + url, flush=True)
    print('在浏览器对话；停止 PyCharm 运行会关闭服务。记录保存在项目 runs/chat/。', flush=True)
    if not args.no_browser:
        opener = threading.Timer(.4, webbrowser.open, args=(url,))
        opener.daemon = True
        opener.start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0
