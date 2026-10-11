'use strict';
const $ = id => document.getElementById(id);
let token = location.hash.slice(1), intent = true;
try {
  if (token) localStorage.setItem('mycursor-token', token);
  else token = localStorage.getItem('mycursor-token') || '';
  intent = localStorage.getItem('mycursor-connect-intent') !== 'false';
} catch (_) {}
if (location.hash) history.replaceState(null, '', location.pathname);
let ws, paired = false, paused = false, dragging = false, generation = 0;
let pending = null, frame = null, lastPong = 0, laser = false, suspended = false, timeout = null;
let toastTimer;
function toast(message) { $('toast').textContent = message; $('toast').hidden = false; clearTimeout(toastTimer); toastTimer = setTimeout(() => $('toast').hidden = true, 4500); }
function rememberIntent(value) { intent = value; try { localStorage.setItem('mycursor-connect-intent', String(value)); } catch (_) {} }
function ui(label = 'Scan to connect') {
  $('status').textContent = paired ? (paused ? 'Paused' : 'Connected') : label;
  $('dot').classList.toggle('online', paired && !paused);
  $('pairing').hidden = paired; $('surface-mark').hidden = !paired;
  $('mouseButtons').hidden = !paired; $('pad').setAttribute('data-enabled', String(paired && !paused));
  $('deviceStatus').textContent = paired ? location.hostname : 'Not connected';
  $('disconnect').hidden = !paired; $('pause').disabled = !paired;
  $('pause').textContent = paused ? 'Resume' : 'Pause';
}
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
function setDrag(value) { dragging = value; $('drag').setAttribute('aria-pressed', String(value)); $('drag').setAttribute('aria-label', value ? 'Release drag' : 'Hold to drag'); $('pad').classList.toggle('dragging', value); }
function release() { discard(); send({type:'release'}); setDrag(false); resetGesture(); }
function disconnect(manual = true) {
  release(); generation++; clearTimeout(timeout);
  if (ws) { ws.onclose = null; ws.close(); ws = null; }
  paired = false; paused = false;
  if (manual) rememberIntent(false);
  ui();
}
function pairManifest() {
  fetch('/pair', {method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({token})})
    .then(response => { if (response.ok) $('manifest').href = '/manifest.webmanifest?paired=1'; }).catch(() => {});
}
function connect() {
  if (!token || !intent || document.hidden) { ui(); return; }
  disconnect(false); const current = generation; ui('Connecting');
  $('scan').disabled = true;
  ws = new WebSocket(`${location.protocol === 'https:' ? 'wss' : 'ws'}://${location.host}/ws`);
  timeout = setTimeout(() => { if (current === generation && !paired) { disconnect(); $('scan').disabled = false; toast('PC unavailable. Check Wi-Fi and scan again.'); } }, 8000);
  ws.onopen = () => { if (current === generation) ws.send(JSON.stringify({type:'auth',token})); };
  ws.onmessage = event => {
    if (current !== generation) return;
    const data = JSON.parse(event.data);
    if (data.type === 'state') {
      clearTimeout(timeout); paired = true; paused = data.paused; lastPong = Date.now(); $('scan').disabled = false;
      laser = !!data.laser; $('laser').disabled = !data.laserSupported;
      $('laser').setAttribute('aria-pressed',String(laser)); $('laser').textContent = laser ? 'Pointer on' : 'Pointer off';
      if (paused) release(); ui(); pairManifest();
    } else if (data.type === 'pong') lastPong = Date.now();
    else if (data.type === 'error') {
      release(); toast(data.message);
      if (data.fatal) { disconnect(); $('scan').disabled = false; }
    }
  };
  ws.onclose = () => {
    if (current !== generation) return;
    clearTimeout(timeout); discard(); setDrag(false); resetGesture(); paired = false; paused = false;
    if (!suspended) rememberIntent(false);
    $('scan').disabled = false; ui();
  };
  ws.onerror = () => { if (current === generation) toast('PC unavailable. Check Wi-Fi.'); };
}
function acceptCode(value) {
  let url;
  try { url = new URL(value.trim()); } catch (_) { throw new Error('This is not a MyCursor pairing code.'); }
  const host = url.hostname;
  const local = host === location.hostname || host === 'localhost' || host.endsWith('.local') || /^(127\.|10\.|192\.168\.|172\.(1[6-9]|2\d|3[01])\.)/.test(host);
  if (!['http:','https:'].includes(url.protocol) || url.username || url.password || url.pathname !== '/' || url.search || !local || !/^[A-Za-z0-9_-]{16,256}$/.test(url.hash.slice(1))) throw new Error('Scan a MyCursor PC pairing code.');
  window.MyCursorScanner.close();
  if (url.origin !== location.origin) { location.assign(url.href); return; }
  token = url.hash.slice(1);
  try { localStorage.setItem('mycursor-token',token); } catch (_) {}
  rememberIntent(true); connect();
}
$('scan').onclick = () => { release(); window.MyCursorScanner.open(acceptCode); };
$('codeForm').onsubmit = async event => {
  event.preventDefault();
  const code = $('pcCode').value.replace(/[\s-]/g, '');
  if (!/^\d{8}$/.test(code)) { $('codeStatus').textContent = 'Enter the eight digits shown on your PC.'; return; }
  $('connectCode').disabled = true; $('codeStatus').textContent = 'Connecting…';
  const controller = new AbortController(), timer = setTimeout(()=>controller.abort(),8000);
  try {
    const response = await fetch('/pair-code', {method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({code}),signal:controller.signal});
    const data = await response.json();
    if (!response.ok) throw new Error(data.error || 'Could not pair.');
    if (!$('scanDialog').open) return;
    acceptCode(`${location.origin}/#${data.token}`);
    $('pcCode').value = ''; $('codeStatus').textContent = '';
  } catch (error) { $('codeStatus').textContent = error.name === 'AbortError' ? 'PC unavailable. Check Wi-Fi.' : error.message || 'PC unavailable. Check Wi-Fi.'; }
  finally { clearTimeout(timer); $('connectCode').disabled = false; }
};
$('settings').onclick = () => { release(); $('settingsDialog').showModal(); };
$('closeSettings').onclick = () => $('settingsDialog').close();
$('disconnect').onclick = () => { disconnect(); $('settingsDialog').close(); };
$('pause').onclick = () => { release(); send({type:'pause'}); };
$('laser').onclick = () => { if (!paused) send({type:'laser',enabled:!laser}); };
$('linkForm').onsubmit = event => { event.preventDefault(); try { acceptCode($('pairLink').value); $('settingsDialog').close(); } catch (error) { toast(error.message); } };
setInterval(() => { if (paired) { if (Date.now() - lastPong > 4000) { ws.close(); return; } send({type:'ping'}); } },1000);
let installPrompt = null, installed = false;
const standalone = window.matchMedia('(display-mode: standalone)');
function installState() {
  installed = standalone.matches || window.navigator.standalone === true || installed;
  $('install').hidden = installed;
  if (installed && $('installHelp').open) $('installHelp').close();
}
standalone.addEventListener('change',installState);
window.addEventListener('appinstalled',() => { installed = true; installState(); });
window.addEventListener('beforeinstallprompt',event => { event.preventDefault(); if (!installed) installPrompt = event; });
$('install').onclick = async () => {
  release();
  if (installPrompt) { await installPrompt.prompt(); installPrompt = null; }
  else { if (token) history.replaceState(null,'','/#'+token); $('installHelp').showModal(); }
};
$('closeInstall').onclick = () => $('installHelp').close(); installState();
if ('serviceWorker' in navigator && window.isSecureContext) navigator.serviceWorker.register('/sw.js').catch(() => {});
let wakeLock = null;
async function keepAwake() { if (window.isSecureContext && 'wakeLock' in navigator && !document.hidden) { try { wakeLock = await navigator.wakeLock.request('screen'); } catch (_) {} } }
document.addEventListener('visibilitychange',() => {
  installState();
  if (document.hidden) { suspended = true; disconnect(false); }
  else { suspended = false; keepAwake(); if (intent && !$('scanDialog').open) connect(); }
});
window.addEventListener('pagehide',() => disconnect(false)); keepAwake();
document.querySelectorAll('[data-tab]').forEach(button => button.onclick = () => {
  release(); document.querySelectorAll('.panel').forEach(p => p.hidden = p.id !== button.dataset.tab);
  document.querySelectorAll('[data-tab]').forEach(b => b.classList.toggle('selected',b === button));
});
document.querySelectorAll('[data-click]').forEach(button => button.onclick = () => { if (paused) return; flush(); if (dragging) release(); send({type:'click',button:button.dataset.click}); });
$('double').onclick = () => { if (paused) return; flush(); if (dragging) release(); send({type:'click',double:true}); };
$('drag').onclick = () => { if (paused || !paired) return; flush(); if (send({type:dragging ? 'up':'down',button:'left'})) setDrag(!dragging); };
document.querySelectorAll('[data-key]').forEach(button => button.onclick = () => { if (!paused) send({type:'key',key:button.dataset.key}); });
$('sendText').onclick = () => { const text = $('typing').value; if (text && !paused && send({type:'text',text})) $('typing').value = ''; };
try { $('speed').value = localStorage.getItem('mycursor-speed') || '1.8'; $('natural').checked = localStorage.getItem('mycursor-natural') !== 'false'; } catch (_) {}
function saveSettings() { $('speedValue').value = Number($('speed').value).toFixed(1)+'×'; try { localStorage.setItem('mycursor-speed',$('speed').value); localStorage.setItem('mycursor-natural',String($('natural').checked)); } catch (_) {} }
$('speed').oninput = saveSettings; $('natural').onchange = saveSettings; saveSettings();
const pad = $('pad'); let gesture = null, previous = null;
function resetGesture() { gesture = null; previous = null; pad.classList.remove('active'); }
function center(touches) { let x = 0, y = 0; for (const t of touches) { x += t.clientX; y += t.clientY; } return {x: x / touches.length, y: y / touches.length, n: touches.length, ids: Array.from(touches, t => t.identifier).sort().join(',')}; }
pad.addEventListener('touchstart', event => {
  if (event.target.closest('button,input,label')) return;
  event.preventDefault(); if (!paired || paused) return;
  const p = center(event.touches);
  if (!gesture) gesture = {start: performance.now(), fingers: p.n, travel: 0, ended: false};
  gesture.fingers = Math.max(gesture.fingers, p.n); previous = p; pad.classList.add('active');
}, {passive: false});
pad.addEventListener('touchmove', event => {
  if (event.target.closest('button,input,label')) return;
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
  if (event.target.closest('button,input,label')) return;
  event.preventDefault(); if (!gesture) return;
  if (event.touches.length) { gesture.ended = true; previous = center(event.touches); return; }
  flush();
  if (!dragging && gesture.travel < 8 && performance.now() - gesture.start < 300) {
    if (gesture.fingers <= 2) send({type: 'click', button: gesture.fingers === 2 ? 'right' : 'left'});
  }
  resetGesture();
}, {passive: false});
pad.addEventListener('touchcancel', event => { if (event.target.closest('button,input,label')) return; event.preventDefault(); release(); }, {passive: false});
pad.addEventListener('contextmenu', event => event.preventDefault());
// Desktop browser fallback, useful for setup and testing.
let mouse = null;
pad.addEventListener('pointerdown', e => { if (e.pointerType !== 'mouse' || paused || !paired) return; pad.setPointerCapture(e.pointerId); mouse = {x: e.clientX, y: e.clientY, start: performance.now(), travel: 0}; });
pad.addEventListener('pointermove', e => { if (!mouse) return; const dx = e.clientX - mouse.x, dy = e.clientY - mouse.y; mouse.travel += Math.hypot(dx, dy); mouse.x = e.clientX; mouse.y = e.clientY; motion('move', dx * Number($('speed').value), dy * Number($('speed').value)); });
pad.addEventListener('pointerup', e => { if (!mouse) return; flush(); if (!dragging && mouse.travel < 8 && performance.now() - mouse.start < 300) send({type:'click', button: e.button === 2 ? 'right' : 'left'}); mouse = null; });
pad.addEventListener('pointercancel', () => { mouse = null; release(); });
connect();
