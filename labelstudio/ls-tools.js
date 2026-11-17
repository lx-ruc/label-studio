// ==UserScript==
// @name         Label Studio 上传助手
// @namespace    ich-prelabel
// @version      1.0
// @description  在 Label Studio 任意页面注入常驻「上传视频」按钮与拖拽上传。社区版只在数据管理器有导入入口，标注视图里完全找不到。
// @match        http://ich.8.160.123.92.nip.io/*
// @match        http://8.160.123.92:8089/*
// @match        http://localhost:8080/*
// @match        http://127.0.0.1:8089/*
// @run-at       document-idle
// @grant        none
// ==/UserScript==
/* eslint-disable */

/**
 * 为什么需要这个：
 * Label Studio 的导入入口只在「项目 → 数据管理器」的右上角，一旦点进「标注」
 * 就变成全屏标注视图，那里没有任何导入按钮。标注员经常就卡在这一步。
 * 本脚本在所有页面右下角放一个常驻按钮，直接调 /api/projects/{id}/import 上传，
 * 并支持把文件拖进窗口任意位置。
 *
 * 认证走浏览器自己的 session + csrftoken，不需要 token，也不会多开账号。
 */
(function () {
  'use strict';
  if (window.__lsToolsLoaded) return;
  window.__lsToolsLoaded = true;

  var ACCEPT = '.mp4,.mov,.avi,.mkv,.webm,.m4v,.flv,.wmv';
  var VID_EXT = /\.(mp4|mov|avi|mkv|webm|m4v|flv|wmv|ts|mpg|mpeg)$/i;

  // 只在 Label Studio 自己的页面里跑（登录页也算，但那时没有项目，按钮会提示先去建项目）
  if (!/^\/(projects|user|organization|$)/.test(location.pathname) && location.pathname !== '/') return;
  // 登录/注册页不放按钮：还没登录，点了只会拿到 403
  if (/^\/user\/(login|signup)/.test(location.pathname)) return;

  // ---------------------------------------------------------------- 样式
  var css = document.createElement('style');
  css.textContent = [
    '#lst-fab{position:fixed;right:24px;bottom:24px;z-index:2147483000;display:flex;gap:8px;align-items:center;',
    '  background:#1D9E75;color:#fff;border:none;border-radius:28px;padding:12px 20px;font-size:14px;',
    '  font-family:-apple-system,BlinkMacSystemFont,"PingFang SC","Microsoft YaHei",sans-serif;',
    '  cursor:pointer;box-shadow:0 4px 16px rgba(0,0,0,.18);transition:transform .12s,background .12s}',
    '#lst-fab:hover{background:#178a66;transform:translateY(-1px)}',
    '#lst-fab:active{transform:translateY(0)}',
    '#lst-fab .plus{font-size:18px;line-height:1;margin-top:-2px}',
    '#lst-panel{position:fixed;right:24px;bottom:88px;z-index:2147483000;width:380px;max-height:52vh;overflow:auto;',
    '  background:#fff;border:1px solid #e3e3e3;border-radius:12px;box-shadow:0 8px 32px rgba(0,0,0,.16);',
    '  font-family:-apple-system,BlinkMacSystemFont,"PingFang SC","Microsoft YaHei",sans-serif;font-size:13px;',
    '  color:#1f1f1f;display:none}',
    '#lst-panel.show{display:block}',
    '#lst-panel .hd{display:flex;justify-content:space-between;align-items:center;padding:12px 14px;',
    '  border-bottom:1px solid #f0f0f0;font-weight:500}',
    '#lst-panel .bd{padding:8px 0}',
    '#lst-panel .row{display:flex;gap:8px;padding:7px 14px;align-items:flex-start;line-height:1.45}',
    '#lst-panel .nm{flex:1;min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}',
    '#lst-panel .st{flex:none;font-size:12px;white-space:nowrap}',
    '#lst-panel .ok{color:#0F6E56}#lst-panel .err{color:#A32D2D}#lst-panel .ing{color:#854F0B}',
    '#lst-panel .ft{padding:10px 14px;border-top:1px solid #f0f0f0;display:flex;gap:8px;justify-content:flex-end}',
    '#lst-panel .ft button{border:1px solid #ddd;background:#fff;border-radius:6px;padding:5px 12px;',
    '  font-size:12px;cursor:pointer;color:#1f1f1f}',
    '#lst-panel .ft button:hover{background:#f7f7f7}',
    '#lst-panel .x{border:none;background:none;cursor:pointer;font-size:18px;line-height:1;color:#999;padding:0 2px}',
    '#lst-drop{position:fixed;inset:0;z-index:2147483001;background:rgba(29,158,117,.10);',
    '  border:3px dashed #1D9E75;display:none;align-items:center;justify-content:center;',
    '  font-size:20px;color:#0F6E56;font-family:-apple-system,BlinkMacSystemFont,"PingFang SC",sans-serif}',
    '#lst-drop.show{display:flex}',
    '#lst-toast{position:fixed;left:50%;transform:translateX(-50%);bottom:24px;z-index:2147483002;',
    '  background:#2C2C2A;color:#fff;padding:10px 18px;border-radius:8px;font-size:13px;display:none}',
    '#lst-toast.show{display:block}'
  ].join('\n');
  document.head.appendChild(css);

  // ---------------------------------------------------------------- DOM
  var fab = document.createElement('button');
  fab.id = 'lst-fab';
  fab.innerHTML = '<span class="plus">＋</span><span>上传视频</span>';
  fab.title = '把视频文件传进当前项目（也可以直接把文件拖进窗口）';

  var panel = document.createElement('div');
  panel.id = 'lst-panel';
  panel.innerHTML =
    '<div class="hd"><span>上传进度</span><button class="x" data-act="close">×</button></div>' +
    '<div class="bd" id="lst-list"></div>' +
    '<div class="ft">' +
    '  <button data-act="open">打开数据管理器</button>' +
    '  <button data-act="again">再传一批</button>' +
    '</div>';

  var drop = document.createElement('div');
  drop.id = 'lst-drop';
  drop.textContent = '松手即可上传到当前项目';

  var toast = document.createElement('div');
  toast.id = 'lst-toast';

  var input = document.createElement('input');
  input.type = 'file';
  input.multiple = true;
  input.accept = ACCEPT + ',video/*';
  input.style.display = 'none';

  document.body.appendChild(fab);
  document.body.appendChild(panel);
  document.body.appendChild(drop);
  document.body.appendChild(toast);
  document.body.appendChild(input);

  function say(msg, ms) {
    toast.textContent = msg;
    toast.classList.add('show');
    clearTimeout(say._t);
    say._t = setTimeout(function () { toast.classList.remove('show'); }, ms || 2600);
  }

  // ---------------------------------------------------------------- 项目 id
  function projectIdFromUrl() {
    var m = location.pathname.match(/\/projects\/(\d+)/);
    return m ? parseInt(m[1], 10) : null;
  }

  // 不在项目页时（项目列表 / 首页），取列表：只有一个就直接用，多个让用户选
  function resolveProject() {
    var pid = projectIdFromUrl();
    if (pid) return Promise.resolve(pid);

    return fetch('/api/projects?page_size=100', { credentials: 'same-origin' })
      .then(function (r) { return r.json(); })
      .then(function (j) {
        var list = (j.results || j || []).filter(function (p) { return p && p.id; });
        if (!list.length) throw new Error('还没有任何项目，请先新建一个项目');
        if (list.length === 1) return list[0].id;

        var names = list.map(function (p, i) { return (i + 1) + '. ' + p.title + '（id=' + p.id + '）'; });
        var ans = window.prompt('这个实例有多个项目，传到哪一个？输入序号：\n\n' + names.join('\n'), '1');
        if (!ans) throw new Error('已取消');
        var idx = parseInt(ans, 10) - 1;
        if (!list[idx]) throw new Error('序号无效');
        return list[idx].id;
      });
  }

  // ---------------------------------------------------------------- CSRF
  function csrfToken() {
    var m = document.cookie.match(/(?:^|;\s*)csrftoken=([^;]+)/);
    return m ? decodeURIComponent(m[1]) : '';
  }

  // Django 只在渲染过带 {% csrf_token %} 的页面后才下发 cookie，
  // 万一没有，先碰一次页面让后端种上。
  function ensureCsrf() {
    if (csrfToken()) return Promise.resolve(csrfToken());
    return fetch('/projects/', { credentials: 'same-origin' })
      .then(function () { return csrfToken(); });
  }

  // ---------------------------------------------------------------- 上传
  var queue = [];

  function rowFor(name) {
    var row = document.createElement('div');
    row.className = 'row';
    row.innerHTML = '<span class="nm"></span><span class="st ing">等待</span>';
    row.querySelector('.nm').textContent = name;
    row.querySelector('.nm').title = name;
    document.getElementById('lst-list').appendChild(row);
    return row;
  }

  function setState(row, text, cls) {
    var st = row.querySelector('.st');
    st.textContent = text;
    st.className = 'st ' + cls;
  }

  function uploadOne(pid, file, row) {
    setState(row, '上传中…', 'ing');
    var fd = new FormData();
    fd.append('file', file);

    return fetch('/api/projects/' + pid + '/import', {
      method: 'POST',
      credentials: 'same-origin',
      headers: { 'X-CSRFToken': csrfToken() },
      body: fd
    }).then(function (r) {
      return r.text().then(function (t) {
        if (r.ok) {
          var n = 1;
          try { n = (JSON.parse(t).task_count) || 1; } catch (e) { /* 返回不是 json 也算成功 */ }
          setState(row, '✓ 已导入 ' + n + ' 条', 'ok');
          return true;
        }
        var msg = t.slice(0, 160);
        try { msg = JSON.stringify(JSON.parse(t)).slice(0, 160); } catch (e) { /* 原样 */ }
        setState(row, '✗ ' + r.status + ' ' + msg, 'err');
        return false;
      });
    }).catch(function (e) {
      setState(row, '✗ ' + (e && e.message ? e.message : '网络错误'), 'err');
      return false;
    });
  }

  function handleFiles(fileList) {
    var files = Array.prototype.slice.call(fileList || []);
    if (!files.length) return;
    panel.classList.add('show');

    var skipped = files.filter(function (f) { return !VID_EXT.test(f.name) && !/^video\//.test(f.type); });
    files = files.filter(function (f) { return VID_EXT.test(f.name) || /^video\//.test(f.type); });
    if (skipped.length) say('已跳过 ' + skipped.length + ' 个非视频文件');
    if (!files.length) { if (!skipped.length) say('没识别到视频文件'); return; }

    ensureCsrf()
      .then(function () { return resolveProject(); })
      .then(function (pid) {
        var rows = files.map(function (f) { return rowFor(f.name); });
        // 串行上传：并发会把 dev server 打满，且进度看不清
        return files.reduce(function (chain, f, i) {
          return chain.then(function () { return uploadOne(pid, f, rows[i]); });
        }, Promise.resolve()).then(function () {
          setTimeout(function () { say('上传完成，正在刷新列表…'); }, 300);
          setTimeout(function () {
            if (projectIdFromUrl()) location.href = '/projects/' + pid + '/data';
            else location.reload();
          }, 1400);
        });
      })
      .catch(function (e) { say(e && e.message ? e.message : '上传失败'); });
  }

  // ---------------------------------------------------------------- 事件
  fab.addEventListener('click', function () {
    input.value = '';
    input.click();
  });
  input.addEventListener('change', function () { handleFiles(input.files); });

  panel.addEventListener('click', function (e) {
    var act = e.target.getAttribute && e.target.getAttribute('data-act');
    if (act === 'close') panel.classList.remove('show');
    if (act === 'open') {
      var pid = projectIdFromUrl();
      location.href = pid ? '/projects/' + pid + '/data' : '/projects/';
    }
    if (act === 'again') { input.value = ''; input.click(); }
  });

  // 拖拽：整个窗口都能接
  var dragDepth = 0;
  window.addEventListener('dragenter', function (e) {
    if (!e.dataTransfer || Array.prototype.indexOf.call(e.dataTransfer.types || [], 'Files') < 0) return;
    dragDepth++;
    drop.classList.add('show');
  });
  window.addEventListener('dragover', function (e) {
    if (e.dataTransfer && Array.prototype.indexOf.call(e.dataTransfer.types || [], 'Files') >= 0) {
      e.preventDefault();
    }
  });
  window.addEventListener('dragleave', function () {
    dragDepth = Math.max(0, dragDepth - 1);
    if (!dragDepth) drop.classList.remove('show');
  });
  window.addEventListener('drop', function (e) {
    if (!e.dataTransfer || !e.dataTransfer.files || !e.dataTransfer.files.length) return;
    e.preventDefault();
    dragDepth = 0;
    drop.classList.remove('show');
    handleFiles(e.dataTransfer.files);
  });

  // 键盘：Alt+U 打开文件选择
  window.addEventListener('keydown', function (e) {
    if (e.altKey && (e.key === 'u' || e.key === 'U')) {
      e.preventDefault();
      input.value = '';
      input.click();
    }
  });
})();
