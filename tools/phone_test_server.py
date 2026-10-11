"""Browser test receiver with a fake input driver; never controls the PC."""
import sys
import io
import qrcode
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from aiohttp import web
from mycursor.phone_server import PhoneServer
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / 'tests'))
from test_phone import FakeDriver

driver = FakeDriver()
server = PhoneServer(driver, 'browser-test-token', laser_supported=True)

async def events(request):
    return web.json_response({'events': driver.events, 'held': sorted(driver.held)})

server.app.router.add_get('/test-events', events)

async def qr(request):
    value = 'https://example.com/#browser-test-token' if request.query.get('invalid') else f'{request.scheme}://{request.host}/#browser-test-token'
    image = qrcode.make(value)
    buffer = io.BytesIO()
    image.save(buffer, format='PNG')
    return web.Response(body=buffer.getvalue(), content_type='image/png')

async def drop(request):
    if server.socket is not None:
        await server.socket.close()
    return web.json_response({'dropped': True})

server.app.router.add_get('/test-qr.png', qr)
server.app.router.add_post('/test-drop', drop)
web.run_app(server.app, host='127.0.0.1', port=8766, access_log=None)
