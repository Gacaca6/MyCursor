"""Browser test receiver with a fake input driver; never controls the PC."""
import sys
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
web.run_app(server.app, host='127.0.0.1', port=8766, access_log=None)
