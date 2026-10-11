'use strict';
window.MyCursorScanner = (() => {
  let stream = null, frame = null, epoch = 0, accept;
  const el = id => document.getElementById(id);
  const canvas = document.createElement('canvas');
  const ctx = canvas.getContext('2d', {willReadFrequently: true});
  function stop() {
    epoch++;
    if (frame !== null) cancelAnimationFrame(frame);
    frame = null; stream?.getTracks().forEach(track => track.stop()); stream = null;
    el('scanVideo').srcObject = null; el('scanVideo').hidden = true; el('cameraMark').hidden = false;
  }
  function decode(source, width, height) {
    const scale = Math.min(1, 1600 / Math.max(width, height));
    canvas.width = Math.round(width * scale); canvas.height = Math.round(height * scale);
    ctx.drawImage(source, 0, 0, canvas.width, canvas.height);
    const pixels = ctx.getImageData(0, 0, canvas.width, canvas.height);
    return window.jsQR(pixels.data, pixels.width, pixels.height, {inversionAttempts: 'attemptBoth'})?.data;
  }
  async function photo(file) {
    if (!file) return;
    const current = epoch, url = URL.createObjectURL(file), image = new Image();
    el('scanStatus').textContent = 'Reading…';
    try {
      await new Promise((resolve, reject) => { image.onload = resolve; image.onerror = reject; image.src = url; });
      if (current !== epoch || !el('scanDialog').open) return;
      const code = decode(image, image.naturalWidth, image.naturalHeight);
      if (!code) throw new Error('No QR code found. Try again.');
      accept(code);
    } catch (error) { el('scanStatus').textContent = error.message || 'Could not read photo. Try again.'; }
    finally { URL.revokeObjectURL(url); el('qrPhoto').value = ''; }
  }
  async function camera() {
    if (!window.isSecureContext || !navigator.mediaDevices?.getUserMedia) {
      el('scanStatus').textContent = 'Photograph the code on your PC.'; return;
    }
    stop(); const current = epoch;
    try {
      const acquired = await navigator.mediaDevices.getUserMedia({video:{facingMode:{ideal:'environment'},width:{ideal:1280}},audio:false});
      if (current !== epoch || !el('scanDialog').open) { acquired.getTracks().forEach(t=>t.stop()); return; }
      stream = acquired; const video = el('scanVideo'); video.srcObject = stream;
      video.hidden = false; el('cameraMark').hidden = true; await video.play();
      el('scanStatus').textContent = 'Point at the code on your PC.';
      function tick() {
        if (current !== epoch) return;
        if (video.readyState >= 2 && video.videoWidth) {
          const code = decode(video, video.videoWidth, video.videoHeight);
          if (code) { try { accept(code); return; } catch (error) { el('scanStatus').textContent = error.message; } }
        }
        frame = requestAnimationFrame(tick);
      }
      tick();
    } catch (_) { el('scanStatus').textContent = 'Use Open camera to photograph the code.'; }
  }
  function open(onCode) { accept = onCode; stop(); el('scanStatus').textContent = 'Scan the code on your PC.'; el('scanDialog').showModal(); camera(); }
  function close() { stop(); if (el('scanDialog').open) el('scanDialog').close(); }
  el('qrPhoto').onchange = event => photo(event.target.files[0]);
  el('closeScan').onclick = close; el('scanDialog').addEventListener('close', stop);
  document.addEventListener('visibilitychange', () => {
    if (document.hidden) {
      // Native camera capture temporarily backgrounds an iPhone Home Screen
      // app. Release video hardware without invalidating its returning photo.
      if (frame !== null) cancelAnimationFrame(frame);
      frame = null; stream?.getTracks().forEach(t => t.stop()); stream = null;
      el('scanVideo').srcObject = null; el('scanVideo').hidden = true;
      el('cameraMark').hidden = false;
    }
  });
  return {open, close};
})();
