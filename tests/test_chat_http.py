import importlib.util
import json
import sys
import tempfile
import threading
import subprocess
import time
import unittest
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'src'))
from video_agent.cli import read


class ChatHTTPTests(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(importlib.util.find_spec('video_agent.chat_server'), '本地网页接口尚未实现')
        from video_agent.chat import ChatService
        from video_agent.chat_server import create_server
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.service = ChatService(self.temp.name, read(ROOT/'data/materials.json'), read(ROOT/'data/brand_rules.json'))
        self.server = create_server(self.service, port=0)
        self.worker = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.worker.start()
        self.addCleanup(self.stop)
        self.url = 'http://127.0.0.1:' + str(self.server.server_address[1])

    def stop(self):
        self.server.shutdown()
        self.server.server_close()
        self.worker.join(2)

    def request(self, path, body=None, headers=None, token=True):
        values = {'X-Agent-Token':self.server.api_token} if token else {}
        values.update(headers or {})
        data = None if body is None else json.dumps(body).encode()
        if data is not None:
            values['Content-Type'] = 'application/json'
        req = urllib.request.Request(self.url+path, data=data, headers=values)
        try:
            with urllib.request.urlopen(req, timeout=5) as response:
                return response.status, response.read(), response.headers
        except urllib.error.HTTPError as exc:
            return exc.code, exc.read(), exc.headers

    def test_local_page_and_authenticated_config_are_available(self):
        status, body, headers = self.request('/', token=False)
        self.assertEqual(status, 200)
        self.assertEqual(headers.get_content_type(), 'text/html')
        self.assertIn(b'<html', body)
        self.assertEqual(headers['X-Frame-Options'], 'DENY')
        status, body, _ = self.request('/api/config')
        self.assertEqual(status, 200)
        self.assertIsInstance(json.loads(body)['has_api_key'], bool)
        self.assertNotIn('VIDEO_API_KEY', json.loads(body))

    def test_api_requires_token_and_rejects_foreign_origin_or_host(self):
        self.assertEqual(self.request('/api/config', token=False)[0], 403)
        self.assertEqual(self.request('/api/sessions', {'mode':'mock'}, headers={'Origin':'https://elsewhere.example'})[0], 403)
        self.assertEqual(self.request('/api/config', headers={'Host':'elsewhere.example'})[0], 403)

    def test_roundtrip_generation_and_refresh_share_the_same_session(self):
        status, data, _ = self.request('/api/sessions', {'mode':'mock'})
        self.assertEqual(status, 201)
        ident = json.loads(data)['id']
        status, data, _ = self.request(f'/api/sessions/{ident}/messages',
            {'message':'剪映盒演示版字幕介绍，受众：学生\n平台：抖音\n风格：自然\n时长：30秒'})
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(data)['result']['status'], 'completed')
        status, data, _ = self.request('/api/sessions/'+ident)
        self.assertEqual(status, 200)
        self.assertEqual(len(json.loads(data)['messages']), 2)

    def test_busy_session_rejects_overlapping_send(self):
        session = self.service.create_session('mock')['id']
        lock = self.service._lock(session)
        with lock:
            status, data, _ = self.request(f'/api/sessions/{session}/messages', {'message':'你好'})
        self.assertEqual(status, 409)
        self.assertEqual(json.loads(data)['error'], 'session_busy')

    def test_unknown_routes_bad_json_and_oversized_body_are_controlled(self):
        self.assertEqual(self.request('/.env')[0], 404)
        self.assertEqual(self.request('/api/sessions', {'mode':'other'})[0], 400)
        self.assertEqual(self.request('/api/sessions', {'mode':'mock','unused':'x'*70000})[0], 413)
        req = urllib.request.Request(self.url+'/api/sessions', data=b'{bad',
                                     headers={'X-Agent-Token':self.server.api_token})
        with self.assertRaises(urllib.error.HTTPError) as failure:
            urllib.request.urlopen(req, timeout=5)
        self.assertEqual(failure.exception.code, 400)

    def test_non_ascii_auth_header_is_rejected_without_internal_error(self):
        self.assertEqual(self.request('/api/config', headers={'X-Agent-Token':'é'})[0], 403)

    def test_chat_launcher_resolves_defaults_from_a_different_working_directory(self):
        log = Path(self.temp.name)/'startup.log'
        with log.open('w', encoding='utf-8') as stream:
            process = subprocess.Popen([sys.executable,str(ROOT/'run_chat.py'),'--no-browser','--port','0'],
                                       cwd=ROOT/'docs', stdout=stream, stderr=stream)
            try:
                import re
                address = None
                deadline = time.monotonic() + 5
                while time.monotonic() < deadline:
                    match = re.search(r'http://127\.0\.0\.1:\d+/', log.read_text(encoding='utf-8',errors='replace'))
                    if match:
                        address = match.group()
                        break
                    if process.poll() is not None:
                        break
                    time.sleep(.05)
                self.assertIsNotNone(address)
                with urllib.request.urlopen(address, timeout=3) as response:
                    self.assertEqual(response.status, 200)
            finally:
                process.terminate()
                process.wait(timeout=3)


if __name__ == '__main__':
    unittest.main()
