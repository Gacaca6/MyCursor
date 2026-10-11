# Legacy webcam controls

Control the Windows mouse pointer with your head or your hand, using the
laptop's built-in webcam. Built as a fallback for a dead touchpad.

Two modes, one click layer:

- **head** — turn your head to steer, hold still to click. Low
  fatigue, precise enough for everyday use, hands free to keep typing.
- **hand** — palm steers the cursor, pinch to click, two fingers to scroll.
  More fun, more capable gestures, and genuinely tiring after a while.

## Honest expectations

Read this before you rely on it.

**Head mode is the one that can replace a mouse for everyday work.** Measured
on this laptop it runs at 30 fps with 100% face detection and, after tuning,
about 0.01 px of cursor shake per frame while you hold still. It is fine for
browsing, clicking, scrolling, switching windows, watching video.

**Hand mode is usable, but will not survive a full workday.** Not because of the
code — because of your arm. Holding a hand up in the camera's view is comfortable for ten
minutes and painful for eight hours. This is the single biggest reason projects
like this get abandoned, and no amount of tuning fixes it. Use hand mode for
bursts, and head mode for sessions.

**Neither mode matches a real mouse for precision work.** Dragging a 4 px
window border or doing detailed design work will be frustrating. Everything
else is fine.

**Other things that will bite you:**

- The camera is shared. If Teams, Zoom or the Camera app grabs it, the pointer
  goes blind until you close them.
- Bad lighting costs you tracking. Backlit — a bright window behind you — is
  the worst case.
- In hand mode your raised hand sits between your eyes and the screen.

## Requirements

- Windows
- **Python 3.12** — mediapipe publishes no wheel for 3.13, so 3.13 cannot run
  this. `py -3.12` must work.
- A working webcam

## Install

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

The two MediaPipe model files (~11 MB) download automatically on first run.

## Run

```powershell
.\run.ps1 -Mode head         # head mode
.\run.ps1 -Hand              # hand mode
.\run.ps1 -Hand -NoPointer   # practice: track but never move the mouse
```

or directly:

```powershell
.\.venv\Scripts\python.exe -m mycursor --mode head  # head mode
.\.venv\Scripts\python.exe -m mycursor --mode hand  # hand mode
```

**Two PowerShell gotchas, both of which `run.ps1` avoids for you:**

1. **The `.\` prefix is required.** A bare
   `.venv\Scripts\python.exe` fails with *"The module '.venv' could
   not be loaded"* -- PowerShell reads a dotted name as a module, not a path.
   It has to be `.\.venv\...`.
2. **You must be in the project folder.** `-m mycursor` only resolves when
   the working directory holds the `mycursor` package, so an absolute path to
   the venv interpreter from elsewhere fails with *"No module named mycursor"*.

`run.ps1` sets its own working directory and builds an absolute interpreter
path, so it works from anywhere. Prefer it.

**The pointer starts switched off.** Press `Ctrl+Alt+Z` when you are ready.
This is deliberate: a mistuned camera pointer that seizes the cursor the instant
it launches is very hard to get out of.

## Running it in the background (no terminal)

This is the intended way to use it day to day.

```powershell
powershell -ExecutionPolicy Bypass -File tools\install_startup.ps1 -Mode hand
```

That drops a shortcut in your Startup folder pointing at `pythonw.exe`, the
interpreter with no console. From the next sign-in onward MyCursor is simply
there, and `Ctrl+Alt+Z` wakes it.

To undo it:

```powershell
powershell -ExecutionPolicy Bypass -File tools\install_startup.ps1 -Remove
```

### Idle costs nothing, and leaves your webcam alone

The hotkey does not unhide an always-running tracker -- it starts one. While
idle there is no camera handle, no model in memory and no inference at all.
Measured on this laptop:

| State | CPU | Memory | Webcam |
|---|---|---|---|
| idle | **0% of one core** | **11 MB** | **free for Teams/Zoom** |
| active | ~1 core | ~300 MB | held |

That matters on a machine with 8 GB of RAM and a 15 W CPU. An always-on
tracker would cost you a core, a chunk of memory, battery and heat around the
clock, and would lock the webcam so nothing else could use it.

The trade is that the **first** wake after sign-in takes a few seconds while
the model loads -- the window appears immediately and tells you so. Every
later wake is instant, because the model stays loaded. Set
`release_models_when_idle` to `true` if you would rather reclaim the memory and
pay the load each time.

Because there is no console, it logs to `mycursor.log` beside `settings.json`.

### The monitor window

A small window, by default 360 px wide in the bottom-right corner, kept above
other apps so it cannot get buried behind whatever you are working in.

It is deliberately not a big always-on-top video feed: on a 1366x768 screen
that covers a third of the desktop, and you only ever need three things from
it -- is my hand inside the active box, what pose does it think I am making,
and is the pointer on.

Placement uses the desktop *work area* rather than the raw screen size, and
measures the real window size after creating it, so it sits clear of the
taskbar instead of half underneath it.

Tune it under `preview` in `settings.json`: `width`, `corner`
(`top-left` / `top-right` / `bottom-left` / `bottom-right`), `margin_px`,
`topmost`.

### Reaching a far corner without leaving the box

Three answers, cheapest first.

**1. Shrink the box.** If a screen corner needs an uncomfortable reach, the
active region is simply bigger than your comfortable range. Raise
`pointer.active_margin_x` / `_y` in `settings.json`:

| margin | box | hand travel vs 0.20 |
|---|---|---|
| 0.20 | 60% of frame | 100% (default) |
| 0.25 | 50% | 83% |
| 0.30 | 40% | 67% |
| 0.35 | 30% | 50% |

Less travel costs you some precision, because the same hand movement now
covers more screen. Raise `stabilise_px` a little if it starts to feel twitchy.

**2. Use the clutch.** Open your palm to park, bring your arm back to a
comfortable position, close your hand again — the cursor stays exactly where
you left it and carries on from there. Same as lifting a mouse off the pad and
putting it down again. Two or three strokes will cross any screen without your
hand ever approaching the edge of the box. This is on by default
(`pointer.clutch`); set it to `false` for a rigid mapping where a given hand
position always means the same screen position.

**3. Use the keyboard for window management.** Your keyboard works, and for
things like minimising a window it beats aiming at a 16-pixel button:

| Keys | Action |
|---|---|
| `Win`+`Down` | minimise |
| `Win`+`Up` | maximise |
| `Alt`+`F4` | close |
| `Alt`+`Tab` | switch window |
| `Win`+`Left` / `Right` | snap to half |

A camera pointer is good at "click that thing". It is not good at hitting title
bar buttons, and it does not have to be.

### Learning the gestures

Press `Ctrl+Alt+G` while it is running. The window switches to a cheat sheet
that **highlights whichever gesture is being detected** as you move your hand,
with the finger readout underneath.

Reading a list teaches you the names; watching a row light up teaches you the
gesture, because the usual problem is that the pose you are making is not the
pose the tracker thinks you are making. Press `Ctrl+Alt+G` again to go back to
the camera view.

### Practice mode

```powershell
.\run.ps1 -Hand -NoPointer
```

Everything runs -- camera, tracking, preview, gesture detection -- but no mouse
event is ever emitted. Use it to learn the gestures or tune the active region
without the cursor running away from you.

### Hotkeys

These work regardless of which window has focus.

| Key | Action |
|---|---|
| `Ctrl+Alt+Z` | wake / sleep — **your kill switch** |
| `Ctrl+Alt+M` | switch head ↔ hand |
| `Ctrl+Alt+C` | recentre head mode on your current pose |
| `Ctrl+Alt+J` | left click from the keyboard |
| `Ctrl+Alt+G` | gesture cheat sheet (highlights what it detects) |
| `Ctrl+Alt+Q` | quit |
| `q` | also quits, when the preview window has focus |

**If a hotkey does nothing, another app has claimed it.** A chord owned by
another process never reaches this one. The default wake key was originally
`Ctrl+Alt+Space`, which the Claude desktop app registers globally, so it
silently never fired. To find free combinations on your machine:

```powershell
.\.venv\Scripts\python.exe tools\check_hotkeys.py
```

It tries to claim each candidate for real and reports what is taken, then
prints a `hotkeys` block you can paste into `settings.json`.

### Head mode

Turn your head to steer. Translation is deliberately ignored — shifting in your
chair does not move the cursor, only rotating your head does. That is what makes
it usable for long stretches.

Clicking, set by `head.click_mode`:

- `dwell` (default) — hold the cursor still for 700 ms. Move away before the
  next click can fire.
- `gesture` — open your jaw for left click, raise your eyebrows for right.
- `none` — movement only; click with `Ctrl+Alt+J`.

If the cursor sits off-centre when your head is neutral, press `Ctrl+Alt+C`.

### Hand mode

| Gesture | Action |
|---|---|
| curled hand, thumb apart | move — the palm centre steers |
| pinch thumb + index | left click |
| hold that pinch, then move | drag |
| pinch thumb + middle finger | right click |
| index + middle **up**, ring **down**, move up/down | scroll |
| open palm, fingers spread | park — rest your arm, cursor holds still |

Hand mode maps an **active region** of the camera view onto the whole screen,
drawn as a box in the preview. It turns green when your hand is inside it. Your
hand position *is* the cursor position — there is no dragging-a-mouse feel to
build up, and no minimum speed to overcome.

The preview also prints each finger as `I:up M:up R:dn P:dn`. When a gesture
"does not work", look there first: almost always the pose the tracker sees is
not the pose you think you are making.

## Tuning

This is where the real work is. Feel is decided by a few numbers in
`settings.json`, and the defaults were measured on one laptop, not yours.

```powershell
.\.venv\Scripts\python.exe tools\tune_filter.py              # head
.\.venv\Scripts\python.exe tools\tune_filter.py --mode hand  # hand
.\.venv\Scripts\python.exe tools\tune_filter.py --apply      # write the result
```

It records ~240 frames of your own tracking, builds a lag-free reference by
smoothing the recording forwards and backwards, then simulates the entire
pointer pipeline for every candidate setting and reports cursor shake in real
screen pixels. **Follow the on-screen prompt while it records** — it needs to
see both movement and pauses to tell noise from intent.

Three findings from building this, in case you tune by hand:

- **A hand should use absolute mapping, not relative.** A mouse needs relative
  motion because it has no position of its own; a tracked hand has one. Mapping
  an active region of the frame straight onto the screen is what every working
  hand-mouse does, and it removes the whole class of "I have to shove it to get
  it going" problems. Relative is still right for a head, whose range is far
  too small to cover a screen.
- **Stabilise on position, not speed.** Noise and slow intent overlap in the
  *speed* domain — landmark jitter is small per frame but fast — so no speed
  threshold can separate them. They do not overlap in *position*: jitter stays
  within a few pixels and deliberate movement does not. So absolute mode ignores
  target movement under `stabilise_px` and follows only the excess beyond it,
  which is steady and precise at the same time.
- **A speed deadzone is a trap, and the tuner will walk straight into it.**
  Landmark noise is high-frequency — small per frame but fast — so raising the
  deadzone does kill visible shake, which is exactly what a shake-based score
  rewards. An earlier version of this project followed its own tuner to
  `deadzone = 0.5` and shipped a pointer that could not be nudged at all:
  anything slower than a flick produced zero movement. opentrack's docs warn
  about the same thing. The deadzone is now modest, `accel_gain()` ramps
  continuously out of it instead of stepping, and hand mode avoids the curve
  entirely. **Do not let a shake metric talk you into a large deadzone.**
- **Watch `follow`, not just shake.** The tuner reports total cursor travel as a
  fraction of intended travel. The original defaults here scored 4.0 — the
  cursor flew four times further than the movement it was tracking — while
  still looking acceptable on a shake-only metric.

Useful settings:

| Setting | Effect |
|---|---|
| `pointer.control_mode` | `auto` (default: absolute for hand, relative for head), or force `absolute` / `relative` / `velocity` |
| `pointer.stabilise_px` | **absolute mode steadiness.** Raise if the cursor shivers, lower for finer control. This is the knob that matters in hand mode |
| `pointer.active_margin_x` / `_y` | how much of the frame edge to trim. Raise for less hand movement per screen inch |
| `pointer.deadzone` | relative mode only. Keep it small — see the warning below |
| `pointer.max_gain` | relative mode only; raise to cross the screen with less movement |
| `pointer.filter_min_cutoff` | lower = steadier but laggier |
| `pointer.filter_beta` | raise to be more responsive to fast movement |
| `head.dwell_time_ms` | lower for faster clicks, at the cost of false ones |
| `hand.pinch_on` / `pinch_off` | pinch thresholds. Keep `on` < `off` — the gap is what stops click chatter |
| `hand.extend_margin` | how decisively a finger must be straight to count as up. Raise if scrolling triggers park instead |
| `hand.cursor_anchor` | `palm` (steady under pinching) or `index_tip` (feels like pointing, drifts on click) |

**The tuner only simulates relative mode.** It was written before hand mode
moved to absolute control, so its numbers apply to head mode. For hand mode,
tune `stabilise_px` and the active margins by feel instead.

Delete any key from `settings.json` to get its default back. Delete the whole
file to reset everything.

## Checks

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests   # 93 tests, no camera needed
.\.venv\Scripts\python.exe tools\smoke_test.py             # models, camera, trackers
```

The smoke test turns the webcam on briefly and reports detection statistics
only. No images are written to disk and nothing leaves the machine. It never
touches the mouse, so it is safe to run at any time.

## How it works

```
camera ──▶ tracker ──▶ Sample ──▶ engine ──▶ SendInput
           (per mode)              (shared)
```

- `mycursor/tracker_head.py`, `tracker_hand.py` — look at a frame, report an
  anchor position plus what you appear to be asking for. They never touch the
  mouse.
- `mycursor/sample.py` — the contract between them and the engine.
- `mycursor/engine.py` — camera loop and every pointer decision: filtering,
  acceleration, click freezing, dwell, the safety switch.
- `mycursor/filters.py` — One Euro filter, gesture hysteresis, gain curve.
- `mycursor/input_win.py` — `SendInput` via ctypes.

A few decisions worth knowing about:

**Media Foundation, not DirectShow.** This is the biggest performance factor in
the whole program. On this laptop's camera, Media Foundation returns a frame in
~4 ms and DirectShow takes ~97 ms, pinning everything to 10 fps regardless of
resolution or pixel format. Inference only costs 25–32 ms, so with the wrong
backend the camera — not the model — is what makes the pointer feel laggy.

**The hand anchor is the palm, not the fingertip.** Pointing with your index
finger feels natural and is the worst available choice: the fingertip is exactly
what moves when you pinch, so every click drags the cursor off target. The
midpoint of the wrist and middle knuckle barely moves when the fingers do,
which removes click drift structurally instead of papering over it.

**Absolute coordinates, computed positions.** Cursor movement is delivered to
`SendInput` as absolute virtual-desktop coordinates, not relative deltas.
Relative deltas get reprocessed by Windows pointer acceleration, which would
silently fight the gain curve here. We integrate movement into a float position
ourselves — so sub-pixel movement accumulates instead of rounding to zero — and
place the cursor exactly where we computed it.

**Every gesture threshold has two values.** A single threshold makes a pinch
flicker on and off while your fingers hover near it, firing a burst of clicks.
Two thresholds with a dead band between them make the state sticky.

## Known limitations

- Windows only (`SendInput`, `GetAsyncKeyState`).
- No tray icon yet — it runs in a console window.
- Hand mode is fatiguing. This is inherent, not a bug.
- `velocity` control mode is implemented but not tuned; `relative` is.
- Hand-mode filter settings have not been tuned on real hand data. Run
  `tools\tune_filter.py --mode hand` to do that.
