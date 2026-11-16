# 2.557.0 B (#4670): a tiny stand-in for the Anthropic Messages API for p2557_b_srvagent_test.py; runs INSIDE the test container
# (docker exec -d python /data/fake_anthropic.py) on port 8091: POST /v1/messages, GET /v1/models.
# A key must start with "sk-test-" (else 401 with a body that repeats the key: the server must never pass it on). Every request
# goes to /data/anthropic.log as one JSON line {path, model, key_ok, version_ok, tools (names), system, first, n} - never the key.
# Answers by markers in the first user message (the events): FAKE_GET_TASK <id> / FAKE_COMMENT <id> -> one tool call, then a
# text with the tool result; FAKE_SLOW -> waits 25 s; FAKE_HEAVY -> 400000 input tokens; otherwise "FAKE answer". A key with
# "nodefault" lists no claude-sonnet-5-5 (the fallback to the first Sonnet).
# 2.1294.0 (#6573): FAKE_THINK <id> -> thinking + redacted_thinking (with signature / data) before the tool call; the next call
# must carry the whole answer back unchanged, else 400 like the real provider. FAKE_REFUSAL -> stop_reason refusal;
# FAKE_CUT -> stop_reason max_tokens (only thinking). The log line also holds max_tokens.
import json
import re
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

LOG = open('/data/anthropic.log', 'a', buffering=1)
MODELS = [{'id': 'claude-opus-5-5', 'display_name': 'Claude Opus 5.5'}, {'id': 'claude-sonnet-5-5', 'display_name': 'Claude Sonnet 5.5'},
          {'id': 'claude-haiku-5-5', 'display_name': 'Claude Haiku 5.5'}]
THINK = [{'type': 'thinking', 'thinking': '', 'signature': 'sig-FAKE-6573-Zm9vYmFy'},
         {'type': 'redacted_thinking', 'data': 'red-FAKE-6573-YmF6'},
         {'type': 'text', 'text': 'Looking.'}]
NODEFAULT = [{'id': 'claude-opus-9-0', 'display_name': 'Claude Opus 9'}, {'id': 'claude-sonnet-9-0', 'display_name': 'Claude Sonnet 9'}]


def text_of(content):
    if isinstance(content, str):
        return content
    out = []
    for b in content or []:
        if b.get('type') == 'text':
            out.append(b.get('text') or '')
        elif b.get('type') == 'tool_result':
            out.append(('ERROR ' if b.get('is_error') else '') + text_of(b.get('content')))
    return '\n'.join(out)


class H(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def send(self, code, obj):
        data = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def auth(self):
        key = self.headers.get('x-api-key') or ''
        if not key.startswith('sk-test-'):
            self.send(401, {'type': 'error', 'error': {'type': 'authentication_error', 'message': f'invalid x-api-key {key}'}})
            return None
        return key

    def do_GET(self):
        key = self.auth()
        LOG.write(json.dumps({'path': self.path, 'key_ok': key is not None, 'version_ok': self.headers.get('anthropic-version') == '2023-06-01'}) + '\n')
        if key is None:
            return
        if not self.path.startswith('/v1/models'):
            return self.send(404, {'type': 'error', 'error': {'type': 'not_found_error', 'message': 'no'}})
        self.send(200, {'data': NODEFAULT if 'nodefault' in key else MODELS, 'has_more': False})

    def do_POST(self):
        n = int(self.headers.get('Content-Length') or 0)
        body = json.loads(self.rfile.read(n) or b'{}')
        key = self.auth()
        msgs = body.get('messages') or []
        first = text_of(msgs[0]['content']) if msgs else ''
        system = text_of(body.get('system'))
        LOG.write(json.dumps({'path': self.path, 'model': body.get('model'), 'key_ok': key is not None,
                              'version_ok': self.headers.get('anthropic-version') == '2023-06-01',
                              'tools': [t.get('name') for t in body.get('tools') or []], 'system': system, 'first': first,
                              'last': text_of(msgs[-1]['content']) if msgs else '', 'n': len(msgs), 'max_tokens': body.get('max_tokens')}, ensure_ascii=False) + '\n')
        if key is None:
            return
        heavy = 'FAKE_HEAVY' in first
        usage = {'input_tokens': 400000 if heavy else 100, 'output_tokens': 20, 'cache_read_input_tokens': 10, 'cache_creation_input_tokens': 5}
        last = msgs[-1] if msgs else {}
        if isinstance(last.get('content'), list) and any(b.get('type') == 'tool_result' for b in last['content']):
            m = re.search(r'FAKE_THINK (\d+)', first)
            if m and (len(msgs) < 2 or msgs[-2].get('content') != THINK + [
                    {'type': 'tool_use', 'id': 'toolu_t1', 'name': 'get_task', 'input': {'task_id': int(m.group(1))}}]):
                return self.send(400, {'type': 'error', 'error': {'type': 'invalid_request_error',
                                                                  'message': 'thinking blocks of the previous turn were changed or left out'}})
            return self.send(200, {'type': 'message', 'role': 'assistant', 'stop_reason': 'end_turn', 'usage': usage,
                                   'content': [{'type': 'text', 'text': 'FAKE result: ' + text_of(last['content'])[:1500]}]})
        m = re.search(r'FAKE_THINK (\d+)', first)
        if m:
            return self.send(200, {'type': 'message', 'role': 'assistant', 'stop_reason': 'tool_use', 'usage': usage,
                                   'content': THINK + [{'type': 'tool_use', 'id': 'toolu_t1', 'name': 'get_task',
                                                        'input': {'task_id': int(m.group(1))}}]})
        if 'FAKE_REFUSAL' in first:
            return self.send(200, {'type': 'message', 'role': 'assistant', 'stop_reason': 'refusal', 'usage': usage,
                                   'stop_details': {'type': 'refusal', 'category': None, 'explanation': 'x'},
                                   'content': [{'type': 'text', 'text': 'FAKE partial before the refusal'}]})
        if 'FAKE_CUT' in first:
            return self.send(200, {'type': 'message', 'role': 'assistant', 'stop_reason': 'max_tokens', 'usage': usage,
                                   'content': [THINK[0], {'type': 'text', 'text': 'FAKE cut mid'}]})
        m = re.search(r'FAKE_(GET_TASK|COMMENT) (\d+)', first)
        if m:
            tid = int(m.group(2))
            call = {'name': 'get_task', 'input': {'task_id': tid}} if m.group(1) == 'GET_TASK' else \
                {'name': 'add_comment', 'input': {'task_id': tid, 'body': 'FAKE comment of the server agent'}}
            return self.send(200, {'type': 'message', 'role': 'assistant', 'stop_reason': 'tool_use', 'usage': usage,
                                   'content': [{'type': 'text', 'text': 'Looking.'}, {'type': 'tool_use', 'id': 'toolu_1', **call}]})
        if 'FAKE_SLOW' in first:
            time.sleep(25)
        self.send(200, {'type': 'message', 'role': 'assistant', 'stop_reason': 'end_turn', 'usage': usage,
                        'content': [{'type': 'text', 'text': 'FAKE answer'}]})


ThreadingHTTPServer(('127.0.0.1', 8091), H).serve_forever()
