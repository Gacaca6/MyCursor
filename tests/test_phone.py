"""Phone protocol, ownership and disconnect tests; no real mouse input."""
import asyncio
import unittest
from aiohttp import web, ClientSession, WSMsgType
from mycursor.phone_server import PhoneServer


class FakeDriver:
    def __init__(self):
        self.events = []
        self.held = set()

    def move(self, x, y): self.events.append(('move', x, y))
    def scroll(self, n): self.events.append(('scroll', n))
    def hscroll(self, n): self.events.append(('hscroll', n))
    def click(self, b): self.events.append(('click', b))
    def double_click(self, b): self.events.append(('double', b))
    def press(self, b): self.held.add(b)
    def release(self, b): self.held.discard(b)
    def release_all(self): self.held.clear()
    def key(self, k): self.events.append(('key', k))
    def text(self, t): self.events.append(('text', t))


class ProtocolTests(unittest.TestCase):
    def setUp(self):
        self.driver = FakeDriver()
        self.server = PhoneServer(self.driver, 'test-token')

    def test_movements_clicks_keys_and_unicode(self):
        for command in [{'type': 'move', 'dx': .25, 'dy': -4},
                        {'type': 'scroll', 'dy': .1, 'dx': -.2},
                        {'type': 'click', 'button': 'right'},
                        {'type': 'click', 'double': True},
                        {'type': 'key', 'key': 'copy'},
                        {'type': 'text', 'text': 'Hello café 😀'}]:
            self.server.dispatch(command)
        self.assertEqual(self.driver.events, [('move', .25, -4), ('scroll', .1),
            ('hscroll', -.2), ('click', 'right'), ('double', 'left'),
            ('key', 'copy'), ('text', 'Hello café 😀')])

    def test_invalid_input_cannot_reach_driver(self):
        for command in [None, [], {'type': 'move', 'dx': True},
                        {'type': 'move', 'dx': float('nan')},
                        {'type': 'move', 'dy': float('inf')},
                        {'type': 'move', 'dx': 2001},
                        {'type': 'scroll', 'dy': 31},
                        {'type': 'click', 'button': 'bogus'},
                        {'type': 'key', 'key': 'run-shell'},
                        {'type': 'text', 'text': 'x' * 2001},
                        {'type': 'text', 'text': '\ud800'}, {'type': 'bogus'}]:
            with self.subTest(command=command), self.assertRaises((ValueError, TypeError)):
                self.server.dispatch(command)
        self.assertEqual(self.driver.events, [])

    def test_pause_blocks_actions_and_release_still_works(self):
        self.driver.press('left')
        self.server.paused = True
        self.server.dispatch({'type': 'move', 'dx': 100})
        self.server.dispatch({'type': 'release'})
        self.assertEqual(self.driver.held, set())
        self.assertEqual(self.driver.events, [])

    def test_presentation_pointer_validation(self):
        with self.assertRaises(ValueError):
            self.server.dispatch({'type': 'laser', 'enabled': True})
        self.server.laser_supported = True
        with self.assertRaises(ValueError):
            self.server.dispatch({'type': 'laser', 'enabled': 'yes'})
        self.server.dispatch({'type': 'laser', 'enabled': True})
        self.assertTrue(self.server.laser)
        self.server.dispatch({'type': 'laser', 'enabled': False})
        self.assertFalse(self.server.laser)


class NetworkTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.driver = FakeDriver()
        self.server = PhoneServer(self.driver, 'test-token')
        self.runner = web.AppRunner(self.server.app)
        await self.runner.setup()
        site = web.TCPSite(self.runner, '127.0.0.1', 0)
        await site.start()
        self.url = f'http://127.0.0.1:{site._server.sockets[0].getsockname()[1]}'
        self.client = ClientSession()

    async def asyncTearDown(self):
        await self.client.close()
        await self.runner.cleanup()

    async def pair(self, token='test-token'):
        ws = await self.client.ws_connect(self.url + '/ws', origin=self.url)
        await ws.send_json({'type': 'auth', 'token': token})
        return ws, await ws.receive_json()

    async def sync(self, ws):
        await ws.send_json({'type': 'ping'})
        return await ws.receive_json()

    async def test_page_and_origin(self):
        async with self.client.get(self.url) as response:
            self.assertEqual(response.status, 200)
            self.assertIn('MyCursor', await response.text())
            self.assertEqual(response.headers['X-Frame-Options'], 'DENY')
        async with self.client.get(self.url + '/ws', headers={'Origin': 'http://evil.example'}) as response:
            self.assertEqual(response.status, 403)

    async def test_manifest_preserves_pairing_only_after_auth(self):
        async with self.client.get(self.url + '/manifest.webmanifest') as response:
            data = await response.json()
            self.assertEqual(data['display'], 'standalone')
            self.assertEqual(data['start_url'], '/')
        async with self.client.post(self.url + '/pair', json={'token':'bad'}, headers={'Origin':self.url}) as response:
            self.assertEqual(response.status, 403)
        async with self.client.post(self.url + '/pair', json={'token':'test-token'}, headers={'Origin':self.url}) as response:
            self.assertEqual(response.status, 200)
            self.assertTrue(response.cookies['mycursor_pair']['httponly'])
        async with self.client.get(self.url + '/manifest.webmanifest', cookies={'mycursor_pair':'test-token'}) as response:
            data = await response.json()
            self.assertEqual(data['start_url'], '/#test-token')
        for path in ('/icon-180.png','/icon-192.png','/icon-512.png','/sw.js'):
            async with self.client.get(self.url + path) as response:
                self.assertEqual(response.status, 200)

    async def test_auth_and_single_phone(self):
        denied, data = await self.pair('bad-token')
        self.assertTrue(data['fatal'])
        await denied.close()
        first, data = await self.pair()
        self.assertEqual(data['type'], 'state')
        second, data = await self.pair()
        self.assertIn('Another phone', data['message'])
        await second.close()
        await first.send_json({'type': 'move', 'dx': 10, 'dy': 20})
        await self.sync(first)
        self.assertIn(('move', 10, 20), self.driver.events)
        await first.close()

    async def test_disconnect_releases_drag_and_allows_reconnect(self):
        ws, _ = await self.pair()
        await ws.send_json({'type': 'down', 'button': 'left'})
        await self.sync(ws)
        self.assertEqual(self.driver.held, {'left'})
        await ws.close()
        await asyncio.sleep(.05)
        self.assertEqual(self.driver.held, set())
        ws, data = await self.pair()
        self.assertEqual(data['type'], 'state')
        await ws.close()

    async def test_bad_command_does_not_break_session(self):
        ws, _ = await self.pair()
        await ws.send_json({'type': 'down'})
        await self.sync(ws)
        await ws.send_str('{bad json')
        self.assertEqual((await ws.receive_json())['type'], 'error')
        self.assertEqual(self.driver.held, set())
        self.assertEqual((await self.sync(ws))['type'], 'pong')
        await ws.close()

    async def test_pause_releases_drag_and_blocks_input(self):
        ws, _ = await self.pair()
        await ws.send_json({'type': 'down'})
        await ws.send_json({'type': 'pause'})
        self.assertTrue((await ws.receive_json())['paused'])
        self.assertEqual(self.driver.held, set())
        await ws.send_json({'type': 'click'})
        await self.sync(ws)
        self.assertEqual(self.driver.events, [])
        await ws.close()

    async def test_silent_phone_is_disconnected_and_drag_released(self):
        ws, _ = await self.pair()
        await ws.send_json({'type': 'down'})
        await self.sync(ws)
        self.server.last_seen -= 4
        watchdog = asyncio.create_task(self.server.watchdog())
        try:
            message = await asyncio.wait_for(ws.receive(), 1)
            self.assertIn(message.type, (WSMsgType.CLOSE, WSMsgType.CLOSED))
            self.assertEqual(self.driver.held, set())
        finally:
            watchdog.cancel()
            try:
                await watchdog
            except asyncio.CancelledError:
                pass


if __name__ == '__main__':
    unittest.main()
