"""Command-line entry point.

    python -m mycursor                  # head mode, pointer starts OFF
    python -m mycursor --mode hand      # hand mode
    python -m mycursor --list-cameras   # find the right camera index

The pointer deliberately starts switched off. Press the toggle hotkey when you
are ready. A camera pointer that seizes the cursor the instant it launches is
very hard to get out of if it is mistuned.
"""

from __future__ import annotations

import argparse
import sys
import textwrap

from .config import CONFIG_PATH, Config

LOG_PATH = CONFIG_PATH.with_name("mycursor.log")


def attach_streams() -> "pathlib.Path | None":
    """Give the process somewhere to print when launched without a console.

    pythonw.exe -- which is how this runs with no terminal window -- starts a
    process with no stdout and no stderr at all. In Python 3 that means
    sys.stdout is literally None, so the first print() anywhere raises
    AttributeError and the app dies before it ever opens the camera.

    Pointing both streams at a log file fixes that and gives a windowless app
    somewhere to leave a trail, which is the only way to debug one.
    """
    import pathlib as _pathlib

    if sys.stdout is not None and sys.stderr is not None:
        return None
    try:
        handle = open(LOG_PATH, "a", encoding="utf-8", buffering=1)
    except OSError:
        # Last resort: swallow output rather than crash on the first print.
        import io

        handle = io.StringIO()
    if sys.stdout is None:
        sys.stdout = handle
    if sys.stderr is None:
        sys.stderr = handle
    return _pathlib.Path(LOG_PATH)


def list_cameras(limit: int = 6) -> None:
    import cv2

    print("Probing camera indices...")
    found = 0
    for index in range(limit):
        capture = cv2.VideoCapture(index, cv2.CAP_MSMF)
        if capture.isOpened():
            ok, frame = capture.read()
            if ok:
                h, w = frame.shape[:2]
                print(f"  index {index}: working, {w}x{h}")
                found += 1
            else:
                print(f"  index {index}: opens but gives no frames (in use?)")
            capture.release()
    if not found:
        print(
            "  No working camera found. Close any app using the webcam and\n"
            "  check Settings > Privacy & security > Camera."
        )


def _resolved_control(cfg: Config) -> str:
    """What control scheme will actually be used, spelled out.

    "auto" in the banner tells the user nothing; the resolved value is what
    explains how the pointer is about to behave.
    """
    if cfg.pointer.control_mode != "auto":
        return cfg.pointer.control_mode
    return "absolute (auto)" if cfg.mode == "hand" else "relative (auto)"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m mycursor",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        description="Use your phone as a Windows touchpad; optional head/hand webcam modes.",
    )
    parser.add_argument(
        "--mode", choices=("phone", "head", "hand"), help="input mode (default: phone touchpad)"
    )
    parser.add_argument(
        "--control",
        choices=("auto", "relative", "absolute", "velocity"),
        help="how tracked movement becomes cursor movement (default: auto)",
    )
    parser.add_argument("--camera", type=int, help="camera index (see --list-cameras)")
    parser.add_argument(
        "--click",
        choices=("dwell", "gesture", "none"),
        help="head mode click method",
    )
    parser.add_argument(
        "--enabled",
        action="store_true",
        help="start with the pointer already active (careful)",
    )
    parser.add_argument(
        "--no-preview", action="store_true", help="run without the preview window"
    )
    parser.add_argument(
        "--no-pointer",
        action="store_true",
        help="practice mode: track and show everything, never move the mouse",
    )
    parser.add_argument(
        "--list-cameras", action="store_true", help="list working camera indices and exit"
    )
    parser.add_argument(
        "--save", action="store_true", help="write these options back to settings.json"
    )
    parser.add_argument('--port', type=int, default=8765, help='phone receiver port')
    parser.add_argument('--no-window', action='store_true', help='phone mode without pairing window')
    return parser


def main(argv: list[str] | None = None) -> int:
    log = attach_streams()
    if log is not None:
        import datetime

        print(f"\n=== MyCursor started {datetime.datetime.now():%Y-%m-%d %H:%M:%S} ===")

    args = build_parser().parse_args(argv)

    if args.list_cameras:
        list_cameras()
        return 0

    if args.mode in (None, 'phone'):
        from .phone import main as phone_main
        options = ['--port', str(args.port)]
        if args.no_window:
            options.append('--no-window')
        return phone_main(options)

    cfg = Config.load()
    if args.mode:
        cfg.mode = args.mode
    if args.control:
        cfg.pointer.control_mode = args.control
    if args.camera is not None:
        cfg.camera.index = args.camera
    if args.click:
        cfg.head.click_mode = args.click
    if args.enabled:
        cfg.start_enabled = True
    if args.no_preview:
        cfg.show_preview = False
    if args.no_pointer:
        cfg.move_pointer = False
    if args.save:
        cfg.save()
        print(f"saved settings to {CONFIG_PATH}")

    if not cfg.move_pointer:
        print("PRACTICE MODE - tracking only, the mouse will not be touched.\n")

    keys = cfg.hotkeys
    print(
        textwrap.dedent(
            f"""
            MyCursor  -  mode: {cfg.mode}   control: {_resolved_control(cfg)}

              {keys.toggle_enable:<16} turn the pointer on/off  (start here)
              {keys.switch_mode:<16} switch head <-> hand
              {keys.recenter:<16} recentre head mode on your current pose
              {keys.left_click:<16} left click from the keyboard
              {keys.quit:<16} quit
              q                in the preview window, also quits

            Settings: {CONFIG_PATH}
            """
        ).strip()
    )

    if cfg.mode == "hand":
        print(
            textwrap.dedent(
                """
                Hand gestures:
                  move          curl your fingers, thumb apart - the palm steers
                  left click    pinch thumb + index
                  drag          hold that pinch, then move
                  right click   pinch thumb + middle finger
                  scroll        index + middle UP, ring finger DOWN, move up/down
                  park          open palm, all fingers spread - rest your arm

                Watch the preview: it shows each finger as I/M/R/P up or dn,
                so you can see the pose the tracker actually thinks you made.
                Keep your hand inside the green "active area" box - that box
                maps to the whole screen.
                """
            ).strip()
        )
    elif cfg.head.click_mode == "dwell":
        print(
            f"\nHead: turn to steer. Hold still {cfg.head.dwell_time_ms} ms to click,"
            "\nthen move away before the next click can fire."
        )
    elif cfg.head.click_mode == "gesture":
        print("\nHead: turn to steer. Open your jaw = left click, raise brows = right.")

    print()

    # Import here so a dependency problem is reported as advice, not a stack trace.
    try:
        from .engine import CameraError, Engine
    except ImportError as exc:
        print(f"A dependency is missing: {exc}", file=sys.stderr)
        print(
            "\nInstall them into this project's venv:\n"
            "  .\\.venv\\Scripts\\python.exe -m pip install -r requirements.txt",
            file=sys.stderr,
        )
        return 2

    from .models import ModelUnavailable

    engine = Engine(cfg, on_state=lambda msg: print(f"  [{msg}]"))
    for problem in engine.keys.errors:
        print(f"  [hotkey ignored] {problem}", file=sys.stderr)

    try:
        engine.run()
    except KeyboardInterrupt:
        print("\nstopped")
    except CameraError as exc:
        print(f"\nCamera problem:\n  {exc}", file=sys.stderr)
        return 3
    except ModelUnavailable as exc:
        print(f"\nModel problem:\n  {exc}", file=sys.stderr)
        return 4
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
