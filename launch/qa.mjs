import fs from 'node:fs';
import path from 'node:path';
import { pathToFileURL } from 'node:url';
import { launchChrome } from '../tools/motionmaxxing/scripts/_cdp.mjs';
const br=await launchChrome({args:['--allow-file-access-from-files']});
try{
 const page=await br.newPage({width:1920,height:1080});
 await page.goto(pathToFileURL(path.resolve('launch/film/index.html?selftest')).href.replace('%3Fselftest','?selftest'));
 const result=await page.eval('window.__ready');
 fs.writeFileSync('launch/seek-check.json',JSON.stringify(result,null,2));
 console.log(JSON.stringify(result));
 if(!result?.ok)process.exitCode=1;
}finally{await br.close()}
