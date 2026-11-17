/**
 * 端到端冒烟测试：拉取本地 Label Studio 真实登录页，用 jsdom 执行页面里的
 * 内联中文脚本，断言界面上的英文确实变成了中文。
 *
 * 这一步是必要的：node 的语法检查只能证明脚本「能解析」，
 * 证明不了「注入到 Django 模板后仍然有效」——
 * 比如注入位置错了、被 {% raw %} 转义、或 </script> 把 HTML 截断，
 * 这些都只有真跑一遍页面才暴露得出来。
 */
const { JSDOM, VirtualConsole } = require('jsdom');

const URL = process.env.LS_URL || 'http://127.0.0.1:8080';
const PAGE = `${URL}/user/login/`;

// 期望「原文 -> 译文」：挑登录页上一定会出现、且不太可能误伤的词
const EXPECT = [
  ['Email', '邮箱'],
  ['Password', '密码'],
  ['Sign in', '登录'],
];

let pass = 0;
let fail = 0;

function check(name, ok, detail) {
  if (ok) { pass += 1; console.log(`  [OK]   ${name}`); }
  else { fail += 1; console.log(`  [FAIL] ${name}` + (detail ? `  -> ${detail}` : '')); }
}

(async () => {
  console.log('='.repeat(66));
  console.log('中文界面端到端冒烟测试');
  console.log('='.repeat(66));
  console.log(`目标: ${PAGE}\n`);

  const res = await fetch(PAGE);
  const html = await res.text();
  check('登录页可访问', res.status === 200, `HTTP ${res.status}`);
  check('页面含内联中文脚本标记', html.includes('ls-zh.user.js 内联版'));
  check('页面 </body> 仍存在且未被破坏', html.includes('</body>'));

  const errors = [];
  const vc = new VirtualConsole();
  vc.on('jsdomError', (e) => errors.push(e.message));
  vc.on('error', (m) => errors.push(String(m)));

  const dom = new JSDOM(html, {
    url: PAGE,
    runScripts: 'dangerously',
    pretendToBeVisual: true,
    virtualConsole: vc,
  });

  // 等一拍，让 MutationObserver 的防抖(120ms)跑完
  await new Promise((r) => setTimeout(r, 600));

  const { window } = dom;
  const text = window.document.body.textContent;
  console.log('\n[登录页文案]');
  for (const [en, zh] of EXPECT) {
    check(`${en} -> ${zh}`, text.includes(zh), `页面文本含 "${en}" 但没翻成 "${zh}"`);
  }

  // jsdom 缺能力导致的报错不算脚本缺陷，单独归类，避免掩盖真实错误
  const KNOWN = [
    /navigation to another Document/,   // location.reload()：真实浏览器可用
    /fetch is not defined/,             // 页面自带脚本用 fetch，jsdom 未实现
  ];
  const real = errors.filter((e) => !KNOWN.some((re) => re.test(e)));
  if (errors.length !== real.length) {
    console.log(`\n  [提示] 忽略 ${errors.length - real.length} 条 jsdom 环境限制报错`
      + '（reload / fetch），真实浏览器中不存在');
  }
  check('脚本执行期间无真实 JS 错误', real.length === 0, real.slice(0, 2).join(' | '));
  check('防重复标记已置位', window.__lsZhLoaded === true);

  console.log('\n' + '='.repeat(66));
  console.log(`结果: ${pass} 通过, ${fail} 失败`);
  console.log('='.repeat(66));
  process.exit(fail ? 1 : 0);
})();
