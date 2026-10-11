// Run with the bundled Node runtime while phone_test_server.py is running.
const { chromium, webkit } = require('playwright');
const assert = require('node:assert/strict');
async function run() {
  const engine = process.env.MYCURSOR_TEST_BROWSER || 'chromium';
  const browser = await (engine === 'webkit' ? webkit : chromium).launch({headless:true, ...(engine === 'chromium' && process.env.MYCURSOR_USE_EDGE === '1' ? {channel:'msedge'} : {})});
  const context = await browser.newContext({viewport:{width:390,height:844},isMobile:true,hasTouch:true});
  const page = await context.newPage();
  const errors=[]; page.on('pageerror',e=>errors.push(e.message));
  await page.goto('http://127.0.0.1:8766/#browser-test-token');
  await page.waitForFunction(()=>document.getElementById('status').textContent.includes('Connected'));
  assert.equal(await page.evaluate(()=>location.hash),'');
  assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth <= innerWidth),true);
  const largeBounds = await page.locator('#pad').boundingBox();
  assert(largeBounds.height > 600, `Large pad is only ${largeBounds.height}px`);
  assert.equal(await page.evaluate(()=>document.documentElement.scrollHeight <= innerHeight + 1),true);
  await page.waitForFunction(()=>document.getElementById('manifest').href.includes('paired=1'));
  const manifest = await (await page.request.get('http://127.0.0.1:8766/manifest.webmanifest')).json();
  assert.equal(manifest.display,'standalone');
  assert.equal(manifest.start_url,'/#browser-test-token');
  assert.equal(manifest.icons.length,2);
  await page.waitForFunction(async()=>!!(await navigator.serviceWorker.getRegistration()));
  await page.locator('#install').click();
  assert.equal(await page.locator('#installHelp').isVisible(),true);
  assert.equal(await page.evaluate(()=>location.hash),'#browser-test-token');
  await page.locator('#closeInstall').click();
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
  await page.locator('#size').click();
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
  await page.locator('#pause').click();
  await page.waitForFunction(()=>document.getElementById('status').textContent.includes('Paused'));
  await page.locator('#pause').click();
  await page.waitForFunction(()=>document.getElementById('status').textContent.includes('Connected'));
  await page.locator('#laser').click();
  await page.waitForFunction(()=>document.getElementById('laser').getAttribute('aria-pressed')==='true');
  await page.locator('#laser').click();
  await page.waitForFunction(()=>document.getElementById('laser').getAttribute('aria-pressed')==='false');
  await page.locator('#reconnect').click();
  await page.waitForFunction(()=>document.getElementById('status').textContent.includes('Connected'));
  await page.locator('[data-tab="touch"]').click();
  await page.locator('#size').click();
  await page.screenshot({path:'phone-touchpad-preview.png',fullPage:true});
  assert.deepEqual(errors,[]);
  console.log(`PASS (${engine}): large-pad layout, paired PWA manifest, service worker, install guide, move, tap, two-finger right click, scroll, drag/release, Unicode typing, slide keys, presentation pointer, pause/resume, reconnect; no browser errors.`);
  await browser.close();
}
run().catch(e=>{console.error(e);process.exit(1)});
