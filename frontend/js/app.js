/* EconIntel 前端核心：状态、分片加载、路由、版本检测、UI 工具 */
"use strict";

var App = {
  meta: window.EI_META || null,
  loadedBlocks: [],
  filters: { q: "", field: "全部", source: "全部", type: "全部", range: 30, imp: "全部" },
  sort: "score",
  view: "card",
};

var VERSION = (window.EI_CONFIG && window.EI_CONFIG.version) || "";
var BLOCKS = (window.EI_CONFIG && window.EI_CONFIG.blocks) || ["b1"];

/* ---------- 工具 ---------- */
function esc(s) {
  return String(s == null ? "" : s).replace(/[&<>"']/g, function (c) {
    return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c];
  });
}
function fmtDate(d) {
  if (!d) return "";
  var p = d.split("-");
  return Number(p[1]) + "月" + Number(p[2]) + "日";
}
function qs(sel) { return document.querySelector(sel); }
function el(tag, cls, html) {
  var e = document.createElement(tag);
  if (cls) e.className = cls;
  if (html != null) e.innerHTML = html;
  return e;
}
function toast(msg, isWarn, action) {
  var t = qs("#toast");
  t.className = "toast show" + (isWarn ? " warn" : "");
  t.textContent = "";
  t.appendChild(document.createTextNode(msg));
  if (action) t.appendChild(action);
  clearTimeout(t._t);
  t._t = setTimeout(function () { t.className = "toast"; }, 6000);
}
function cacheBusted(url) {
  return url + (url.indexOf("?") >= 0 ? "&" : "?") + "v=" + VERSION;
}
function loadScript(url, cb) {
  var s = document.createElement("script");
  s.src = url;
  s.onload = function () { cb && cb(); };
  s.onerror = function () { cb && cb(); }; // 失败也继续，避免卡死
  document.head.appendChild(s);
}
// 标签 → 徽章样式（以后端算好的标签 p.l 为准，避免前端取整与后端阈值不一致）
function labelInfo(l) {
  if (l && l.indexOf("热点") >= 0) return { cls: "l-hot", icon: "🔥" };
  if (l && l.indexOf("重要") >= 0) return { cls: "l-imp", icon: "⭐" };
  return { cls: "l-norm", icon: "📄" };
}
function badgeHtml(p) {
  var li = labelInfo(p.l);
  var score = p.s == null ? "?" : p.s.toFixed(1);
  return '<span class="badge ' + li.cls + '">' + li.icon + " " + score + "</span>";
}

/* ---------- 分片加载 ---------- */
function ensureIndex(block, cb) {
  if (App.loadedBlocks.indexOf(block) >= 0) { cb && cb(); return; }
  loadScript(cacheBusted("data/index-" + block + ".js"), function () {
    App.loadedBlocks.push(block);
    App.loadedBlocks.sort();
    updateRangeNote();
    cb && cb();
  });
}
function ensureDetail(block, cb) {
  if (window.EI_DETAIL && window.EI_DETAIL[block]) { cb && cb(); return; }
  loadScript(cacheBusted("data/detail-" + block + ".js"), cb);
}
function allIndexEntries() {
  var out = [];
  for (var i = 0; i < App.loadedBlocks.length; i++) {
    var arr = window.EI_INDEX && window.EI_INDEX[App.loadedBlocks[i]];
    if (arr) out = out.concat(arr);
  }
  return out;
}
function findPaper(id) {
  for (var i = 0; i < App.loadedBlocks.length; i++) {
    var arr = window.EI_INDEX && window.EI_INDEX[App.loadedBlocks[i]];
    if (!arr) continue;
    for (var j = 0; j < arr.length; j++) if (arr[j].id === id) return arr[j];
  }
  return null;
}

/* ---------- 范围提示 ---------- */
function totalIndexCount() {
  var meta = App.meta;
  if (!meta || !meta.blocks_info) return 0;
  var n = 0;
  meta.blocks_info.forEach(function (b) { n += b.count; });
  return n;
}
function updateRangeNote() {
  var note = qs("#range-note");
  var meta = App.meta;
  if (!meta) { note.innerHTML = ""; return; }
  var loaded = App.loadedBlocks.length;
  var total = meta.blocks.length;
  if (loaded >= total) {
    note.innerHTML = "已加载全部数据：<b>" + meta.window_start + " ~ " + meta.window_end +
      "</b>，共 <b>" + totalIndexCount() + "</b> 篇";
  } else {
    note.innerHTML = '<span class="loading">数据加载中… 已加载 ' + loaded + "/" + total +
      " 个分片，正在后台补载</span>";
  }
}

/* ---------- 版本检测 ---------- */
function startVersionPolling() {
  if (window.EI_OFFLINE) return; // 离线单文件版不轮询
  setInterval(function () {
    try {
      fetch(cacheBusted("data/meta.js")).then(function (r) { return r.text(); }).then(function (txt) {
        var m = txt.match(/window\.EI_META\s*=\s*(\{.*?\});?/s);
        if (!m) return;
        var meta = JSON.parse(m[1]);
        if (meta.version && meta.version !== VERSION) {
          var btn = el("button", "btn", "立即刷新");
          btn.onclick = function () { location.reload(true); };
          toast("检测到新数据（" + meta.generated_at.slice(0, 16).replace("T", " ") + " UTC）", false, btn);
        }
      }).catch(function () { /* 离线/无网场景静默 */ });
    } catch (e) { /* ignore */ }
  }, 60000);
}

/* ---------- 路由 ---------- */
function route() {
  var hash = location.hash || "#/";
  var nav = document.querySelectorAll(".nav a");
  for (var i = 0; i < nav.length; i++) {
    nav[i].className = hash.indexOf(nav[i].getAttribute("href")) === 0 ? "active" : "";
  }
  qs("#app").innerHTML = "";
  if (hash.indexOf("#/scholars") === 0) Pages.scholars();
  else if (hash.indexOf("#/subs") === 0) Pages.subs();
  else if (hash.indexOf("#/status") === 0) Pages.status();
  else Pages.renderPapers();
}

/* ---------- 初始化 ---------- */
App.init = function () {
  if (window.EI_META) {
    qs("#f-updated").textContent = new Date(window.EI_META.generated_at).toLocaleString("zh-CN", { hour12: false });
    qs("#f-window").textContent = "窗口 " + window.EI_META.window_start + " ~ " + window.EI_META.window_end;
    // 填充筛选选项
    var fieldSel = qs("#f-field"), srcSel = qs("#f-source");
    (window.EI_META.fields || []).forEach(function (f) {
      var o = el("option", null, esc(f)); o.value = f; fieldSel.appendChild(o);
    });
    (window.EI_META.sources || []).forEach(function (s) {
      var o = el("option", null, esc(s.name)); o.value = s.key; srcSel.appendChild(o);
    });
  }
  // 首屏：注入 b1 → 渲染；后台补载其余分片
  var b1 = BLOCKS[0];
  ensureIndex(b1, function () {
    route();
    for (var i = 1; i < BLOCKS.length; i++) {
      (function (b) {
        ensureIndex(b, function () {
          if (App.filters.q || App.filters.field !== "全部" || App.filters.source !== "全部") {
            Pages.renderPapers(); // 补载完成自动刷新结果（搜索永不漏）
          }
        });
      })(BLOCKS[i]);
    }
  });
  startVersionPolling();
  window.addEventListener("hashchange", route);
};
