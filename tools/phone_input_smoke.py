"""Verify actual Windows cursor movement over the authenticated socket.

Moves the cursor briefly, then restores it. Does not click or type into apps.
"""
import asyncio
import json
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from aiohttp import ClientSession
from mycursor.input_win import MouseDriver


async def main():
    mouse = MouseDriver()
    original = mouse.get_pos()
    token = json.loads(Path('phone-settings.json').read_text())['token']
    url = 'http://127.0.0.1:8765'
    async with ClientSession() as client:
        async with client.get(url + '/health') as response:
            state = await response.json()
        if state['connected']:
            print('SKIP: a phone is connected; leave the active controller undisturbed.')
            return
    try:
        # Start away from edges so clamping does not hide motion.
        mouse.move_to(mouse.origin_x + mouse.width / 2, mouse.origin_y + mouse.height / 2)
        await asyncio.sleep(.1)
        start = mouse.get_pos()
        async with ClientSession() as client:
            async with client.ws_connect(url + '/ws', origin=url) as ws:
                await ws.send_json({'type': 'auth', 'token': token})
                reply = await ws.receive_json()
                assert reply['type'] == 'state' and not reply['paused'], reply
                await ws.send_json({'type': 'move', 'dx': 37, 'dy': 23})
                await ws.send_json({'type': 'ping'})
                assert (await ws.receive_json())['type'] == 'pong'
                await asyncio.sleep(.1)
                end = mouse.get_pos()
                assert abs(end[0] - start[0] - 37) <= 2, (start, end)
                assert abs(end[1] - start[1] - 23) <= 2, (start, end)
                print(f'PASS: authenticated WebSocket -> Windows SendInput -> actual cursor delta {end[0]-start[0]}, {end[1]-start[1]}.')
    finally:
        mouse.move_to(*original)


asyncio.run(main())
