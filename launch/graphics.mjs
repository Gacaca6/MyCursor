import fs from 'node:fs';
import path from 'node:path';
import { createRequire } from 'node:module';
import { fileURLToPath } from 'node:url';
import { compose, LAYOUTS } from '../tools/goldie/src/layouts.ts';
const require=createRequire(import.meta.url);
const {createCanvas,loadImage,GlobalFonts}=require('@napi-rs/canvas');
const root=path.dirname(fileURLToPath(import.meta.url));
const assets=path.join(root,'film/assets');
const out=path.join(root,'graphics');fs.mkdirSync(out,{recursive:true});
for(const [file,family] of [['display.ttf','Bricolage'],['body.ttf','Instrument']]) {
 if(fs.existsSync(path.join(assets,file)))GlobalFonts.registerFromPath(path.join(assets,file),family);
}
const ink='#141715',paper='#f4f2ec',mint='#96e9ca',green='#0d6e52';
const scenes=[
 {id:'touchpad',image:'pad',headline:['Your phone.','Your mouse.'],sub:'Tap, scroll and drag on your Windows PC.',layout:'classic',dark:false},
 {id:'present',image:'present',headline:['Own the room.'],sub:'Change slides. Keep your notes close.',layout:'tilt',dark:true},
 {id:'media',image:'media',headline:['Stay on','the sofa.'],sub:'Play, pause and turn it up from your phone.',layout:'hero',dark:false},
 {id:'share',image:'share',headline:['Send it.','Skip the cable.'],sub:'Move files between your phone and PC.',layout:'classic',dark:true},
 {id:'typing',image:'typing',headline:['Type here.','See it there.'],sub:'Your phone keyboard. Your Windows PC.',layout:'tilt',dark:false}
];
const shots={};for(const s of ['pad','present','media','share','typing'])shots[s]=await loadImage(path.join(assets,`device-${s}.webp`));
const logo=await loadImage(path.join(assets,'icon.png'));
function text(ctx,t,x,y,size,color=ink,weight=700,align='left',family='Bricolage') {ctx.font=`${weight} ${size}px ${family}`;ctx.fillStyle=color;ctx.textAlign=align;ctx.textBaseline='top';ctx.fillText(t,x,y);}
function ground(ctx,w,h,dark=false){ctx.fillStyle=dark?'#101715':paper;ctx.fillRect(0,0,w,h);const g=ctx.createRadialGradient(w*.8,h*.6,0,w*.8,h*.6,w*.9);g.addColorStop(0,dark?'#244d3d':'#cbe9da');g.addColorStop(1,dark?'#101715':paper);ctx.fillStyle=g;ctx.fillRect(0,0,w,h);ctx.globalAlpha=.055;ctx.fillStyle=dark?'#ffffff':'#0d6e52';for(let i=0;i<13000;i++){const x=((i*7919)%100003)/100003*w,y=((i*1543)%99991)/99991*h;ctx.fillRect(x,y,1,1)}ctx.globalAlpha=1;}
function device(ctx,img,r,rotation=0){ctx.save();ctx.translate(r.left+r.width/2,r.top+r.height/2);ctx.rotate(rotation*Math.PI/180);ctx.shadowColor='#00000055';ctx.shadowBlur=38;ctx.shadowOffsetY=24;ctx.drawImage(img,-r.width/2,-r.height/2,r.width,r.height);ctx.restore();}
function wrap(ctx,t,max){const words=t.split(' '),lines=[];let line='';for(const word of words){const candidate=line?line+' '+word:word;if(ctx.measureText(candidate).width>max&&line){lines.push(line);line=word}else line=candidate;}if(line)lines.push(line);return lines;}
for(const size of [{width:1080,height:1920,label:'story'},{width:1080,height:1350,label:'feed'}])for(const s of scenes){
 const {width:w,height:h}=size;const can=createCanvas(w,h),ctx=can.getContext('2d');ground(ctx,w,h,s.dark);const color=s.dark?paper:ink;
 ctx.drawImage(logo,70,50,44,44);text(ctx,'MyCursor',128,50,35,color);
 const composition=compose(LAYOUTS[s.layout],size,{copyHeightRatio:.36,deviceWidthRatio:.84});
 const r=composition.devices[0].frame;
 // Goldie's compose() owns the device geometry; a native-canvas adapter draws
 // existing real, already-bezelled web-app captures, without a simulator.
 const headlineSize=h===1920?92:78;let y=h===1920?155:145;
 for(const line of s.headline){text(ctx,line,w/2,y,headlineSize,color,800,'center');y+=headlineSize*1.02;}
 ctx.font='400 35px Instrument';const sublines=wrap(ctx,s.sub,850);y+=25;for(const line of sublines){text(ctx,line,w/2,y,35,s.dark?'#b8c6bd':'#4c5a51',400,'center','Instrument');y+=46;}
 // Keep the composed device below all copy and above the offer strip.
 const top=Math.max(r.top,y+40);const maxH=h-top-145;const scale=Math.min(r.height,maxH)/r.height;
 const dr={left:w/2-r.width*scale/2,top,width:r.width*scale,height:r.height*scale};device(ctx,shots[s.image],dr,composition.devices[0].rotate);
 ctx.fillStyle=mint;ctx.beginPath();ctx.roundRect(60,h-104,w-120,58,29);ctx.fill();text(ctx,'All features free during beta',w/2,h-94,29,ink,700,'center','Instrument');
 fs.writeFileSync(path.join(out,`${s.id}-${size.label}.png`),can.toBuffer('image/png'));
}
for(const [w,h,name] of [[1920,1080,'launch-wide'],[1080,1080,'launch-square']]){
 const can=createCanvas(w,h),ctx=can.getContext('2d');ground(ctx,w,h);
 ctx.drawImage(logo,70,60,58,58);text(ctx,'MyCursor',145,64,43);
 if(w>h){text(ctx,'Leave the mouse',95,245,126);text(ctx,'at home.',95,377,126,green);text(ctx,'Your phone is already the control you need.',100,555,38,ink,400,'left','Instrument');device(ctx,shots.pad,{left:1230,top:170,width:330,height:681},-10);device(ctx,shots.present,{left:1490,top:250,width:310,height:640},9);text(ctx,'All features. Free during beta.',100,730,46);text(ctx,'Windows 10/11 · iPhone & Android',100,800,30,'#4c5a51',400,'left','Instrument');text(ctx,'gacaca6.github.io/MyCursor',100,940,30,green,600,'left','Instrument');}
 else{text(ctx,'Leave the mouse',w/2,160,90,ink,800,'center');text(ctx,'at home.',w/2,257,90,green,800,'center');device(ctx,shots.pad,{left:252,top:400,width:230,height:475},-10);device(ctx,shots.present,{left:590,top:415,width:230,height:475},10);text(ctx,'All features. Free during beta.',w/2,950,40,ink,700,'center','Instrument');}
 fs.writeFileSync(path.join(out,`${name}.png`),can.toBuffer('image/png'));
}
fs.writeFileSync(path.join(out,'manifest.json'),JSON.stringify({renderer:'Goldie compose() + native canvas web-capture adapter',scenes,outputs:fs.readdirSync(out).filter(f=>f.endsWith('.png'))},null,2));
console.log(`Rendered ${fs.readdirSync(out).filter(f=>f.endsWith('.png')).length} graphics with Goldie geometry.`);
