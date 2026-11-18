// Browser verification without npm dependencies or the user's browser profile.
import { spawn } from 'node:child_process';
import { mkdir, readFile, writeFile } from 'node:fs/promises';
import http from 'node:http';
import path from 'node:path';
import { pathToFileURL } from 'node:url';
import { randomUUID } from 'node:crypto';

const report = process.argv[2];
if (!report) throw new Error('Usage: node scripts/check-report.mjs <report.html>');
const chrome = process.env.VU_BROWSER || 'C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe';
const profile = path.resolve('.runtime', `browser-${randomUUID()}`);
const output = path.resolve('.impeccable', 'review');
await mkdir(profile, { recursive: true });
await mkdir(output, { recursive: true });
const browser = spawn(chrome, ['--headless', '--disable-gpu', '--no-first-run', '--no-default-browser-check', '--disable-background-networking', '--remote-debugging-port=0', `--user-data-dir=${profile}`, 'about:blank'], { windowsHide: true, stdio: 'ignore' });
const pause = ms => new Promise(resolve => setTimeout(resolve, ms));
let socket;
try {
  let port;
  for (let attempt = 0; attempt < 100; attempt++) {
    try { port = (await readFile(path.join(profile, 'DevToolsActivePort'), 'utf8')).split('\n')[0]; break; }
    catch { await pause(100); }
  }
  if (!port) throw new Error('Headless browser did not publish its debugging port.');
  const targets = await new Promise((resolve, reject) => {
    http.get(`http://127.0.0.1:${port}/json`, response => {
      let body = ''; response.on('data', part => body += part);
      response.on('end', () => { try { resolve(JSON.parse(body)); } catch (error) { reject(error); } });
    }).on('error', reject);
  });
  socket = new WebSocket(targets.find(target => target.type === 'page').webSocketDebuggerUrl);
  await new Promise((resolve, reject) => { socket.addEventListener('open', resolve, { once: true }); socket.addEventListener('error', reject, { once: true }); });
  let serial = 0;
  const waiting = new Map();
  const exceptions = [];
  socket.addEventListener('message', event => {
    const message = JSON.parse(event.data);
    if (message.method === 'Runtime.exceptionThrown') exceptions.push(message.params);
    if (waiting.has(message.id)) {
      const pending = waiting.get(message.id); waiting.delete(message.id);
      clearTimeout(pending.timer);
      message.error ? pending.reject(new Error(JSON.stringify(message.error))) : pending.resolve(message.result);
    }
  });
  function command(method, params = {}) {
    const id = ++serial;
    return new Promise((resolve, reject) => {
      const timer = setTimeout(() => { waiting.delete(id); reject(new Error(`Timed out: ${method}`)); }, 10000);
      waiting.set(id, { resolve, reject, timer }); socket.send(JSON.stringify({ id, method, params }));
    });
  }
  async function evaluate(expression) {
    const result = await command('Runtime.evaluate', { expression, returnByValue: true });
    if (result.exceptionDetails) throw new Error(JSON.stringify(result.exceptionDetails));
    return result.result.value;
  }
  await command('Page.enable'); await command('Runtime.enable');
  const checks = [];
  for (const viewport of [{ name: 'desktop', width: 1440, height: 1000 }, { name: 'mobile', width: 390, height: 844 }]) {
    await command('Emulation.setDeviceMetricsOverride', { width: viewport.width, height: viewport.height, deviceScaleFactor: 1, mobile: false });
    await command('Page.navigate', { url: pathToFileURL(path.resolve(report)).href });
    for (let attempt = 0; attempt < 50; attempt++) {
      if (await evaluate('document.readyState === "complete" && !!document.querySelector(".scenario")')) break;
      await pause(50);
    }
    const state = await evaluate(`(() => {
      const details = document.querySelector('details.scenario');
      details.querySelector('summary').click();
      const disclosureWorks = details.open;
      details.querySelector('summary').click();
      details.querySelector('summary').focus();
      const keyboardFocusable = document.activeElement.tagName === 'SUMMARY';
      document.activeElement.blur();
      return { viewport: innerWidth, documentWidth: document.documentElement.scrollWidth, scenarioCount: document.querySelectorAll('.scenario').length, disclosureWorks, keyboardFocusable, title: document.title };
    })()`);
    if (state.documentWidth > state.viewport || !state.disclosureWorks || !state.keyboardFocusable) throw new Error(`Report layout/interaction failure: ${JSON.stringify(state)}`);
    const metrics = await command('Page.getLayoutMetrics');
    const screenshot = await command('Page.captureScreenshot', { format: 'png', captureBeyondViewport: true, clip: { x: 0, y: 0, width: viewport.width, height: metrics.cssContentSize.height, scale: 1 } });
    const filename = path.join(output, `${viewport.name}.png`);
    await writeFile(filename, Buffer.from(screenshot.data, 'base64'));
    checks.push({ ...viewport, ...state, screenshot: filename });
  }
  if (exceptions.length) throw new Error(`Browser JavaScript errors: ${JSON.stringify(exceptions)}`);
  await writeFile(path.join(output, 'browser-checks.json'), JSON.stringify(checks, null, 2));
  console.log(JSON.stringify({ passed: true, checks }, null, 2));
  await command('Browser.close').catch(() => {});
} finally {
  socket?.close();
  if (browser.exitCode === null) {
    await Promise.race([new Promise(resolve => browser.once('exit', resolve)), pause(3000)]);
    if (browser.exitCode === null) browser.kill();
  }
}

