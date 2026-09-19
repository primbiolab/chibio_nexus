// Mini cliente CDP (Node ≥22, WebSocket global). Sin dependencias.
const { spawn } = require('child_process');
const fs = require('fs'), os = require('os'), path = require('path');

const CHROME = 'C:/Program Files/Google/Chrome/Application/chrome.exe';
const sleep = ms => new Promise(r => setTimeout(r, ms));

class Page {
  constructor(ws) {
    this.ws = ws; this.id = 0; this.pending = new Map(); this.handlers = {};
    this.reqs = []; this.logs = []; this.dialogs = [];
    ws.onmessage = ev => {
      const m = JSON.parse(ev.data);
      if (m.id && this.pending.has(m.id)) { const p = this.pending.get(m.id); this.pending.delete(m.id); m.error ? p.rej(new Error(JSON.stringify(m.error))) : p.res(m.result); }
      else if (m.method) this._event(m.method, m.params);
    };
  }
  send(method, params = {}) { const id = ++this.id; this.ws.send(JSON.stringify({ id, method, params })); return new Promise((res, rej) => this.pending.set(id, { res, rej })); }
  _event(method, p) {
    if (method === 'Network.requestWillBeSent') this.reqs.push({ id: p.requestId, method: p.request.method, url: p.request.url, t: Date.now() });
    else if (method === 'Network.responseReceived') { const r = this.reqs.find(x => x.id === p.requestId); if (r) r.status = p.response.status; }
    else if (method === 'Network.loadingFailed') { const r = this.reqs.find(x => x.id === p.requestId); if (r) r.failed = p.errorText; }
    else if (method === 'Runtime.consoleAPICalled' && ['error', 'warning'].includes(p.type)) this.logs.push(p.type + ': ' + p.args.map(a => a.value ?? a.description).join(' ').slice(0, 200));
    else if (method === 'Runtime.exceptionThrown') this.logs.push('EXC: ' + (p.exceptionDetails.exception?.description || p.exceptionDetails.text).slice(0, 200));
    else if (method === 'Page.javascriptDialogOpening') { this.dialogs.push(p.message); this.send('Page.handleJavaScriptDialog', { accept: this.dialogAccept !== false }); }
  }
  async ev(expr) {
    const r = await this.send('Runtime.evaluate', { expression: expr, returnByValue: true, awaitPromise: true });
    if (r.exceptionDetails) throw new Error('eval: ' + (r.exceptionDetails.exception?.description || r.exceptionDetails.text));
    return r.result.value;
  }
  async goto(url, wait = 1500) { await this.send('Page.navigate', { url }); await sleep(wait); }
  mark() { return this.reqs.length; }
  since(m, filter) { return this.reqs.slice(m).filter(r => !/getSysdata|\.(css|js|png|woff2?)(\?|$)|fonts\.|cdnjs/.test(r.url) && (!filter || filter.test(r.url))); }
  fmt(list) { return list.map(r => `${r.method} ${r.url.replace('http://127.0.0.1:5000', '')} → ${r.status ?? r.failed ?? '?'}`).join('\n      '); }
}

async function launch(port = 9333) {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'cdp-'));
  const proc = spawn(CHROME, ['--headless=new', '--remote-debugging-port=' + port, '--user-data-dir=' + dir, '--no-first-run', '--disable-gpu', '--window-size=1920,1080', 'about:blank'], { stdio: 'ignore' });
  let targets;
  for (let i = 0; i < 50; i++) { try { targets = await (await fetch(`http://127.0.0.1:${port}/json/list`)).json(); if (targets.length) break; } catch (e) {} await sleep(200); }
  const tgt = targets.find(t => t.type === 'page');
  const ws = new WebSocket(tgt.webSocketDebuggerUrl);
  await new Promise(r => (ws.onopen = r));
  const page = new Page(ws);
  for (const d of ['Page', 'Runtime', 'Network']) await page.send(d + '.enable');
  const newPage = async url => {
    const t = await (await fetch(`http://127.0.0.1:${port}/json/new?${encodeURIComponent(url)}`, { method: 'PUT' })).json();
    const w = new WebSocket(t.webSocketDebuggerUrl); await new Promise(r => (w.onopen = r));
    const p = new Page(w); for (const d of ['Page', 'Runtime', 'Network']) await p.send(d + '.enable'); return p;
  };
  const close = () => { try { ws.close(); } catch (e) {} proc.kill(); };
  return { page, newPage, close, sleep };
}
module.exports = { launch, sleep };
