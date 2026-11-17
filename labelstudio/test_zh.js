/**
 * 用 jsdom 验证 ls-zh.user.js 的运行时行为。
 *
 * 只测「逻辑」，不测「词典是否翻译得准」—— 后者靠 sourcemap 覆盖率脚本。
 * 重点验证几件改坏了会直接把页面搞崩的事：
 *   1. 精确匹配 / 去标点容错匹配
 *   2. contenteditable 内不翻（否则会干扰标注员正在编辑的内容）
 *   3. showLabels 的三种情形（新用户写入 / 保留其他设置 / 尊重用户手动关闭）
 *   4. 单节点熔断，防止跟 React 反复拉锯导致页面疯狂重绘
 *   5. ?nozh=1 逃生通道
 *
 * 注意：document.body.textContent 会把内联 <script> 的源码也算进去，
 * 所以取文本时必须先摘掉 script 标签，否则断言全部失真。
 */
const fs = require('fs');
const path = require('path');
const { JSDOM } = require('jsdom');

const SRC = path.resolve(__dirname, 'ls-zh.user.js');
const code = fs.readFileSync(SRC, 'utf8');

let pass = 0;
let fail = 0;

function check(name, ok, detail) {
  if (ok) { pass += 1; console.log(`  [OK]   ${name}`); }
  else { fail += 1; console.log(`  [FAIL] ${name}` + (detail ? `  -> ${detail}` : '')); }
}

/** 取 body 的可见文本，排除 <script> 自身内容 */
function bodyText(win) {
  const clone = win.document.body.cloneNode(true);
  clone.querySelectorAll('script').forEach((s) => s.remove());
  return clone.textContent;
}

const KEY = 'labelStudio:settings';
const DONE = 'lsZhLabelsFixed';

function run(setup, opts = {}) {
  const dom = new JSDOM('<!doctype html><html><head><title>Label Studio</title></head>'
    + '<body></body></html>', {
    runScripts: 'dangerously',
    url: opts.url || 'http://127.0.0.1:8080/projects/',
    pretendToBeVisual: true,
  });
  const { window } = dom;
  if (!window.MutationObserver) {
    window.MutationObserver = class {
      observe() {}
      disconnect() {}
    };
  }
  if (setup) setup(window);
  const script = window.document.createElement('script');
  script.textContent = code;
  window.document.body.appendChild(script);
  return window;
}

/**
 * 预置成「已经跑过一次」的状态，让 boot() 跳过刷新分支、真正执行扫描。
 * 不预置的话 boot() 会因为首次修正 showLabels 而 reload 并 return。
 */
function asReturningUser(win, settings = {}) {
  win.localStorage.setItem(KEY, JSON.stringify({ showLabels: true, ...settings }));
  win.localStorage.setItem(DONE, '1');
}

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

(async () => {
  console.log('='.repeat(66));
  console.log('ls-zh.user.js 运行时验证（jsdom）');
  console.log('='.repeat(66));

  // ---- 1. 文本节点翻译
  console.log('\n[1] 文本节点翻译');
  {
    const w = run((win) => {
      asReturningUser(win);
      win.document.body.innerHTML =
        '<div><span>Save</span><button>Delete</button><p>Hello world</p></div>';
    });
    const t = bodyText(w);
    check('Save -> 保存', t.includes('保存'), t.slice(0, 80));
    check('Delete -> 删除', t.includes('删除'), t.slice(0, 80));
    check('未收录的原文保持不动', t.includes('Hello world'), t.slice(0, 80));
  }

  // ---- 2. 去标点容错匹配
  console.log('\n[2] 带标点的文案（容错匹配）');
  {
    const w = run((win) => {
      asReturningUser(win);
      win.document.body.innerHTML =
        '<div><span>Saved!</span><span>Total:</span><i>Preview</i></div>';
    });
    const t = bodyText(w);
    check('Saved! -> 已保存!（保留感叹号）', t.includes('已保存!'), t.slice(0, 80));
    // 只替换正文、原样保留标点：所以是「总计:」而不是「总计：」
    check('Total: -> 总计:（保留原标点，不擅自改全角）', t.includes('总计:'), t.slice(0, 80));
    check('Preview -> 预览', t.includes('预览'), t.slice(0, 80));
  }

  // ---- 3. contenteditable 跳过
  console.log('\n[3] 正在编辑的内容不翻');
  {
    const w = run((win) => {
      asReturningUser(win);
      win.document.body.innerHTML =
        '<div contenteditable="true"><span>Save</span></div>';
    });
    const t = bodyText(w);
    check('contenteditable 内的 Save 保持原样', t.includes('Save'), t.slice(0, 80));
  }

  // ---- 4. 属性翻译
  console.log('\n[4] title / placeholder / alt 属性');
  {
    const w = run((win) => {
      asReturningUser(win);
      win.document.body.innerHTML =
        '<input title="Play" placeholder="Search"><img alt="Video">';
  });
    const d = w.document;
    check('title=Play -> 播放', d.querySelector('input').getAttribute('title') === '播放',
      d.querySelector('input').getAttribute('title'));
    check('placeholder=Search -> 搜索',
      d.querySelector('input').getAttribute('placeholder') === '搜索',
      d.querySelector('input').getAttribute('placeholder'));
    check('alt=Video -> 视频', d.querySelector('img').getAttribute('alt') === '视频',
      d.querySelector('img').getAttribute('alt'));
  }

  // ---- 5. showLabels 三种情形
  console.log('\n[5] 自动开启「显示区域标签」（showLabels）');

  {
    const w = run((win) => {
      win.localStorage.removeItem(KEY);
      win.localStorage.removeItem(DONE);
    });
    const raw = w.localStorage.getItem(KEY);
    check('新用户：写入 showLabels=true', raw && JSON.parse(raw).showLabels === true,
      String(raw));
  }
  {
    const w = run((win) => {
      win.localStorage.setItem(KEY, JSON.stringify({ enableHotkeys: false, foo: 1 }));
      win.localStorage.removeItem(DONE);
    });
    const s = JSON.parse(w.localStorage.getItem(KEY));
    check('已有设置：保留 enableHotkeys', s.enableHotkeys === false, JSON.stringify(s));
    check('已有设置：保留 foo', s.foo === 1, JSON.stringify(s));
    check('已有设置：补上 showLabels=true', s.showLabels === true, JSON.stringify(s));
  }
  {
    // 模拟：我们已经修正过一次(DONE=1)，之后用户在设置里手动关掉了
    const w = run((win) => {
      win.localStorage.setItem(KEY, JSON.stringify({ showLabels: false }));
      win.localStorage.setItem(DONE, '1');
    });
    const s = JSON.parse(w.localStorage.getItem(KEY));
    check('用户手动关闭后：保持 false，不强制改回', s.showLabels === false,
      JSON.stringify(s));
  }

  // ---- 6. 熔断：同一节点反复改不会无限翻译
  console.log('\n[6] 单节点熔断（防止与 React 拉锯）');
  {
    const w = run((win) => {
      asReturningUser(win);
      win.document.body.innerHTML = '<div><span>Save</span></div>';
    });
    const node = w.document.querySelector('span').firstChild;
    // 直接改同一个文本节点的值，模拟 React 每次重渲染都改回英文
    for (let i = 0; i < 10; i += 1) {
      node.nodeValue = 'Save';
      await sleep(200); // 等过防抖(120ms)让 flush 跑完
    }
    check('翻译次数封顶后不再篡改该节点', node.nodeValue === 'Save', node.nodeValue);
  }

  // ---- 7. 逃生通道
  console.log('\n[7] ?nozh=1 强制英文');
  {
    const w = run((win) => {
      win.localStorage.removeItem('lsZhDisabled');
    }, { url: 'http://127.0.0.1:8080/projects/?nozh=1' });
    check('写入 lsZhDisabled=1', w.localStorage.getItem('lsZhDisabled') === '1',
      String(w.localStorage.getItem('lsZhDisabled')));
  }

  console.log('\n' + '='.repeat(66));
  console.log(`结果: ${pass} 通过, ${fail} 失败`);
  console.log('='.repeat(66));
  process.exit(fail ? 1 : 0);
})();
