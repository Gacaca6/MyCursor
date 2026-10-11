# Mousely research and MyCursor implementation

Reviewed the official site and support page on 11 October 2026:

- https://mouse.ly/
- https://mouse.ly/support

Mousely uses companion phone and desktop apps, delivering input events rather
than recording the desktop. It advertises trackpad movement, click, right click,
scroll, drag, slide navigation, volume and a digital presentation pointer.
It describes Wi-Fi and Bluetooth working together and nearby-device pairing.

Its public availability statements are inconsistent: the support page says
iPhone, Windows and Mac are available; the homepage footer lists Windows as
coming next. The homepage compatibility line limits iOS 26+ to macOS 26.1+
and Android to Windows 10/11, with Android invitation-only. Consequently these
pages do not establish a working public iPhone-to-Windows pairing route.

## What MyCursor now provides

An iPhone Safari touchpad and a Windows receiver using the existing SendInput
mouse driver. A QR code pairs the phone over the same Wi-Fi or hotspot. The
browser sends relative motion over one persistent WebSocket, with short motion
batches for responsive movement. No camera, cloud account, or raised-hand pose
is required. No desktop images are captured or transmitted.

Implemented: movement, single/double/right/middle clicks, two-finger scrolling
in both directions, a drag toggle for selection and moving windows, speed and
scroll-direction preferences, Unicode text entry, keyboard shortcuts,
presentation navigation/start/end, and media/volume controls.

The desktop window displays a pairing QR and network addresses. The phone
reconnects after network interruptions or returning from sleep. Ownership is
limited to one phone; a disconnect or three-second silence releases held mouse
buttons. Ctrl+Alt+Z pauses/resumes; Ctrl+Alt+Q quits.

## Differences and limits

- Local Wi-Fi/hotspot transport, not native Bluetooth HID or USB-only operation.
- The digital presentation pointer is a click-through red marker following
  the PC cursor. There is no notification-silencing integration.
- Browser must remain open; phone sleep stops control. Normal phone/browser
  auto-lock rules apply.
- The phone controls the active Windows app. Presentation buttons use standard
  F5, Page Up/Down and Escape; individual presentation apps may differ.
- Input cannot control Windows UAC prompts or higher-privilege apps from a
  normal receiver. Microsoft documents this limitation:
  https://learn.microsoft.com/en-us/windows/win32/api/winuser/nf-winuser-sendinput
- This version uses HTTP on the local network, so use a trusted home network or
  personal hotspot. The pairing token stays in a URL fragment, then local
  storage; it is sent in the socket auth message, not a URL query/access log.
  HTTP traffic is not encrypted. Do not forward the receiver port to the internet.
- Pairing survives receiver restarts via phone-settings.json and browser
  storage. Changing the PC IP (for example switching to a hotspot) requires
  scanning the current QR again. Delete phone-settings.json while stopped to
  revoke saved pairing and generate a new token.

## Verification

125 Python tests passed, covering the old camera math plus phone authentication,
single-controller ownership, command validation, Unicode, pause and lost-phone
button release. A Chromium mobile viewport test exercised touch movement,
one/two-finger taps, scrolling, drag/drop, typing, presentation commands and
reconnects with a fake input receiver. A separate Windows smoke check verifies
actual cursor movement, without clicking or typing into the user's apps.

The user confirmed that actual phone-to-PC controls work in Chrome on their
iPhone. Standalone Home Screen installation and Safari still need confirmation
on the physical phone. Automated mobile Chromium checks also validate the
large-pad layout, manifest, paired launch URL, installation help and service
worker registration on localhost. iPhone supports HTTP Home Screen web apps:
https://webkit.org/blog/13878/web-push-for-web-apps-on-ios-and-ipados/
Service workers and wake lock are enabled only on secure origins; they do not
run on a normal HTTP LAN phone connection.

## Installed-app pairing and layout update

The main screen now shows a full-size touch surface, connection state and a
Settings icon. Unpaired/disconnected sessions show Scan PC; keyboard, remote,
pointer speed, pause and installation are inside Settings. Install is hidden
in standalone display mode, on Apple's navigator.standalone signal, and on
the browser appinstalled event. Manual disconnects remain disconnected after
relaunch; network loss returns to Scan and releases held input.

QR decoding uses vendored ZXing WASM 3.1.5 (MIT wrapper, Apache 2.0 ZXing-C++)
with QR-only detection, rotation, inversion and denoising. Its matched WASM
binary is served locally, with CSP permission restricted to WASM compilation.
Images stay on the phone. On local
HTTP, a directly tapped native image input opens the phone camera; secure
origins also support live video scanning. Native camera capture must not
invalidate the returning image when iOS temporarily backgrounds the app.
The touchpad ignores taps on its Scan button so preventDefault does not swallow
the button's touchscreen click.

When camera photos cannot be decoded, Scan offers an eight-digit code shown on
the PC. Same-origin requests, ten-minute rotation, and a global five-failure
per-minute limit protect this alternative pairing exchange. It returns the
existing authentication token; the normal WebSocket still confirms connection.

Browser checks use real touchscreen taps to open Scan and the native file
chooser, decode generated QR images, reject unrelated codes, and connect
through the real authenticated WebSocket receiver (using a fake OS input
driver). They test disconnect/relaunch and network-loss behavior, installed-app
signals, and the complete mouse/keyboard/remote flows in Chromium and WebKit.
