// End-to-end smoke test for a real packaged UE Pixel Streaming session.
// It sends one prediction and one focus request through the browser bridge and
// requires successful acknowledgements from PredictionSceneBridge in UE.
const fs = require('fs');
const os = require('os');
const path = require('path');
const {spawn} = require('child_process');
const WS = require(process.env.AGENT_WS_MODULE || 'ws');

const sleep = ms => new Promise(resolve => setTimeout(resolve, ms));
let chrome;
let socket;

(async () => {
  const profile = fs.mkdtempSync(path.join(os.tmpdir(), 'chebaling-prediction-live-'));
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
  let streamStatus = '';
  for (let i = 0; i < 150; i++) {
    streamStatus = await evaluate('document.querySelector("#twin-status")?.textContent?.trim() || ""');
    if (streamStatus === '画面已连接') break;
    await sleep(1000);
  }
  if (streamStatus !== '画面已连接') throw new Error(`Pixel Streaming did not connect: ${streamStatus}`);

  if (process.env.AGENT_ENTER_SCENE === '1') {
    const rect = await evaluate(`(() => {
      const value = document.querySelector('#twin-frame')?.getBoundingClientRect();
      return value ? {x:value.x, y:value.y, width:value.width, height:value.height} : null;
    })()`);
    if (!rect) throw new Error('Pixel Streaming iframe was unavailable.');
    const x = rect.x + rect.width * 0.5;
    const y = rect.y + rect.height * 0.89;
    for (let attempt = 0; attempt < 3; attempt++) {
      await call('Input.dispatchMouseEvent', {type:'mouseMoved', x, y});
      await call('Input.dispatchMouseEvent', {type:'mousePressed', x, y, button:'left', clickCount:1});
      await call('Input.dispatchMouseEvent', {type:'mouseReleased', x, y, button:'left', clickCount:1});
      await sleep(500);
    }
    await sleep(8000);
  }


  await evaluate(`(() => {
    window.__ueControlStatuses = [];
    window.addEventListener('message', event => {
      if (event.data?.channel === 'chebaling.player.control-status') {
        window.__ueControlStatuses.push(event.data);
      }
    });
    return true;
  })()`);

  const targetId = process.env.AGENT_TEST_TREE_ID || '0101046';
  const applyAction = {
    type: 'apply_prediction', target_id: targetId, species: '端到端测试树种', year: 2030,
    dbh_m: 0.3, tree_height_m: 8, crown_diameter_ns_m: 3,
    crown_diameter_ew_m: 3, crown_volume_m3: 20, focus: true,
  };
  const send = action => evaluate(`(() => {
    const frame = document.querySelector('#twin-frame');
    if (!frame?.contentWindow) return false;
    frame.contentWindow.postMessage({channel:'chebaling.portal.control',version:1,actions:[${JSON.stringify(action)}]}, '*');
    return true;
  })()`);
  if (!await send(applyAction)) throw new Error('Pixel Streaming iframe was unavailable.');

  const waitForExecuted = async action => {
    let latestStatuses = [];
    for (let i = 0; i < 30; i++) {
      const statuses = await evaluate('window.__ueControlStatuses || []');
      latestStatuses = statuses;
      const error = statuses.find(item => item.action === action && item.target_id === targetId && item.status === 'error');
      if (error) throw new Error(`${action} failed in UE: ${error.message || 'unknown error'}`);
      const success = statuses.find(item => item.action === action && item.target_id === targetId && item.status === 'executed');
      if (success) return success;
      await sleep(1000);
    }
    throw new Error(`No executed acknowledgement for ${action} ${targetId}. statuses=${JSON.stringify(latestStatuses)}`);
  };

  const applied = await waitForExecuted('apply_prediction');
  await send({type: 'focus_prediction', target_id: targetId});
  const focused = await waitForExecuted('focus_prediction');
  if (process.env.AGENT_SCREENSHOT) {
    await sleep(1500);
    const shot = await call('Page.captureScreenshot', {
      format: 'png',
      captureBeyondViewport: false,
    });
    fs.writeFileSync(process.env.AGENT_SCREENSHOT, Buffer.from(shot.result.data, 'base64'));
    console.log('Screenshot: ' + process.env.AGENT_SCREENSHOT);
    if (process.env.AGENT_VERIFY_MOVEMENT === '1') {
      const rect = await evaluate(`(() => {
        const value = document.querySelector('#twin-frame')?.getBoundingClientRect();
        return value ? {x:value.x, y:value.y, width:value.width, height:value.height} : null;
      })()`);
      const x = rect.x + rect.width * 0.5;
      const y = rect.y + rect.height * 0.5;
      await call('Input.dispatchMouseEvent', {type:'mousePressed', x, y, button:'left', clickCount:1});
      await call('Input.dispatchMouseEvent', {type:'mouseReleased', x, y, button:'left', clickCount:1});
      await call('Input.dispatchKeyEvent', {type:'keyDown', code:'KeyW', key:'w', windowsVirtualKeyCode:87});
      await sleep(1200);
      await call('Input.dispatchKeyEvent', {type:'keyUp', code:'KeyW', key:'w', windowsVirtualKeyCode:87});
      await sleep(1000);
      const moved = await call('Page.captureScreenshot', {format:'png', captureBeyondViewport:false});
      fs.writeFileSync(process.env.AGENT_SCREENSHOT.replace(/\.png$/i, '-moved.png'), Buffer.from(moved.result.data, 'base64'));
    }
  }
  console.log(`PASS: UE applied and focused prediction for ${targetId}`);
  console.log(JSON.stringify({applied, focused}));
  await call('Browser.close');
})().catch(error => {
  console.error(error);
  process.exitCode = 1;
}).finally(() => {
  if (socket) socket.close();
  if (chrome) chrome.kill();
});
