// Run with the bundled Node runtime while phone_test_server.py is running.
const { chromium, webkit } = require('playwright');
const assert = require('node:assert/strict');
async function run() {
  const engine = process.env.MYCURSOR_TEST_BROWSER || 'chromium';
  const browser = await (engine === 'webkit' ? webkit : chromium).launch({headless:true, ...(engine === 'chromium' && process.env.MYCURSOR_USE_EDGE === '1' ? {channel:'msedge'} : {})});
  const context = await browser.newContext({viewport:{width:390,height:844},isMobile:true,hasTouch:true});
  await context.addInitScript(() => {
    Object.defineProperty(window,'isSecureContext',{value:false});
    Object.defineProperty(navigator,'standalone',{value:true});
  });
  const page = await context.newPage();
  const errors=[]; page.on('pageerror',e=>errors.push(e.message));
  await page.goto('http://127.0.0.1:8766/');
  await page.waitForFunction(()=>document.getElementById('scan') && !document.getElementById('pairing').hidden);
  assert.equal(await page.locator('#mouseButtons').isVisible(),false);
  assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth <= innerWidth),true);
  const qr = await (await page.request.get('http://127.0.0.1:8766/test-qr.png')).body();
  const invalidQr = await (await page.request.get('http://127.0.0.1:8766/test-qr.png?invalid=1')).body();
  async function capture(buffer,name) {
    const box = await page.locator('#qrPhoto').boundingBox();
    const [chooser] = await Promise.all([
      page.waitForEvent('filechooser'),
      page.touchscreen.tap(box.x+box.width/2,box.y+box.height/2)
    ]);
    await chooser.setFiles({name,mimeType:'image/png',buffer});
  }
  { const box = await page.locator('#scan').boundingBox(); await page.touchscreen.tap(box.x+box.width/2,box.y+box.height/2); }
  await page.waitForFunction(()=>document.getElementById('scanDialog').open);
  await capture(invalidQr,'invalid-qr.png');
  await page.waitForFunction(()=>document.getElementById('scanStatus').textContent.includes('MyCursor PC pairing code'));
  assert.equal(await page.locator('#scanDialog').isVisible(),true);
  assert.equal(await page.evaluate(()=>location.host),'127.0.0.1:8766');
  await page.locator('#closeScan').click();
  async function scan() {
    { const box = await page.locator('#scan').boundingBox(); await page.touchscreen.tap(box.x+box.width/2,box.y+box.height/2); }
  await page.waitForFunction(()=>document.getElementById('scanDialog').open);
    await capture(qr,'pc-qr.png');
    await page.waitForFunction(()=>document.getElementById('status').textContent==='Connected');
    assert.equal(await page.locator('#scanDialog').isVisible(),false);
    assert.equal(await page.locator('#scan').isVisible(),false);
  }
  await scan();
  assert.equal(await page.evaluate(()=>location.hash),'');
  const largeBounds = await page.locator('#pad').boundingBox();
  assert(largeBounds.height > 650, `Touchpad is only ${largeBounds.height}px`);
  assert.equal(await page.evaluate(()=>document.documentElement.scrollHeight <= innerHeight + 1),true);
  await page.waitForFunction(()=>document.getElementById('manifest').href.includes('paired=1'));
  const manifest = await (await page.request.get('http://127.0.0.1:8766/manifest.webmanifest')).json();
  assert.equal(manifest.display,'standalone');
  assert.equal(manifest.start_url,'/#browser-test-token-0123456789012345678901234');
  assert.equal(manifest.icons.length,2);
  await page.locator('#settings').click();
  assert.equal(await page.locator('#install').isVisible(),false);
  await page.locator('#closeSettings').click();
  async function touch(type, points) {
    await page.evaluate(({type,points})=>{
      const pad=document.getElementById('pad');
      const values=points.map(p=>({identifier:p[0],target:pad,clientX:p[1],clientY:p[2]}));
      let event;
      try {
        const touches=values.map(v=>new Touch(v));
        event=new TouchEvent(type,{touches,targetTouches:touches,changedTouches:touches,bubbles:true,cancelable:true});
      } catch (_) {
        // WebKit exposes native Touch instances but does not allow constructing
        // them. Provide the same TouchList fields for deterministic gestures.
        event=new Event(type,{bubbles:true,cancelable:true});
        Object.defineProperties(event,{touches:{value:values},targetTouches:{value:values},changedTouches:{value:values}});
      }
      pad.dispatchEvent(event);
    },{type,points});
    await page.waitForTimeout(25);
  }
  await touch('touchstart',[[1,100,300]]);
  await touch('touchmove',[[1,120,310]]);
  await touch('touchend',[]);
  await touch('touchstart',[[2,100,300]]); await touch('touchend',[]);
  await touch('touchstart',[[3,100,300],[4,150,300]]);
  await touch('touchend',[[4,150,300]]); await touch('touchend',[]);
  await touch('touchstart',[[5,100,300],[6,150,300]]);
  await touch('touchmove',[[5,100,355],[6,150,355]]);
  await touch('touchend',[[6,150,355]]); await touch('touchend',[]);
  await page.locator('#drag').click();
  await page.waitForFunction(async()=>{
    const data = await (await fetch('/test-events')).json();
    return data.held.includes('left');
  });
  let events = await (await page.request.get('http://127.0.0.1:8766/test-events')).json();
  assert.deepEqual(events.held,['left']);
  await touch('touchstart',[[7,100,300]]); await touch('touchmove',[[7,110,300]]); await touch('touchend',[]);
  await page.locator('#drag').click();
  await page.locator('#settings').click();
  await page.locator('[data-tab="keys"]').click();
  await page.locator('#typing').fill('café 😀'); await page.locator('#sendText').click();
  await page.locator('[data-key="copy"]').click();
  await page.locator('[data-tab="slides"]').click(); await page.locator('[data-key="pagedown"]').click();
  await page.waitForTimeout(100);
  events=await (await page.request.get('http://127.0.0.1:8766/test-events')).json();
  assert.deepEqual(events.held,[]);
  assert(events.events.some(e=>e[0]==='move' && Math.abs(e[1]-36)<.01 && Math.abs(e[2]-18)<.01));
  assert(events.events.some(e=>e[0]==='click' && e[1]==='left'));
  assert(events.events.some(e=>e[0]==='click' && e[1]==='right'));
  assert(events.events.some(e=>e[0]==='scroll' && e[1]===1));
  assert(events.events.some(e=>e[0]==='text' && e[1]==='café 😀'));
  assert(events.events.some(e=>e[0]==='key' && e[1]==='pagedown'));
  await page.locator('[data-tab="general"]').click();
  await page.locator('#pause').click();
  await page.waitForFunction(()=>document.getElementById('status').textContent.includes('Paused'));
  await page.locator('#pause').click();
  await page.waitForFunction(()=>document.getElementById('status').textContent.includes('Connected'));
  await page.locator('[data-tab="slides"]').click();
  await page.locator('#laser').click();
  await page.waitForFunction(()=>document.getElementById('laser').getAttribute('aria-pressed')==='true');
  await page.locator('#laser').click();
  await page.waitForFunction(()=>document.getElementById('laser').getAttribute('aria-pressed')==='false');
  await page.locator('[data-tab="general"]').click();
  await page.locator('#disconnect').click();
  await page.waitForFunction(()=>!document.getElementById('pairing').hidden);
  assert.equal(await page.locator('#mouseButtons').isVisible(),false);
  await page.reload();
  await page.waitForTimeout(300);
  assert.equal(await page.locator('#scan').isVisible(),true);
  // The old reader is loaded only by this regression test, never by the app.
  await page.addScriptTag({url:'http://127.0.0.1:8766/jsqr.js'});
  for (const position of ['center', 'corner']) {
    const oldDecoderResult = await page.evaluate(async position => {
      const image = new Image(); image.src = `/test-qr.png?photo=${position}`;
      await image.decode();
      const canvas = document.createElement('canvas');
      const scale = 1600 / Math.max(image.width, image.height);
      canvas.width = Math.round(image.width * scale); canvas.height = Math.round(image.height * scale);
      const ctx = canvas.getContext('2d'); ctx.drawImage(image, 0, 0, canvas.width, canvas.height);
      const pixels = ctx.getImageData(0, 0, canvas.width, canvas.height);
      return !!window.jsQR(pixels.data, pixels.width, pixels.height, {inversionAttempts:'attemptBoth'});
    }, position);
    assert.equal(oldDecoderResult, false, 'Fixture must reproduce the original photo downscaling failure');
    const photo = await (await page.request.get(`http://127.0.0.1:8766/test-qr.png?photo=${position}`)).body();
    const box = await page.locator('#scan').boundingBox();
    await page.touchscreen.tap(box.x+box.width/2,box.y+box.height/2);
    await page.waitForFunction(()=>document.getElementById('scanDialog').open);
    await capture(photo,`screen-${position}.jpg`);
    await page.waitForFunction(()=>document.getElementById('status').textContent==='Connected',null,{timeout:30000});
    await page.locator('#settings').click();
    await page.locator('#disconnect').click();
  }
  // A camera failure must still allow pairing without a photo or Safari.
  const blank = Buffer.from(await page.evaluate(()=>{
    const canvas = document.createElement('canvas'); canvas.width=100; canvas.height=100;
    const ctx=canvas.getContext('2d');ctx.fillStyle='white';ctx.fillRect(0,0,100,100);
    return canvas.toDataURL('image/png').split(',')[1];
  }),'base64');
  { const box=await page.locator('#scan').boundingBox(); await page.touchscreen.tap(box.x+box.width/2,box.y+box.height/2); }
  await capture(blank,'no-qr.png');
  await page.waitForFunction(()=>document.getElementById('scanStatus').textContent.includes('QR unreadable'));
  assert.equal(await page.locator('#pcCode').isVisible(),true);
  await page.locator('#pcCode').fill('bad');
  await page.locator('#connectCode').click();
  await page.waitForFunction(()=>document.getElementById('codeStatus').textContent.includes('eight digits'));
  const {code} = await (await page.request.get('http://127.0.0.1:8766/test-code')).json();
  await page.locator('#pcCode').fill(code.slice(0,4)+' '+code.slice(4));
  await page.locator('#connectCode').click();
  await page.waitForFunction(()=>document.getElementById('status').textContent==='Connected');
  assert.equal(await page.locator('#scanDialog').isVisible(),false);
  await page.locator('#settings').click(); await page.locator('#disconnect').click();
  await scan();
  await page.locator('#drag').click();
  await page.waitForFunction(async()=> (await (await fetch('/test-events')).json()).held.includes('left'));
  await page.request.post('http://127.0.0.1:8766/test-drop');
  await page.waitForFunction(()=>!document.getElementById('pairing').hidden);
  const released = await (await page.request.get('http://127.0.0.1:8766/test-events')).json();
  assert.deepEqual(released.held,[]);
  await page.screenshot({path:'phone-scan-preview.png',fullPage:true});
  await scan();
  await page.screenshot({path:'phone-touchpad-preview.png',fullPage:true});
  assert.deepEqual(errors,[]);
  console.log(`PASS (${engine}): ZXing QR-only WASM decoder, camera-sized blurred/rotated JPEGs, unreadable photo → code pairing → authenticated connection, installed-iPhone detection, disconnect/Scan state, network loss releases drag, large-pad layout, paired PWA manifest, service worker, install guide, movement and gestures; no browser errors.`);
  await context.close();
  const browserContext = await browser.newContext({viewport:{width:390,height:844},isMobile:true,hasTouch:true});
  const installPage = await browserContext.newPage();
  await installPage.goto('http://127.0.0.1:8766/');
  await installPage.locator('#settings').click();
  assert.equal(await installPage.locator('#install').isVisible(),true);
  await installPage.locator('#install').click();
  assert.equal(await installPage.locator('#installHelp').isVisible(),true);
  await installPage.evaluate(()=>window.dispatchEvent(new Event('appinstalled')));
  assert.equal(await installPage.locator('#installHelp').isVisible(),false);
  assert.equal(await installPage.locator('#install').isVisible(),false);
  await installPage.waitForFunction(async()=>!!(await navigator.serviceWorker.getRegistration()));
  assert.equal(await installPage.evaluate(()=>typeof window.ZXingWASM.readBarcodes),'function');
  await browser.close();
}
run().catch(e=>{console.error(e);process.exit(1)});
