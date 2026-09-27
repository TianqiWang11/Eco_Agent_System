// Live smoke test for the locally running portal and UE Pixel Streaming stack.
// This test does not mock the API, signalling server, WebRTC stream, or UE.
const fs = require('fs');
const os = require('os');
const path = require('path');
const {spawn} = require('child_process');
const WS = require(process.env.AGENT_WS_MODULE || 'ws');

const sleep = ms => new Promise(resolve => setTimeout(resolve, ms));
let chrome;
let socket;

(async () => {
  const profile = fs.mkdtempSync(path.join(os.tmpdir(), 'chebaling-live-'));
  chrome = spawn(process.env.AGENT_CHROME || 'C:/Program Files/Google/Chrome/Application/chrome.exe', [
    '--headless=new',
    '--autoplay-policy=no-user-gesture-required',
    '--remote-debugging-port=0',
    '--user-data-dir=' + profile,
    '--window-size=1600,1000',
    'about:blank',
  ], {windowsHide: true, stdio: 'ignore'});

  const activePortFile = path.join(profile, 'DevToolsActivePort');
  for (let i = 0; i < 150 && !fs.existsSync(activePortFile); i++) await sleep(100);
  if (!fs.existsSync(activePortFile)) throw new Error('Chrome DevTools did not start.');

  const port = fs.readFileSync(activePortFile, 'utf8').split('\n')[0];
  const pages = await (await fetch(`http://127.0.0.1:${port}/json/list`)).json();
  socket = new WS(pages.find(page => page.type === 'page').webSocketDebuggerUrl);
  await new Promise(resolve => socket.once('open', resolve));

  let id = 0;
  const pending = new Map();
  socket.on('message', raw => {
    const message = JSON.parse(raw);
    if (pending.has(message.id)) {
      pending.get(message.id)(message);
      pending.delete(message.id);
    }
  });
  const call = (method, params = {}) => new Promise(resolve => {
    pending.set(++id, resolve);
    socket.send(JSON.stringify({id, method, params}));
  });
  const evaluate = async expression => {
    const response = await call('Runtime.evaluate', {expression, returnByValue: true, awaitPromise: true});
    if (response.result.exceptionDetails) throw new Error(JSON.stringify(response.result.exceptionDetails));
    return response.result.result.value;
  };

  await call('Page.navigate', {url: process.env.AGENT_PORTAL_URL || 'http://127.0.0.1:8000'});
  let status = '';
  for (let i = 0; i < 120; i++) {
    status = await evaluate('document.querySelector("#twin-status")?.textContent?.trim() || ""');
    if (status === '画面已连接') break;
    await sleep(1000);
  }
  const frameUrl = await evaluate('document.querySelector("#twin-frame")?.src || ""');
  if (status !== '画面已连接') throw new Error(`Pixel Streaming did not produce advancing video frames. status=${status} frame=${frameUrl}`);
  console.log(`PASS: live UE video frames reached the portal (${frameUrl})`);
  await call('Browser.close');
})().catch(error => {
  console.error(error);
  process.exitCode = 1;
}).finally(() => {
  if (socket) socket.close();
  if (chrome) chrome.kill();
});
