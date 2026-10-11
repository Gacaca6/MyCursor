"""Local authenticated WebSocket receiver. Only one phone owns input at a time."""
from __future__ import annotations

import asyncio
import contextlib
import hmac
import math
import secrets
import time
from collections import deque
from pathlib import Path
from aiohttp import web, WSMsgType

STATIC = Path(__file__).with_name('web')
ALLOWED_KEYS = frozenset(('enter tab backspace escape delete left up right down home end '
    'pageup pagedown space f5 volumeup volumedown mute playpause copy paste undo '
    'selectall switchwindow desktop start').split())


def number(data, key, limit):
    value = data.get(key, 0)
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError('Invalid movement')
    if abs(value) > limit:
        raise ValueError('Movement exceeds limit')
    return value


class PhoneServer:
    def __init__(self, driver, token=None, on_status=None, laser_supported=False):
        self.driver = driver
        self.token = token or secrets.token_urlsafe(24)
        self.on_status = on_status or (lambda message: None)
        self.socket = None
        self.paused = False
        self.laser_supported = laser_supported
        self.laser = False
        self.last_seen = 0
        self._pair_code = ''
        self._code_expires = 0
        self._code_failures = deque()
        self.app = web.Application(client_max_size=16384, middlewares=[self.headers])
        self.app.router.add_get('/', self.index)
        self.app.router.add_get('/app.js', self.script)
        self.app.router.add_get('/scanner.js', self.scanner_script)
        self.app.router.add_get('/jsqr.js', self.qr_script)
        self.app.router.add_get('/zxing.js', self.zxing_script)
        self.app.router.add_get('/zxing_reader.wasm', self.zxing_wasm)
        self.app.router.add_get('/style.css', self.style)
        self.app.router.add_get('/health', self.health)
        self.app.router.add_post('/pair', self.pair_cookie)
        self.app.router.add_post('/pair-code', self.pair_code)
        self.app.router.add_get('/manifest.webmanifest', self.manifest)
        self.app.router.add_get('/sw.js', self.service_worker)
        self.app.router.add_get('/icon-{size}.png', self.icon)
        self.app.router.add_get('/ws', self.connect)
        self.app.on_cleanup.append(self.cleanup)

    @web.middleware
    async def headers(self, request, handler):
        response = await handler(request)
        if not isinstance(response, web.WebSocketResponse):
            response.headers.update({
                'Cache-Control': 'no-store', 'X-Content-Type-Options': 'nosniff',
                'Referrer-Policy': 'no-referrer', 'X-Frame-Options': 'DENY',
                'Content-Security-Policy': "default-src 'self'; connect-src 'self'; img-src 'self' blob:; media-src 'self' blob:; style-src 'self'; script-src 'self' 'wasm-unsafe-eval'; frame-ancestors 'none'",
            })
        return response

    async def index(self, request):
        return web.FileResponse(STATIC / 'index.html')

    async def script(self, request):
        return web.FileResponse(STATIC / 'app.js')

    async def scanner_script(self, request):
        return web.FileResponse(STATIC / 'scanner.js')

    async def qr_script(self, request):
        return web.FileResponse(STATIC / 'jsqr.js')

    async def zxing_script(self, request):
        return web.FileResponse(STATIC / 'zxing.js')

    async def zxing_wasm(self, request):
        return web.FileResponse(STATIC / 'zxing_reader.wasm', headers={'Content-Type': 'application/wasm'})

    @property
    def pairing_code(self):
        if time.monotonic() >= self._code_expires:
            self._pair_code = f'{secrets.randbelow(100_000_000):08d}'
            self._code_expires = time.monotonic() + 600
        return self._pair_code

    async def pair_code(self, request):
        if request.headers.get('Origin') != f'{request.scheme}://{request.host}':
            return web.json_response({'error': 'Open MyCursor on this PC’s address.'}, status=403)
        now = time.monotonic()
        while self._code_failures and now - self._code_failures[0] >= 60:
            self._code_failures.popleft()
        if len(self._code_failures) >= 5:
            return web.json_response({'error': 'Too many attempts. Wait one minute.'}, status=429)
        try:
            data = await request.json()
            code = data.get('code', '')
        except (ValueError, AttributeError, TypeError):
            code = ''
        if not isinstance(code, str) or len(code) != 8 or not code.isascii() or not code.isdigit() or not hmac.compare_digest(code, self.pairing_code):
            self._code_failures.append(now)
            return web.json_response({'error': 'Check the current code on your PC.'}, status=401)
        return web.json_response({'token': self.token})

    async def style(self, request):
        return web.FileResponse(STATIC / 'style.css')

    async def health(self, request):
        return web.json_response({'app': 'MyCursor Phone', 'connected': self.socket is not None, 'paused': self.paused})

    async def pair_cookie(self, request):
        if request.headers.get('Origin') != f'{request.scheme}://{request.host}':
            raise web.HTTPForbidden()
        try:
            data = await request.json()
            token = data.get('token', '')
            valid = isinstance(token, str) and hmac.compare_digest(token, self.token)
        except (ValueError, TypeError, AttributeError):
            valid = False
        if not valid:
            raise web.HTTPForbidden()
        response = web.json_response({'paired': True})
        response.set_cookie('mycursor_pair', self.token, httponly=True,
                            samesite='Strict', secure=request.secure, max_age=31536000)
        return response

    async def manifest(self, request):
        cookie = request.cookies.get('mycursor_pair', '')
        try:
            paired = hmac.compare_digest(cookie, self.token)
        except TypeError:
            paired = False
        # A credential-free request never receives the secret. Preserve pairing
        # in the installed start URL: iOS may use separate Home Screen storage.
        start = '/#' + self.token if paired else '/'
        return web.json_response({
            'id': '/', 'name': 'MyCursor Phone Touchpad', 'short_name': 'MyCursor',
            'description': 'Use your iPhone as your Windows touchpad.',
            'start_url': start, 'scope': '/', 'display': 'standalone',
            'background_color': '#0b1120', 'theme_color': '#0b1120',
            'icons': [{'src': f'/icon-{size}.png', 'sizes': f'{size}x{size}',
                       'type': 'image/png', 'purpose': 'any maskable'} for size in (192, 512)],
        }, content_type='application/manifest+json')

    async def service_worker(self, request):
        return web.FileResponse(STATIC / 'sw.js')

    async def icon(self, request):
        size = request.match_info['size']
        if size not in ('180', '192', '512'):
            raise web.HTTPNotFound()
        return web.FileResponse(STATIC / f'icon-{size}.png')

    async def state(self):
        if self.socket is not None and not self.socket.closed:
            await self.socket.send_json({'type': 'state', 'paused': self.paused,
                                        'laser': self.laser, 'laserSupported': self.laser_supported})

    async def toggle(self):
        self.paused = not self.paused
        self.driver.release_all()
        self.on_status('Paused' if self.paused else ('Phone connected' if self.socket else 'Waiting for phone'))
        await self.state()

    def dispatch(self, data):
        if not isinstance(data, dict):
            raise ValueError('Expected an object')
        kind = data.get('type')
        if kind in ('ping', 'release'):
            if kind == 'release':
                self.driver.release_all()
            return
        if self.paused:
            return
        button = data.get('button', 'left')
        if kind in ('click', 'down', 'up'):
            if button not in ('left', 'right', 'middle'):
                raise ValueError('Invalid button')
            if kind == 'click':
                if data.get('double') is True:
                    self.driver.double_click(button)
                else:
                    self.driver.click(button)
            elif kind == 'down':
                self.driver.press(button)
            else:
                self.driver.release(button)
        elif kind == 'move':
            self.driver.move(number(data, 'dx', 2000), number(data, 'dy', 2000))
        elif kind == 'scroll':
            self.driver.scroll(number(data, 'dy', 30))
            self.driver.hscroll(number(data, 'dx', 30))
        elif kind == 'key':
            if data.get('key') not in ALLOWED_KEYS:
                raise ValueError('Invalid key')
            self.driver.key(data['key'])
        elif kind == 'text':
            value = data.get('text')
            if not isinstance(value, str) or len(value) > 2000:
                raise ValueError('Text must be at most 2000 characters')
            # Reject unpaired surrogates before injecting any of the text.
            value.encode('utf-16-le')
            self.driver.text(value)
        elif kind == 'laser':
            if not self.laser_supported:
                raise ValueError('Laser pointer needs the PC pairing window running.')
            if not isinstance(data.get('enabled'), bool):
                raise ValueError('Invalid laser setting')
            self.laser = data['enabled']
        else:
            raise ValueError('Unknown command')

    async def connect(self, request):
        # Prevent unrelated websites from opening a socket to this PC.
        if request.headers.get('Origin') != f'{request.scheme}://{request.host}':
            raise web.HTTPForbidden(text='Open the MyCursor page to connect.')
        ws = web.WebSocketResponse(heartbeat=5, max_msg_size=16384)
        await ws.prepare(request)
        owned = False
        try:
            first = await asyncio.wait_for(ws.receive(), timeout=5)
            if first.type != WSMsgType.TEXT:
                await ws.close(code=1008, message=b'Pairing required')
                return ws
            auth = first.json()
            token = auth.get('token', '') if isinstance(auth, dict) else ''
            if not isinstance(token, str) or not hmac.compare_digest(token, self.token):
                await ws.send_json({'type': 'error', 'message': 'Pairing expired. Scan the PC QR code again.', 'fatal': True})
                await ws.close(code=1008)
                return ws
            if self.socket is not None:
                await ws.send_json({'type': 'error', 'message': 'Another phone is connected. Disconnect it first.', 'fatal': True})
                await ws.close(code=1008)
                return ws
            self.socket = ws
            owned = True
            self.last_seen = time.monotonic()
            self.driver.release_all()
            self.on_status('Paused' if self.paused else 'Phone connected')
            await self.state()
            async for msg in ws:
                if msg.type != WSMsgType.TEXT:
                    break
                try:
                    data = msg.json()
                    self.last_seen = time.monotonic()
                    if isinstance(data, dict) and data.get('type') == 'pause':
                        await self.toggle()
                    else:
                        self.dispatch(data)
                        if isinstance(data, dict) and data.get('type') == 'laser':
                            await self.state()
                    if isinstance(data, dict) and data.get('type') == 'ping':
                        await ws.send_json({'type': 'pong'})
                except (ValueError, TypeError, KeyError, OSError) as exc:
                    self.driver.release_all()
                    await ws.send_json({'type': 'error', 'message': str(exc)})
        except (asyncio.TimeoutError, ValueError, TypeError):
            await ws.close(code=1008)
        finally:
            if owned:
                self.driver.release_all()
                self.laser = False
                self.socket = None
                self.on_status('Paused' if self.paused else 'Waiting for phone')
        return ws

    async def watchdog(self):
        while True:
            await asyncio.sleep(0.25)
            if self.socket is not None and time.monotonic() - self.last_seen > 3:
                self.driver.release_all()
                await self.socket.close(code=1001, message=b'Phone asleep')

    async def cleanup(self, app):
        if self.socket is not None:
            await self.socket.close(code=1001)
        self.driver.release_all()


async def serve(server, host, port, stop, ready, hotkeys=None):
    runner = web.AppRunner(server.app, access_log=None)
    await runner.setup()
    task = None
    try:
        await web.TCPSite(runner, host, port).start()
        ready()
        task = asyncio.create_task(server.watchdog())
        while not stop.is_set():
            if hotkeys:
                events = hotkeys.poll()
                if 'toggle' in events:
                    await server.toggle()
                if 'quit' in events:
                    stop.set()
            await asyncio.sleep(0.03)
    finally:
        if task:
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task
        await runner.cleanup()
