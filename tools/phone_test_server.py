"""Browser test receiver with a fake input driver; never controls the PC."""
import sys
import io
import qrcode
from PIL import Image, ImageFilter, ImageEnhance
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from aiohttp import web
from mycursor.phone_server import PhoneServer
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / 'tests'))
from test_phone import FakeDriver

driver = FakeDriver()
TOKEN = 'browser-test-token-0123456789012345678901234'
server = PhoneServer(driver, TOKEN, laser_supported=True)

async def events(request):
    return web.json_response({'events': driver.events, 'held': sorted(driver.held)})

server.app.router.add_get('/test-events', events)

async def qr(request):
    value = f'https://example.com/#{TOKEN}' if request.query.get('invalid') else f'{request.scheme}://{request.host}/#{TOKEN}'
    image = qrcode.make(value)
    if request.query.get('photo'):
        # A small code in a camera-sized JPEG, with screen blur, rotation and
        # reduced contrast. A pristine QR PNG misses this real-world failure.
        code = image.convert('RGB').resize((145, 145), Image.Resampling.LANCZOS)
        code = ImageEnhance.Contrast(code).enhance(.65)
        code = code.rotate(11, resample=Image.Resampling.BICUBIC, expand=True, fillcolor='white')
        image = Image.new('RGB', (4032, 3024), '#747b82')
        position = (2870, 1980) if request.query['photo'] == 'corner' else (1900, 1400)
        image.paste(code, position)
        image = image.filter(ImageFilter.GaussianBlur(.35))
        buffer = io.BytesIO()
        image.save(buffer, format='JPEG', quality=80)
        return web.Response(body=buffer.getvalue(), content_type='image/jpeg')
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
