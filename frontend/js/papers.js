/* 论文流页面：筛选 / 排序 / 双视图 / 详情弹窗 */
"use strict";

var Pages = Pages || {};
var _rendered = 0;
var _chunk = 100;

Pages.filteredPapers = function () {
  var f = App.filters;
  var list = allIndexEntries();
  var minDate = null;
  if (f.range > 0 && f.range < 90) {
    var d = new Date(Date.now() - f.range * 864e5);
    minDate = d.toISOString().slice(0, 10);
  }
  if (f.q) {
    var q = f.q.toLowerCase();
    list = list.filter(function (p) {
      return (p.t || "").toLowerCase().indexOf(q) >= 0 ||
        (p.a || []).some(function (a) { return a.toLowerCase().indexOf(q) >= 0; }) ||
        (p.k || []).some(function (k) { return k.toLowerCase().indexOf(q) >= 0; });
    });
  }
  if (f.field !== "全部") list = list.filter(function (p) { return p.f === f.field; });
  if (f.source !== "全部") list = list.filter(function (p) { return p.src === f.source; });
  if (f.type !== "全部") list = list.filter(function (p) { return (p.ty === "jr") === (f.type === "期刊论文"); });
  if (f.imp !== "全部") list = list.filter(function (p) { return p.l === f.imp; });
  if (minDate) list = list.filter(function (p) { return p.d >= minDate; });
  list.sort(function (a, b) {
    if (App.sort === "date") return (b.d < a.d ? -1 : b.d > a.d ? 1 : b.s - a.s);
    return (b.s - a.s) || (b.d < a.d ? -1 : 1);
  });
  return list;
};

function cardHtml(p) {
  var authors = (p.a || []).join(", ");
  var kw = (p.k || []).map(function (k) { return '<span class="chip">' + esc(k) + "</span>"; }).join("");
  return (
    '<div class="paper-card ' + (p.s >= 80 ? "l-hot" : p.s >= 60 ? "l-imp" : "") + '" data-id="' + p.id + '">' +
    '<div class="pc-top">' + badgeHtml(p) +
    (p.f ? '<span class="badge badge-field">' + esc(p.f) + "</span>" : "") +
    '<span class="badge badge-src">' + esc(p.src) + "</span>" +
    '<span class="badge ' + (p.ty === "jr" ? "badge-jr" : "badge-wp") + '">' + (p.ty === "jr" ? "期刊" : "工作论文") + "</span>" +
    '<span class="pc-date">' + fmtDate(p.d) + "</span></div>" +
    '<div class="pc-title">' + esc(p.t) + "</div>" +
    (authors ? '<div class="pc-authors">' + esc(authors) + "</div>" : "") +
    (kw ? '<div class="pc-kw">' + kw + "</div>" : "") +
    "</div>"
  );
}

function listRowHtml(p) {
  var authors = (p.a || []).slice(0, 3).join(", ");
  return (
    '<div class="paper-list" data-id="' + p.id + '">' +
    '<span class="pl-score">' + badgeHtml(p) + "</span>" +
    '<span class="pl-main"><span class="pl-title">' + esc(p.t) + "</span>" +
    (authors ? '<span class="pl-sub">' + esc(authors) + " · " + esc(p.src) + " · " + fmtDate(p.d) + "</span>" : "") +
    "</span></div>"
  );
}

Pages.renderPapers = function () {
  var app = qs("#app");
  var list = Pages.filteredPapers();
  _rendered = 0;
  app.innerHTML = "";
  var root = el("div", "papers-view");
  app.appendChild(root);

  // 搜索时若补载未完成 → 提示
  var loading = App.loadedBlocks.length < BLOCKS.length && (App.filters.q || App.filters.field !== "全部");
  if (loading) {
    var tip = el("div", "range-note loading", "后台数据补载中，结果可能不完整，完成后将自动更新…");
    app.insertBefore(tip, root);
  }

  if (!list.length) {
    app.appendChild(el("div", "empty", "没有符合条件的论文。试试放宽筛选条件。"));
    return;
  }
  renderChunk(root, list);
};

function renderChunk(root, list) {
  var end = Math.min(_rendered + _chunk, list.length);
  var frag = document.createDocumentFragment();
  for (var i = _rendered; i < end; i++) {
    frag.appendChild(el("div", null, App.view === "card" ? cardHtml(list[i]) : listRowHtml(list[i])));
  }
  root.appendChild(frag);
  _rendered = end;
  if (_rendered < list.length) {
    var btn = el("button", "load-more", "加载更多（" + (_rendered) + "/" + list.length + "）");
    btn.onclick = function () { renderChunk(root, list); };
    root.appendChild(btn);
  } else {
    var done = el("div", "range-note", "共 " + list.length + " 篇");
    root.appendChild(done);
  }
}

/* ---------- 详情弹窗 ---------- */
Pages.openDetail = function (id) {
  var entry = findPaper(id);
  if (!entry) { toast("数据未加载，请稍候", true); return; }
  ensureDetail(entry.b, function () {
    var d = window.EI_DETAIL && window.EI_DETAIL[entry.b] && window.EI_DETAIL[entry.b][id];
    if (!d) { toast("详情数据缺失", true); return; }
    renderModal(d);
  });
};

function renderModal(d) {
  var mask = el("div", "modal-mask");
  var authors = (d.a || []).join(", ");
  var jel = (d.jel || []).join(", ");
  var absHtml = d.abs
    ? esc(d.abs)
    : '<span class="no-abs">该来源未提供摘要（可在原文链接查看）</span>';
  var versions = (d.vs || []).map(function (v) {
    return '<div class="v-row">' +
      '<span class="badge ' + (v.ty === "jr" ? "badge-jr" : "badge-wp") + '">' + (v.ty === "jr" ? "期刊版" : "工作论文") + "</span>" +
      "<span>" + esc(v.t) + "</span>" +
      '<span class="pc-date">' + esc(v.sn) + " · " + fmtDate(v.d) + "</span>" +
      (v.url ? ' <a href="' + esc(v.url) + '" target="_blank" rel="noopener">原文 ↗</a>' : "") +
      "</div>";
  }).join("");

  // 评分构成（透明展示）
  var bd = d.bd;
  var scoreHtml = "";
  if (bd) {
    var citeNote = d.ct == null
      ? "引用数未知（按 0 计）"
      : "引用 " + d.ct + "（来源：" + (d.cs === "crossref" ? "CrossRef" : d.cs === "openalex" ? "OpenAlex" : d.cs === "s2" ? "Semantic Scholar" : "未知") + "）";
    scoreHtml =
      '<div class="m-section"><h4>重要性评分构成（' + Math.round(d.s) + " / 100）</h4>" +
      '<div class="m-meta">' +
      "<span>机构权威</span><span><b>" + bd.institution + " 分</b>（" + (d.cr === "A" ? "A 官方机构" : d.cr === "B" ? "B 学术数据库" : "C 预印本") + "）</span>" +
      "<span>引用数</span><span><b>" + bd.citations + " 分</b>（" + citeNote + "）</span>" +
      "<span>时效性</span><span><b>" + bd.recency + " 分</b>（发布于 " + d.d + "）</span>" +
      "<span>论文类型</span><span><b>" + bd.paper_type + " 分</b>（" + (d.ty === "jr" ? "期刊论文" : "工作论文") + "）</span>" +
      "</div></div>";
  }

  var maskHtml =
    '<div class="modal">' +
    '<button class="m-close" title="关闭">×</button>' +
    '<div class="m-top">' + badgeHtml({ s: d.s, l: d.l }) +
    (d.f ? '<span class="badge badge-field">' + esc(d.f) + "</span>" : "") +
    '<span class="badge badge-src">' + esc(d.sn) + "</span>" +
    '<span class="badge ' + (d.ty === "jr" ? "badge-jr" : "badge-wp") + '">' + (d.ty === "jr" ? "期刊论文" : "工作论文") + "</span>" +
    '<span class="pc-date">' + d.d + "</span></div>" +
    '<h2 class="m-title">' + esc(d.t) + "</h2>" +
    (d.st && d.st !== d.t ? '<span class="m-short">精简：' + esc(d.st) + "</span>" : "") +
    (d.c ? '<div class="m-section"><h4>核心贡献</h4><p>' + esc(d.c) + "</p></div>" : "") +
    scoreHtml +
    '<div class="m-section"><h4>摘要</h4><div class="m-abs">' + absHtml + "</div></div>" +
    '<div class="m-section"><div class="m-meta">' +
    (authors ? "<span>作者</span><span><b>" + esc(authors) + "</b></span>" : "") +
    "<span>时间</span><span>" + esc(d.d) + (d.ct != null ? " · 引用 " + d.ct : "") + "</span>" +
    (jel ? "<span>JEL</span><span>" + esc(jel) + "</span>" : "") +
    (d.doi ? '<span>DOI</span><span><a href="https://doi.org/' + esc(d.doi) + '" target="_blank" rel="noopener">' + esc(d.doi) + "</a></span>" : "") +
    '<span>可信度</span><span>' + (d.cr === "A" ? "A 官方机构" : d.cr === "B" ? "B 学术数据库" : "C 预印本") + "</span>" +
    "</div></div>" +
    (versions ? '<div class="m-versions"><h4>版本历史（同一研究的其他版本）</h4>' + versions + "</div>" : "") +
    '<div class="m-links">' +
    (d.url ? '<a class="btn btn-primary" href="' + esc(d.url) + '" target="_blank" rel="noopener">查看原文 ↗</a>' : "") +
    '<button class="btn" data-follow="field" data-value="' + esc(d.f) + '">关注领域</button>' +
    '<button class="btn" data-follow="source" data-value="' + esc(d.src) + '">关注来源</button>' +
    (d.a && d.a.length ? '<button class="btn" data-follow="author" data-value="' + esc(d.a[0]) + '">关注作者</button>' : "") +
    "</div></div>";

  mask.innerHTML = maskHtml;
  mask.addEventListener("click", function (e) {
    if (e.target === mask || e.target.className === "m-close") closeModal();
    var fb = e.target.closest && e.target.closest("[data-follow]");
    if (fb) {
      Subs.add(fb.getAttribute("data-follow"), fb.getAttribute("data-value"));
      toast("已关注：" + fb.getAttribute("data-value"));
    }
  });
  qs("#modal-root").appendChild(mask);
  document.body.style.overflow = "hidden";
}

function closeModal() {
  var root = qs("#modal-root");
  root.innerHTML = "";
  document.body.style.overflow = "";
}

/* ---------- 事件绑定 ---------- */
document.addEventListener("DOMContentLoaded", function () {
  var appEl = qs("#app");
  appEl.addEventListener("click", function (e) {
    var card = e.target.closest && e.target.closest("[data-id]");
    if (card) Pages.openDetail(Number(card.getAttribute("data-id")));
  });
  var qInput = qs("#f-q");
  var qTimer = null;
  qInput.addEventListener("input", function () {
    clearTimeout(qTimer);
    qTimer = setTimeout(function () {
      App.filters.q = qInput.value.trim();
      Pages.renderPapers();
    }, 250);
  });
  function bindSel(id, key, parse) {
    qs(id).addEventListener("change", function () {
      App.filters[key] = parse ? parse(this.value) : this.value;
      Pages.renderPapers();
    });
  }
  bindSel("#f-field", "field");
  bindSel("#f-source", "source");
  bindSel("#f-type", "type");
  bindSel("#f-imp", "imp");
  bindSel("#f-range", "range", Number);
  qs("#f-sort").addEventListener("change", function () { App.sort = this.value; Pages.renderPapers(); });
  qs("#view-card").onclick = function () {
    App.view = "card";
    qs("#view-card").className = "active"; qs("#view-list").className = "";
    Pages.renderPapers();
  };
  qs("#view-list").onclick = function () {
    App.view = "list";
    qs("#view-list").className = "active"; qs("#view-card").className = "";
    Pages.renderPapers();
  };
  document.addEventListener("keydown", function (e) {
    if (e.key === "Escape") closeModal();
  });
});
