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
  // ZXing-C++ reads QR codes only; its WASM and script are served by the PC.
  // No cloud decoder, CDN, or photograph upload is used.
  window.ZXingWASM.prepareZXingModule({overrides:{locateFile:()=>'/zxing_reader.wasm'}});
  const options = {formats:['QRCode'],tryHarder:true,tryRotate:true,tryInvert:true,
    tryDownscale:true,tryDenoise:true,maxNumberOfSymbols:1};
  async function decode(source, width, height, region = [0, 0, width, height], limit = 2048) {
    const [x, y, w, h] = region, scale = Math.min(1, limit / Math.max(w, h));
    canvas.width = Math.max(1, Math.round(w * scale)); canvas.height = Math.max(1, Math.round(h * scale));
    ctx.drawImage(source, x, y, w, h, 0, 0, canvas.width, canvas.height);
    const pixels = ctx.getImageData(0, 0, canvas.width, canvas.height);
    const results = await window.ZXingWASM.readBarcodes(pixels, options);
    return results.find(result=>result.isValid && result.format === 'QRCode')?.text;
  }
  async function decodePhoto(image, current) {
    const width = image.naturalWidth, height = image.naturalHeight;
    const regions = [[0,0,width,height,2048],[0,0,width,height,4096]];
    const w = width * .6, h = height * .6;
    regions.push([(width-w)/2,(height-h)/2,w,h,2048]);
    for (const y of [0, (height-h)/2, height-h]) {
      for (const x of [0, (width-w)/2, width-w]) {
        if (x === (width-w)/2 && y === (height-h)/2) continue;
        regions.push([x,y,w,h,2048]);
      }
    }
    for (const [x,y,w,h,limit] of regions) {
      await new Promise(resolve=>setTimeout(resolve,0));
      if (current !== epoch || !el('scanDialog').open) return;
      const code = await decode(image,width,height,[x,y,w,h],limit);
      if (code) return code;
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
      if (!code) throw new Error('QR unreadable. Connect with the code on your PC instead.');
      accept(code);
    } catch (error) {
      if (current !== epoch || !el('scanDialog').open) return;
      el('scanStatus').textContent = error.message?.includes('pairing code') ? error.message : 'QR unreadable. Connect with the code on your PC instead.';
      el('codePairing').open = true;
    }
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
      async function tick() {
        if (current !== epoch) return;
        if (video.readyState >= 2 && video.videoWidth) {
          let code;
          try { code = await decode(video, video.videoWidth, video.videoHeight); }
          catch (_) { el('scanStatus').textContent = 'Use the code on your PC to connect.'; el('codePairing').open = true; return; }
          if (current !== epoch) return;
          if (code) { try { accept(code); return; } catch (error) { el('scanStatus').textContent = error.message; } }
        }
        frame = requestAnimationFrame(tick);
      }
      tick();
    } catch (_) { el('scanStatus').textContent = 'Use Open camera to photograph the code.'; }
  }
  function open(onCode) { accept = onCode; stop(); el('codeStatus').textContent = ''; el('pcCode').value = '';  el('scanStatus').textContent = 'Scan the code on your PC.'; el('scanDialog').showModal(); camera(); }
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
