# MyCursor

## Phone touchpad (new default)

Free, open-source phone touchpad for **Windows 10/11**. Works in **iPhone
Chrome/Safari** and modern Android browsers. The Windows receiver runs on your
own PC; opening a GitHub page alone cannot control the computer.

For a fresh PC: install **Python 3.12** from python.org (enable the Python
launcher), download this repository with **Code → Download ZIP**, extract it,
and double-click **Start Phone Touchpad.cmd**. It installs the phone-only
dependencies and creates the **MyCursor Phone Touchpad** desktop shortcut.
Keep the extracted folder in place, because the shortcut points into it.

MyCursor now uses your **iPhone as a touchpad for this Windows PC**, with no
webcam or hand tracking. Double-click **MyCursor Phone Touchpad** on your desktop,
or `Start Phone Touchpad.cmd` in this folder. A pairing window opens on the PC.

1. Put the PC and iPhone on the same Wi-Fi, or connect the PC to your iPhone's
   Personal Hotspot.
2. On first use, scan the PC's QR code with the iPhone Camera and open the link
   in Chrome or Safari. Install the Home Screen app through Settings → Install app.
   Inside the installed app, tap **Scan PC** to pair again.
3. Slide one finger to move, tap to click, use two fingers to scroll or tap for
   right click. Tap the **hand icon** to hold a selection/window, then tap it
   again to release.

The phone has separate click buttons, double click, middle click, speed controls,
a keyboard/text panel, app shortcuts, slide navigation and volume/media controls.
The touchpad fills the screen. The **gear icon** opens Settings, including
pointer speed, pause, keyboard, remote controls, installation and pairing help.
The main screen shows **Connected** after the receiver accepts the scanned code.
**Settings → Disconnect** releases held input and returns to **Scan PC**. A lost
network connection also returns to Scan; deliberate disconnects stay disconnected
even when you reopen the app.

On local HTTP iPhone connections, Scan PC opens the native camera so you can
photograph the QR code shown on the PC. The app decodes that photo locally; it
is never uploaded. Live camera scanning is enabled on HTTPS/localhost, where
browser camera streams are available. Invalid/non-MyCursor QR codes are rejected.
Because movement is relative, lift and repeat strokes to reach every screen
corner; your finger is never limited to mapping one small phone area to the PC.
The presentation pointer highlights the PC cursor using a click-through overlay.
Keep Safari open. After returning from sleep it reconnects automatically.
**Ctrl+Alt+Z** pauses/resumes; **Ctrl+Alt+Q** quits. Closing the PC pairing window
quits the receiver; minimizing it keeps it running.

```powershell
.\run-phone.ps1
# Or, if already installed:
.\.venv\Scripts\python.exe -m mycursor --mode phone
```

Phone mode only needs `requirements-phone.txt`; it does not load MediaPipe,
OpenCV, or the camera. Dependencies install automatically through the launcher.
The QR pairing remains valid across restarts on the same address. If you change
Wi-Fi/hotspot, restart the PC receiver and scan the updated QR. You can bookmark
the page. Open **Settings → Install app**, then use Chrome/Safari's
**Share > Add to Home Screen**. Install is hidden in the installed Home Screen
app and immediately after a browser's installation-complete event.
Keep **Open as Web App** enabled if shown. The app icon, standalone manifest and
paired launch address let the iPhone open it as its own Home Screen app. This
works over local HTTP on iPhone. Offline shell caching/service workers and a
screen wake lock only run on secure origins such as HTTPS or PC localhost;
the local HTTP phone connection needs the PC receiver and obeys auto-lock.

If Safari cannot load the page, double-click **Allow Phone Connection.cmd** and
accept Windows' administrator prompt. It adds a firewall rule restricted to
MyCursor's Python executables, TCP port 8765 and the local subnet. Guest Wi-Fi
can prevent phone-to-PC connections; use your personal hotspot in that case.
When there are multiple network addresses, choose the Wi-Fi/hotspot address in
the PC window rather than a virtual adapter address.

This is a local HTTP connection; use trusted Wi-Fi or your hotspot. Do not share
the QR/pairing link. To revoke pairing, quit, delete `phone-settings.json`, and
start again. Windows UAC prompts and administrator apps cannot be controlled
by the normal receiver. There is no Bluetooth or USB-only mode in this version.
See [Mousely research](RESEARCH-MOUSELY.md).

For automatic startup:

```powershell
powershell -ExecutionPolicy Bypass -File tools\install_startup.ps1 -Mode phone
# To remove:
powershell -ExecutionPolicy Bypass -File tools\install_startup.ps1 -Remove
```

Checks: `python -m unittest discover -s tests` (full legacy dependencies) or
`python -m unittest discover -s tests -p test_phone.py` (phone-only install).
For browser checks run `npm install`, `npx playwright install chromium webkit`,
start `python tools/phone_test_server.py` in another terminal, then `npm run
test:browser`. Set `MYCURSOR_TEST_BROWSER=webkit` to test WebKit. These use fake input for phone
protocol/browser tests. `tools/phone_input_smoke.py` verifies actual cursor motion
and restores the position, skipping if a phone is already connected.

## Optional webcam controls

The earlier head/hand controls remain available with `--mode head` or
`--mode hand`. See [legacy webcam instructions](LEGACY-WEBCAM.md). Phone mode
needs no webcam and installs separately.

## License

MIT — free to use, modify and share.
