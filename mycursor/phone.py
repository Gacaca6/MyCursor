"""Phone mode launcher and a keyboard-accessible Windows pairing window."""
from __future__ import annotations

import argparse
import asyncio
import json
import queue
import secrets
import socket
import threading
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SETTINGS = ROOT / 'phone-settings.json'


def load_token():
    try:
        data = json.loads(SETTINGS.read_text(encoding='utf-8'))
        if isinstance(data.get('token'), str) and len(data['token']) >= 24:
            return data['token']
    except (OSError, ValueError, AttributeError):
        pass
    token = secrets.token_urlsafe(24)
    SETTINGS.write_text(json.dumps({'token': token}, indent=2), encoding='utf-8')
    return token


def addresses():
    values = []
    # UDP connect selects the default route without sending a packet.
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        try:
            sock.connect(('192.0.2.1', 9))
            values.append(sock.getsockname()[0])
        except OSError:
            pass
    try:
        values.extend(socket.gethostbyname_ex(socket.gethostname())[2])
    except OSError:
        pass
    return list(dict.fromkeys(x for x in values if not x.startswith(('127.', '169.254.')))) or ['127.0.0.1']


def main(argv=None):
    parser = argparse.ArgumentParser(description='Use your phone as a Windows touchpad.')
    parser.add_argument('--port', type=int, default=8765)
    parser.add_argument('--host', default='0.0.0.0')
    parser.add_argument('--no-window', action='store_true')
    args = parser.parse_args(argv)
    if not 1 <= args.port <= 65535:
        parser.error('Port must be between 1 and 65535')
    if not args.no_window:
        # Repeated desktop-shortcut launches bring the receiver forward.
        import urllib.request
        try:
            with urllib.request.urlopen(f'http://127.0.0.1:{args.port}/health', timeout=1) as response:
                existing = json.load(response)
            if existing.get('app') == 'MyCursor Phone':
                import ctypes
                from ctypes import wintypes
                user32 = ctypes.windll.user32
                user32.FindWindowW.argtypes = [wintypes.LPCWSTR, wintypes.LPCWSTR]
                user32.FindWindowW.restype = wintypes.HWND
                existing_hwnd = user32.FindWindowW(None, 'MyCursor · Connect your iPhone')
                if existing_hwnd:
                    user32.ShowWindow(existing_hwnd, 9)
                    user32.SetForegroundWindow(existing_hwnd)
                print('MyCursor Phone is already running.')
                return 0
        except (OSError, ValueError):
            pass
    try:
        from .phone_input import PhoneDriver
        from .phone_server import PhoneServer, serve
        from .hotkeys import Hotkeys
        import qrcode
    except ImportError as exc:
        print(f'Missing phone dependency: {exc}\nInstall: .\\.venv\\Scripts\\python.exe -m pip install -r requirements-phone.txt')
        return 2

    token = load_token()
    ips = addresses()
    urls = [f'http://{ip}:{args.port}/#{token}' for ip in ips]
    events = queue.Queue()
    stop = threading.Event()
    server = PhoneServer(PhoneDriver(), token, events.put, laser_supported=not args.no_window)
    keys = Hotkeys()
    keys.bind('toggle', 'ctrl+alt+z')
    keys.bind('quit', 'ctrl+alt+q')
    loop = asyncio.new_event_loop()
    result = [0]

    def ready():
        events.put('Waiting for phone')
        print('MyCursor Phone is ready. Scan the QR code in the pairing window.')

    def run():
        asyncio.set_event_loop(loop)
        try:
            loop.run_until_complete(serve(server, args.host, args.port, stop, ready, keys))
        except OSError as exc:
            result[0] = 3
            events.put(f'Cannot start: {exc}. Another MyCursor Phone may already be running.')
            print(f'Cannot start phone receiver: {exc}')
        finally:
            stop.set()
            loop.close()

    if args.no_window:
        print(f'Phone pairing link: {urls[0]}')
        try:
            run()
        except KeyboardInterrupt:
            stop.set()
        return result[0]

    import tkinter as tk
    from tkinter import ttk
    from PIL import ImageTk
    window = tk.Tk()
    window.title('MyCursor · Connect your iPhone')
    window.geometry('500x690')
    window.minsize(440, 590)
    window.configure(bg='#111827')
    # A click-through overlay follows the cursor without taking keyboard focus.
    import ctypes
    from ctypes import wintypes
    laser = tk.Toplevel(window)
    laser.overrideredirect(True)
    laser.attributes('-topmost', True)
    laser.attributes('-transparentcolor', '#ff00ff')
    laser.configure(bg='#ff00ff')
    canvas = tk.Canvas(laser, width=36, height=36, bg='#ff00ff', highlightthickness=0)
    canvas.pack()
    canvas.create_oval(5, 5, 31, 31, fill='#ff4b5b', outline='white', width=2)
    canvas.create_oval(13, 13, 23, 23, fill='white', outline='white')
    laser.geometry('36x36+0+0')
    laser.update_idletasks()
    user32 = ctypes.windll.user32
    user32.GetParent.argtypes = [wintypes.HWND]
    user32.GetParent.restype = wintypes.HWND
    hwnd = user32.GetParent(laser.winfo_id())
    get_style = user32.GetWindowLongPtrW if ctypes.sizeof(ctypes.c_void_p) == 8 else user32.GetWindowLongW
    set_style = user32.SetWindowLongPtrW if ctypes.sizeof(ctypes.c_void_p) == 8 else user32.SetWindowLongW
    get_style.argtypes = [wintypes.HWND, ctypes.c_int]
    get_style.restype = ctypes.c_ssize_t
    set_style.argtypes = [wintypes.HWND, ctypes.c_int, ctypes.c_ssize_t]
    set_style.restype = ctypes.c_ssize_t
    set_style(hwnd, -20, get_style(hwnd, -20) | 0x20 | 0x80 | 0x08000000)
    laser.withdraw()

    def update_laser():
        if server.laser and not server.paused and server.socket is not None:
            x, y = server.driver.get_pos()
            from .input_win import move_window
            move_window(hwnd, x - 18, y - 18)
            user32.ShowWindow(hwnd, 4)  # SW_SHOWNOACTIVATE
            window.after(25, update_laser)
        else:
            user32.ShowWindow(hwnd, 0)
            window.after(150, update_laser)

    window.after(150, update_laser)
    style = ttk.Style(window)
    style.theme_use('clam')
    style.configure('TButton', padding=9)
    style.configure('TCombobox', padding=5)
    tk.Label(window, text='Your phone is your touchpad.', font=('Segoe UI', 20, 'bold'), bg='#111827', fg='#ecf3ff').pack(pady=(18, 6))
    tk.Label(window, text='1. Connect iPhone and PC to the same Wi-Fi\n   or connect the PC to your iPhone hotspot.\n2. Scan this code with your iPhone Camera.\n3. Open the link in Safari and slide to move.', justify='left', font=('Segoe UI', 11), bg='#111827', fg='#b8c8df').pack(pady=8)
    qr_label = tk.Label(window, bg='#111827')
    qr_label.pack(pady=8)
    ip_choice = tk.StringVar(value=ips[0])
    combo = ttk.Combobox(window, values=ips, textvariable=ip_choice, state='readonly', width=28)
    if len(ips) > 1:
        tk.Label(window, text='PC network address (try another if needed)', bg='#111827', fg='#b8c8df').pack()
        combo.pack(pady=5)
    url_var = tk.StringVar()
    entry = ttk.Entry(window, textvariable=url_var, state='readonly', width=65)
    entry.pack(padx=18, fill='x', pady=7)

    def update_qr(*_):
        url = f'http://{ip_choice.get()}:{args.port}/#{token}'
        url_var.set(url)
        image = qrcode.make(url).convert('RGB').resize((252, 252))
        qr_label.image = ImageTk.PhotoImage(image)
        qr_label.configure(image=qr_label.image)
        # Local artifact makes the pairing code available in this chat too.
        qrcode.make(url).save(ROOT / 'phone-pairing.png')

    update_qr()
    combo.bind('<<ComboboxSelected>>', update_qr)
    status = tk.StringVar(value='Starting…')
    tk.Label(window, textvariable=status, wraplength=460, font=('Segoe UI', 11, 'bold'), bg='#111827', fg='#7be4c4').pack(pady=8)
    row = ttk.Frame(window)
    row.pack(pady=4)

    def copy():
        window.clipboard_clear()
        window.clipboard_append(url_var.get())

    def pause():
        if loop.is_running():
            asyncio.run_coroutine_threadsafe(server.toggle(), loop)

    def close():
        stop.set()
        window.destroy()

    ttk.Button(row, text='Copy link', command=copy).pack(side='left', padx=4)
    ttk.Button(row, text='Pause / resume', command=pause).pack(side='left', padx=4)
    ttk.Button(row, text='Quit', command=close).pack(side='left', padx=4)
    tk.Label(window, text='Ctrl+Alt+Z: pause / resume   ·   Ctrl+Alt+Q: quit\nYou can minimize this window while using the touchpad.\nIf Safari cannot connect, allow Python on your private network\nin Windows Firewall. Guest Wi-Fi may block device connections.', font=('Segoe UI', 9), bg='#111827', fg='#9aacbf').pack(pady=12)
    window.protocol('WM_DELETE_WINDOW', close)
    thread = threading.Thread(target=run, name='phone-receiver', daemon=True)
    thread.start()

    def tick():
        while not events.empty():
            status.set(events.get_nowait())
        if stop.is_set() and result[0] == 0:
            window.destroy()
            return
        window.after(150, tick)

    window.after(150, tick)
    window.mainloop()
    stop.set()
    thread.join(timeout=5)
    return result[0]


if __name__ == '__main__':
    raise SystemExit(main())
