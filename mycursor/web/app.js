'use strict';
const $ = id => document.getElementById(id);
let token = location.hash.slice(1);
try { if (token) localStorage.setItem('mycursor-token', token); else token = localStorage.getItem('mycursor-token') || ''; } catch (_) {}
if (location.hash) history.replaceState(null, '', location.pathname);
let largePad = true;
try { largePad = localStorage.getItem('mycursor-large-pad') !== 'false'; } catch (_) {}
function setLargePad(value) {
  largePad = value; document.body.classList.toggle('pad-only', value);
  $('size').textContent = value ? 'More controls' : 'Large pad';
  if (value) {
    document.querySelectorAll('.panel').forEach(p => p.hidden = p.id !== 'touch');
    document.querySelectorAll('[data-tab]').forEach(b => b.classList.toggle('selected', b.dataset.tab === 'touch'));
  }
  try { localStorage.setItem('mycursor-large-pad', String(value)); } catch (_) {}
}
setLargePad(largePad);
let ws, retry, paired = false, paused = false, fatal = false, dragging = false, generation = 0;
let pending = null, frame = null, lastPong = 0;
let laser = false;
function status(message, online = false) { $('status').textContent = message; $('dot').classList.toggle('online', online); }
function send(message) {
  if (!paired || ws?.readyState !== WebSocket.OPEN) return false;
  if (ws.bufferedAmount > 32768) { ws.close(); return false; }
  ws.send(JSON.stringify(message)); return true;
}
function flush() { if (frame !== null) cancelAnimationFrame(frame); frame = null; if (pending) send(pending); pending = null; }
function discard() { if (frame !== null) cancelAnimationFrame(frame); frame = null; pending = null; }
function motion(type, dx, dy) {
  if (!paired || paused) return;
  if (pending && pending.type !== type) flush();
  if (!pending) pending = {type, dx: 0, dy: 0};
  pending.dx += dx; pending.dy += dy;
  if (frame === null) frame = requestAnimationFrame(flush);
}
function setDrag(value) {
  dragging = value; $('drag').setAttribute('aria-pressed', String(value)); $('drag').textContent = value ? 'Drop / release' : 'Drag: off'; $('pad').classList.toggle('dragging', value);
}
function release() { discard(); send({type: 'release'}); setDrag(false); resetGesture(); }
function connect() {
  clearTimeout(retry); const current = ++generation;
  if (ws) { ws.onclose = null; ws.close(); }
  paired = false; fatal = false; discard(); setDrag(false); resetGesture();
  if (!token) { status('Scan the QR code on your PC to pair.'); return; }
  status('Connecting…');
  ws = new WebSocket(`${location.protocol === 'https:' ? 'wss' : 'ws'}://${location.host}/ws`);
  ws.onopen = () => ws.send(JSON.stringify({type: 'auth', token}));
  ws.onmessage = event => {
    if (current !== generation) return;
    const data = JSON.parse(event.data);
    if (data.type === 'state') {
      paired = true; paused = data.paused; lastPong = Date.now();
      laser = !!data.laser;
      $('laser').disabled = !data.laserSupported;
      $('laser').setAttribute('aria-pressed', String(laser));
      $('laser').textContent = laser ? 'Presentation pointer: on' : 'Presentation pointer: off';
      $('pause').textContent = paused ? 'Resume' : 'Pause';
      if (paused) release();
      status(paused ? 'Paused — tap Resume to control' : 'Connected · Ready to use', !paused);
    } else if (data.type === 'pong') lastPong = Date.now();
    else if (data.type === 'error') { fatal = !!data.fatal; status(data.message); setDrag(false); }
  };
  ws.onclose = () => {
    if (current !== generation) return;
    paired = false; discard(); setDrag(false); resetGesture();
    if (!fatal) { status('Disconnected · Reconnecting…'); if (!document.hidden) retry = setTimeout(connect, 1200); }
  };
  ws.onerror = () => status('Cannot reach PC. Check Wi-Fi and the PC app.');
}
setInterval(() => {
  if (paired) {
    if (Date.now() - lastPong > 4000) { ws.close(); return; }
    send({type: 'ping'});
  }
}, 1000);
$('reconnect').onclick = connect;
$('pause').onclick = () => { release(); send({type: 'pause'}); };
$('laser').onclick = () => { if (!paused) send({type: 'laser', enabled: !laser}); };
$('size').onclick = () => { release(); setLargePad(!largePad); };
let installPrompt = null;
window.addEventListener('beforeinstallprompt', event => { event.preventDefault(); installPrompt = event; });
$('install').onclick = async () => {
  release();
  if (installPrompt) { await installPrompt.prompt(); installPrompt = null; }
  else {
    // Preserve pairing even when iOS installs from the visible page URL.
    if (token) history.replaceState(null, '', '/#' + token);
    $('installHelp').showModal();
  }
};
$('closeInstall').onclick = () => $('installHelp').close();
if (token) fetch('/pair', {method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({token})})
  .then(response => { if (response.ok) $('manifest').href = '/manifest.webmanifest?paired=1'; }).catch(() => {});
if ('serviceWorker' in navigator && window.isSecureContext) navigator.serviceWorker.register('/sw.js').catch(() => {});
// Wake lock is available only on secure origins; normal phone auto-lock rules
// apply to a plain local HTTP connection.
let wakeLock = null;
async function keepAwake() {
  if (window.isSecureContext && 'wakeLock' in navigator && !document.hidden) {
    try { wakeLock = await navigator.wakeLock.request('screen'); } catch (_) {}
  }
}
document.addEventListener('visibilitychange', keepAwake); keepAwake();
document.addEventListener('visibilitychange', () => { if (document.hidden) { release(); clearTimeout(retry); ws?.close(); } else connect(); });
window.addEventListener('pagehide', () => { release(); ws?.close(); });
document.querySelectorAll('[data-tab]').forEach(button => button.onclick = () => {
  release(); document.querySelectorAll('.panel').forEach(p => p.hidden = p.id !== button.dataset.tab);
  document.querySelectorAll('[data-tab]').forEach(b => b.classList.toggle('selected', b === button));
});
document.querySelectorAll('[data-click]').forEach(button => button.onclick = () => { if (paused) return; flush(); if (dragging) release(); send({type: 'click', button: button.dataset.click}); });
$('double').onclick = () => { if (paused) return; flush(); if (dragging) release(); send({type: 'click', double: true}); };
$('drag').onclick = () => { if (paused || !paired) return; flush(); if (send({type: dragging ? 'up' : 'down', button: 'left'})) setDrag(!dragging); };
document.querySelectorAll('[data-key]').forEach(button => button.onclick = () => { if (!paused) send({type: 'key', key: button.dataset.key}); });
$('sendText').onclick = () => { const text = $('typing').value; if (text && !paused && send({type: 'text', text})) $('typing').value = ''; };
try { $('speed').value = localStorage.getItem('mycursor-speed') || '1.8'; $('natural').checked = localStorage.getItem('mycursor-natural') !== 'false'; } catch (_) {}
function saveSettings() { $('speedValue').value = Number($('speed').value).toFixed(1) + '×'; try { localStorage.setItem('mycursor-speed', $('speed').value); localStorage.setItem('mycursor-natural', String($('natural').checked)); } catch (_) {} }
$('speed').oninput = saveSettings; $('natural').onchange = saveSettings; saveSettings();

const pad = $('pad'); let gesture = null, previous = null;
function resetGesture() { gesture = null; previous = null; pad.classList.remove('active'); }
function center(touches) { let x = 0, y = 0; for (const t of touches) { x += t.clientX; y += t.clientY; } return {x: x / touches.length, y: y / touches.length, n: touches.length, ids: Array.from(touches, t => t.identifier).sort().join(',')}; }
pad.addEventListener('touchstart', event => {
  event.preventDefault(); if (!paired || paused) return;
  const p = center(event.touches);
  if (!gesture) gesture = {start: performance.now(), fingers: p.n, travel: 0, ended: false};
  gesture.fingers = Math.max(gesture.fingers, p.n); previous = p; pad.classList.add('active');
}, {passive: false});
pad.addEventListener('touchmove', event => {
  event.preventDefault(); if (!gesture || !paired || paused || !event.touches.length) return;
  const p = center(event.touches);
  if (previous && p.ids === previous.ids) {
    const dx = p.x - previous.x, dy = p.y - previous.y; gesture.travel += Math.hypot(dx, dy);
    if (!gesture.ended && gesture.fingers === 1 && p.n === 1) {
      const speed = Number($('speed').value); motion('move', dx * speed, dy * speed);
    } else if (!gesture.ended && gesture.fingers === 2 && p.n === 2) {
      const sign = $('natural').checked ? 1 : -1; motion('scroll', -dx / 55 * sign, dy / 55 * sign);
    }
  }
  previous = p;
}, {passive: false});
pad.addEventListener('touchend', event => {
  event.preventDefault(); if (!gesture) return;
  if (event.touches.length) { gesture.ended = true; previous = center(event.touches); return; }
  flush();
  if (!dragging && gesture.travel < 8 && performance.now() - gesture.start < 300) {
    if (gesture.fingers <= 2) send({type: 'click', button: gesture.fingers === 2 ? 'right' : 'left'});
  }
  resetGesture();
}, {passive: false});
pad.addEventListener('touchcancel', event => { event.preventDefault(); release(); }, {passive: false});
pad.addEventListener('contextmenu', event => event.preventDefault());
// Desktop browser fallback, useful for setup and testing.
let mouse = null;
pad.addEventListener('pointerdown', e => { if (e.pointerType !== 'mouse' || paused || !paired) return; pad.setPointerCapture(e.pointerId); mouse = {x: e.clientX, y: e.clientY, start: performance.now(), travel: 0}; });
pad.addEventListener('pointermove', e => { if (!mouse) return; const dx = e.clientX - mouse.x, dy = e.clientY - mouse.y; mouse.travel += Math.hypot(dx, dy); mouse.x = e.clientX; mouse.y = e.clientY; motion('move', dx * Number($('speed').value), dy * Number($('speed').value)); });
pad.addEventListener('pointerup', e => { if (!mouse) return; flush(); if (!dragging && mouse.travel < 8 && performance.now() - mouse.start < 300) send({type:'click', button: e.button === 2 ? 'right' : 'left'}); mouse = null; });
pad.addEventListener('pointercancel', () => { mouse = null; release(); });
connect();
