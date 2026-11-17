/**
 * 上传助手的冒烟测试。
 *
 * 为什么必须真跑一遍：语法检查只能证明脚本能解析，证明不了
 * 「拖拽事件能收到文件」「CSRF 头带上了」「打到正确的接口」——
 * 这几处任何一处错，标注员看到的都是「点了没反应」。
 *
 * 用法：node labelstudio/smoke_tools.js
 */
const fs = require('fs');
const path = require('path');
const { JSDOM, VirtualConsole } = require('jsdom');

const SRC = path.join(__dirname, 'ls-tools.js');
const PAGE_URL = 'http://ich.8.160.123.92.nip.io/projects/1/data';

let pass = 0, fail = 0;
function check(name, ok, detail) {
  if (ok) { pass++; console.log(`  [OK]   ${name}`); }
  else { fail++; console.log(`  [FAIL] ${name}` + (detail ? `  -> ${detail}` : '')); }
}

(async () => {
  console.log('='.repeat(66));
  console.log('上传助手冒烟测试');
  console.log('='.repeat(66));

  const code = fs.readFileSync(SRC, 'utf8');
  check('脚本存在且非空', code.length > 2000, `${code.length} 字节`);

  const calls = [];
  const vc = new VirtualConsole();
  const jsErrors = [];
  vc.on('jsdomError', (e) => jsErrors.push(e.message));

  const dom = new JSDOM('<!doctype html><html><head></head><body></body></html>', {
    url: PAGE_URL,
    runScripts: 'dangerously',
    pretendToBeVisual: true,
    virtualConsole: vc,
  });
  const { window } = dom;

  // --- 打桩：网络与存储
  window.document.cookie = 'csrftoken=TESTCSRF123';
  const uploaded = [];
  window.fetch = function (url, opts) {
    const rec = { url: String(url), method: (opts && opts.method) || 'GET',
                  csrf: (opts && opts.headers && opts.headers['X-CSRFToken']) || null,
                  files: [] };
    if (opts && opts.body && typeof opts.body.forEach === 'function') {
      try { opts.body.forEach((v, k) => { if (k === 'file') rec.files.push(v.name); }); } catch (e) {}
    }
    calls.push(rec);
    if (rec.method === 'POST') {
      uploaded.push(rec);
      return Promise.resolve({ ok: true, status: 201, text: () => Promise.resolve('{"task_count":1}') });
    }
    return Promise.resolve({
      ok: true, status: 200,
      json: () => Promise.resolve({ results: [{ id: 1, title: '非遗视频' }] }),
      text: () => Promise.resolve(''),
    });
  };

  // --- 注入脚本
  const s = window.document.createElement('script');
  s.textContent = code;
  window.document.head.appendChild(s);

  // ---- 1. 按钮是否出现
  const fab = window.document.getElementById('lst-fab');
  check('注入常驻按钮 #lst-fab', !!fab);
  check('按钮文案含「上传视频」', !!fab && fab.textContent.includes('上传视频'),
        fab ? fab.textContent : '按钮不存在');
  check('进度面板存在但默认隐藏',
        !!window.document.getElementById('lst-panel') &&
        !window.document.getElementById('lst-panel').classList.contains('show'));
  check('拖拽遮罩存在', !!window.document.getElementById('lst-drop'));

  // 位置：固定在右下角，任何页面都不会被内容盖住
  const cssText = Array.from(window.document.querySelectorAll('style')).map((e) => e.textContent).join('');
  check('按钮定位为 fixed', /#lst-fab\{[^}]*position:fixed/.test(cssText.replace(/\n/g, '')));
  check('按钮层级足够高', /#lst-fab\{[^}]*z-index:2147/.test(cssText.replace(/\n/g, '')));

  // ---- 2. 拖一个视频进来，是否真的发起上传
  function makeFile(name, type) {
    return new window.File([new Uint8Array([0, 1, 2, 3])], name, { type });
  }
  const files = [makeFile('测试片段.mp4', 'video/mp4'), makeFile('说明.txt', 'text/plain')];
  const ev = new window.Event('drop', { bubbles: true });
  Object.defineProperty(ev, 'dataTransfer', { value: { files, types: ['Files'] } });
  window.dispatchEvent(ev);

  await new Promise((r) => setTimeout(r, 400));

  check('拖拽后发起了 POST 上传', uploaded.length === 1,
        `实际 ${uploaded.length} 次；调用记录 ${JSON.stringify(calls.map((c) => c.url))}`);
  if (uploaded.length) {
    const u = uploaded[0];
    check('打到 /api/projects/1/import', u.url === '/api/projects/1/import', u.url);
    check('带上了 X-CSRFToken', u.csrf === 'TESTCSRF123', String(u.csrf));
    check('只传视频，非视频被跳过',
          u.files.length === 1 && u.files[0] === '测试片段.mp4', JSON.stringify(u.files));
  }

  // ---- 3. 进度UI
  const panel = window.document.getElementById('lst-panel');
  check('上传后进度面板自动展开', panel.classList.contains('show'));
  const rows = window.document.querySelectorAll('#lst-list .row');
  check('每个文件一行', rows.length === 1, `${rows.length} 行`);
  check('成功状态已标记', /已导入/.test(panel.textContent), panel.textContent.slice(0, 80));

  // ---- 4. 真实 JS 错误
  const KNOWN = [/navigation to another Document/, /Not implemented: navigation/];
  const real = jsErrors.filter((e) => !KNOWN.some((re) => re.test(e)));
  check('执行期间无真实 JS 错误', real.length === 0, real.slice(0, 2).join(' | '));

  console.log('\n' + '='.repeat(66));
  console.log(`结果: ${pass} 通过, ${fail} 失败`);
  console.log('='.repeat(66));
  process.exit(fail ? 1 : 0);
})();
