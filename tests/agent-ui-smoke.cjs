// Browser-only contract test. Uses mock API/SSE, never calls a real model or UE.
// node tests/agent-ui-smoke.cjs (requires ws; AGENT_WS_MODULE may supply its path)
const http = require('http');
const fs = require('fs');
const path = require('path');
const os = require('os');
const {spawn} = require('child_process');
const WS = require(process.env.AGENT_WS_MODULE || 'ws');
const assert = require('assert/strict');
const frontend = path.resolve(__dirname, '../frontend');
const sleep = ms => new Promise(resolve => setTimeout(resolve, ms));
let approved = false, ws, chrome;
const server = http.createServer((req, res) => {
  const send = data => {res.setHeader('Content-Type', 'application/json');res.end(JSON.stringify(data));};
  const url = new URL(req.url, 'http://localhost');
  if (url.pathname === '/') {res.setHeader('Content-Type', 'text/html; charset=utf-8');res.end(fs.readFileSync(path.join(frontend, 'platform.html')));return;}
  if (url.pathname.startsWith('/portal-assets/')) {
    const file = path.join(frontend, path.basename(url.pathname));
    if (!fs.existsSync(file)) {res.statusCode=404;res.end();return;}
    res.setHeader('Content-Type', file.endsWith('.css')?'text/css':file.endsWith('.js')?'text/javascript':'image/svg+xml');
    res.end(fs.readFileSync(file));return;
  }
  if (url.pathname === '/platform/config') return send({platform_name:'Agent test',pixel_streaming_auto_connect:false});
  if (url.pathname === '/platform/status') return send({data_source:{mode:'excel',file_count:8}});
  if (url.pathname === '/platform/warmup') return send({accepted:true});
  if (url.pathname === '/agent/sessions') {approved=false;res.statusCode=202;return send({id:'a'.repeat(32),token:'fixture'});}
  if (url.pathname.endsWith('/approval')) {approved=true;res.statusCode=202;return send({accepted:true});}
  if (url.pathname.endsWith('/events')) {
    assert.equal(req.headers.authorization, 'Bearer fixture');
    res.setHeader('Content-Type','text/event-stream');
    const event = approved ? {id:2,kind:'session.completed',message:'任务已完成'} : {id:1,kind:'approval.requested',message:'等待工具执行审批'};
    res.end('id: '+event.id+'\nevent: trace\ndata: '+JSON.stringify(event)+'\n\n');return;
  }
  if (url.pathname.startsWith('/agent/sessions/')) return send({id:'a'.repeat(32),status:approved?'completed':'awaiting_approval',
    final:approved?{answer:'测试完成',artifacts:[{title:'预测数据',filename:'dbh_predictions_2030_random_50.xlsx',mime:'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',content_base64:'UEsDBAoAAAAA'}],
      ue_actions:[{type:'apply_prediction',target_id:'0107029',species:'绒毛润楠',year:2030,dbh_m:0.3,tree_height_m:8,crown_diameter_ns_m:3,crown_diameter_ew_m:3,crown_volume_m3:20,focus:true}]}:null,
    approval:approved?null:{digest:'b'.repeat(64),summary:'继续执行这项受控操作需要你的确认。'}});
  res.statusCode=404;res.end();
});
(async()=>{
  await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));
  const profile = fs.mkdtempSync(path.join(os.tmpdir(),'agent-ui-'));
  chrome = spawn(process.env.AGENT_CHROME || 'C:/Program Files/Google/Chrome/Application/chrome.exe',
    ['--headless=new','--remote-debugging-port=0','--user-data-dir='+profile,'--window-size=1600,1000','about:blank'],{windowsHide:true,stdio:'ignore'});
  chrome.on('error', e => {throw e;});
  const active = path.join(profile,'DevToolsActivePort');
  for(let i=0;i<100&&!fs.existsSync(active);i++) await sleep(100);
  const port=fs.readFileSync(active,'utf8').split('\n')[0];
  const pages=await (await fetch('http://127.0.0.1:'+port+'/json/list')).json();
  ws=new WS(pages.find(p=>p.type==='page').webSocketDebuggerUrl);
  await new Promise(resolve=>ws.once('open',resolve));
  let id=0;const pending=new Map();
  ws.on('message', raw=>{const m=JSON.parse(raw);if(pending.has(m.id)){pending.get(m.id)(m);pending.delete(m.id);}});
  const call=(method,params={})=>new Promise(resolve=>{pending.set(++id,resolve);ws.send(JSON.stringify({id,method,params}));});
  const evaluate=async expression=>{const r=await call('Runtime.evaluate',{expression,returnByValue:true,awaitPromise:true});if(r.result.exceptionDetails)throw Error(JSON.stringify(r));return r.result.result.value;};
  await call('Page.navigate',{url:'http://127.0.0.1:'+server.address().port});
  for(let i=0;i<100;i++){if(await evaluate('document.readyState === "complete" && !!window.Agent')) break;await sleep(50);}
  const before=await evaluate('document.querySelector(".twin-panel").getBoundingClientRect().height');
  assert.equal(await evaluate('document.querySelector(".agent-task-panel") === null'),true);
  await evaluate('sendMessage("请创建一个工作区文件")');
  assert.equal(await evaluate('document.querySelectorAll(".inline-approval button").length'),2);
  await evaluate('document.querySelector(".inline-approval button").click()');
  for(let i=0;i<100;i++){if(await evaluate('!Agent.busy'))break;await sleep(50);}
  assert.equal(await evaluate('document.querySelector(".twin-panel").getBoundingClientRect().height'),before);
  assert.equal(await evaluate('document.querySelector("#chat-messages").textContent.includes("测试完成")'),true);
  assert.equal(await evaluate('document.querySelector(`a[download="dbh_predictions_2030_random_50.xlsx"]`) !== null'),true);
  assert.equal(await evaluate('document.querySelector(".prediction-tree-list-items button")?.dataset.treeId'), '0107029');
  assert.equal(await evaluate('document.querySelector(".prediction-tree-list-items button")?.disabled'), true);
  console.log('PASS: inline progress, safe approval, final response, stable UE size');
  await call('Browser.close');ws.close();server.close();
})().catch(error=>{console.error(error);if(ws)ws.close();if(chrome)chrome.kill();server.close();process.exitCode=1;});
