import fs from 'node:fs';
const CDP='9223', BASE='http://127.0.0.1:8017';
const sleep=ms=>new Promise(r=>setTimeout(r,ms));
let page;
try{page=await(await fetch(`http://127.0.0.1:${CDP}/json/new?about:blank`,{method:'PUT'})).json();}catch{page=await(await fetch(`http://127.0.0.1:${CDP}/json/new?about:blank`)).json();}
const ws=new WebSocket(page.webSocketDebuggerUrl);
await new Promise(r=>ws.addEventListener('open',r));
let id=0;const pend=new Map();const events=[];
ws.addEventListener('message',ev=>{const m=JSON.parse(ev.data);if(m.id&&pend.has(m.id)){const p=pend.get(m.id);pend.delete(m.id);m.error?p.rej(new Error(m.error.message)):p.res(m.result);}else if(m.method)events.push(m);});
const send=(m,p={})=>new Promise((res,rej)=>{const i=++id;pend.set(i,{res,rej});ws.send(JSON.stringify({id:i,method:m,params:p}));});
const ev=async e=>{const r=await send('Runtime.evaluate',{expression:e,returnByValue:true,awaitPromise:true});if(r.exceptionDetails)return{JS_ERROR:r.exceptionDetails.exception?.description};return r.result?.value;};
const shot=async n=>{const r=await send('Page.captureScreenshot',{format:'png'});fs.writeFileSync(`out/shots/${n}.png`,Buffer.from(r.data,'base64'));console.log('shot',n);};
await send('Runtime.enable');await send('Page.enable');await send('Network.enable');await send('Network.setCacheDisabled',{cacheDisabled:true});
await send('Emulation.setDeviceMetricsOverride',{width:1440,height:1000,deviceScaleFactor:1,mobile:false});
await send('Page.navigate',{url:BASE+'/?v='+Date.now()});
await sleep(2400);
await ev(`document.querySelector('#btn-start').click()`);await sleep(400);
await ev(`(async()=>{const b=await(await fetch('/api/sample/_qa_face.jpg?x='+Date.now())).blob();const f=new File([b],'qa.jpg',{type:'image/jpeg'});await pickSprite(f);})()`);
await sleep(800);
await ev(`document.querySelector('#eeg-samples .chip').click(); document.querySelector('#dna-samples .chip').click();`);
for(let i=0;i<24;i++){await sleep(250);if(await ev(`!document.querySelector('#btn-scan').disabled`))break;}
await ev(`document.querySelector('#btn-scan').click()`);
for(let i=0;i<26;i++){await sleep(600);if(await ev(`document.querySelector('#view-dossier').classList.contains('active')`))break;}
console.log('dossier',await ev(`document.querySelector('#view-dossier').classList.contains('active')`),'sprite',await ev(`!!(state.profile&&state.profile.avatar&&state.profile.avatar.sprite)`));
await ev(`document.querySelector('#btn-scene').click()`);await sleep(1600);
await shot('scene-mode');
console.log('scene',await ev(`JSON.stringify({hidden:document.querySelector('#scene').hidden,char:document.querySelector('#scene-char').src.slice(0,30),text:document.querySelector('#scene-text').textContent.slice(0,30),name:document.querySelector('#scene-name').textContent})`));
const errs=events.filter(e=>e.method==='Runtime.exceptionThrown').map(e=>e.params.exceptionDetails.exception?.description);
console.log('errors',errs.length,errs.slice(0,3));
ws.close();
