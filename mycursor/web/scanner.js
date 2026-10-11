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
  function decode(source, width, height, region = [0, 0, width, height], limit = 1600, contrast = false) {
    const [x, y, w, h] = region;
    const scale = Math.min(1, limit / Math.max(w, h));
    canvas.width = Math.max(1, Math.round(w * scale)); canvas.height = Math.max(1, Math.round(h * scale));
    ctx.drawImage(source, x, y, w, h, 0, 0, canvas.width, canvas.height);
    const pixels = ctx.getImageData(0, 0, canvas.width, canvas.height);
    if (contrast) {
      // Expand washed-out screen photographs without applying a hard threshold
      // that would destroy the decoder's local lighting correction.
      for (let i = 0; i < pixels.data.length; i += 4) {
        const gray = .299 * pixels.data[i] + .587 * pixels.data[i+1] + .114 * pixels.data[i+2];
        const value = Math.max(0, Math.min(255, (gray - 128) * 1.8 + 128));
        pixels.data[i] = pixels.data[i+1] = pixels.data[i+2] = value;
      }
    }
    return window.jsQR(pixels.data, pixels.width, pixels.height, {inversionAttempts: 'attemptBoth'})?.data;
  }
  async function decodePhoto(image, current) {
    const width = image.naturalWidth, height = image.naturalHeight;
    const initial = decode(image, width, height);
    if (initial) return initial;
    const whole = [0, 0, width, height];
    const regions = [whole];
    // Preserve small QR modules in full-resolution iPhone photos. Overlapping
    // crops also find a code off centre without splitting it at tile boundaries.
    for (const fraction of [.6, .35]) {
      const w = width * fraction, h = height * fraction;
      regions.push([(width-w)/2, (height-h)/2, w, h]);
      for (const y of [0, (height-h)/2, height-h]) {
        for (const x of [0, (width-w)/2, width-w]) {
          if (x === (width-w)/2 && y === (height-h)/2) continue;
          regions.push([x, y, w, h]);
        }
      }
    }
    for (const contrast of [false, true]) {
      for (const region of regions) {
        await new Promise(resolve => setTimeout(resolve, 0));
        if (current !== epoch || !el('scanDialog').open) return;
        const code = decode(image, width, height, region, 2000, contrast);
        if (code) return code;
      }
    }
  }
  async function photo(file) {
    if (!file) return;
    const current = ++epoch, url = URL.createObjectURL(file), image = new Image();
    el('scanStatus').textContent = 'Reading…';
    try {
      await new Promise((resolve, reject) => { image.onload = resolve; image.onerror = reject; image.src = url; });
      if (current !== epoch || !el('scanDialog').open) return;
      const code = await decodePhoto(image, current);
      if (current !== epoch || !el('scanDialog').open) return;
      if (!code) throw new Error('Move closer so the QR fills the photo. Keep all four edges visible.');
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
