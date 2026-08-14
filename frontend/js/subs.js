/* 订阅中心：localStorage 关注（作者/领域/来源）→ 匹配最近论文 */
"use strict";

var Pages = Pages || {};
var Subs = Subs || {};

Subs.get = function () {
  try { return JSON.parse(localStorage.getItem("eiconsubs") || "[]"); }
  catch (e) { return []; }
};
Subs.save = function (list) {
  localStorage.setItem("eiconsubs", JSON.stringify(list));
};
Subs.add = function (kind, value) {
  if (!value) return;
  var list = Subs.get();
  for (var i = 0; i < list.length; i++) {
    if (list[i].kind === kind && list[i].value.toLowerCase() === value.toLowerCase()) return;
  }
  list.push({ kind: kind, value: value });
  Subs.save(list);
  Subs.render && Subs.render();
};
Subs.remove = function (kind, value) {
  Subs.save(Subs.get().filter(function (s) { return !(s.kind === kind && s.value === value); }));
  Subs.render && Subs.render();
};

Subs.matches = function (sub) {
  var v = sub.value.toLowerCase();
  return allIndexEntries().filter(function (p) {
    if (sub.kind === "author") return (p.a || []).some(function (a) { return a.toLowerCase().indexOf(v) >= 0; });
    if (sub.kind === "field") return (p.f || "").toLowerCase() === v;
    if (sub.kind === "source") return (p.src || "") === sub.value;
    return false;
  }).sort(function (a, b) { return b.s - a.s; }).slice(0, 20);
};

Subs.render = function () {
  var app = qs("#app");
  var list = Subs.get();
  app.innerHTML = "";
  app.appendChild(el("h2", null, "订阅中心"));
  app.appendChild(el("p", "range-note", "关注作者 / 领域 / 来源后，此处自动汇总匹配论文（取最近 20 篇，按重要性排序）。数据保存在本浏览器。"));
  // 添加表单
  var form = el("div", "sub-form");
  form.innerHTML =
    '<select id="sub-kind"><option value="author">作者</option><option value="field">领域</option><option value="source">来源</option></select>' +
    '<input id="sub-value" placeholder="输入作者名 / 领域 / 来源 key（如 nber、宏观）">' +
    '<button class="btn btn-primary" id="sub-add">添加关注</button>';
  app.appendChild(form);
  qs("#sub-add").onclick = function () {
    Subs.add(qs("#sub-kind").value, qs("#sub-value").value.trim());
    qs("#sub-value").value = "";
  };
  qs("#sub-value").addEventListener("keydown", function (e) {
    if (e.key === "Enter") qs("#sub-add").click();
  });

  if (!list.length) {
    app.appendChild(el("div", "empty", "还没有关注。打开论文详情页点「关注作者/领域/来源」，或在上方手动添加。"));
    return;
  }
  var kindName = { author: "作者", field: "领域", source: "来源" };
  list.forEach(function (sub) {
    var box = el("div", "sub-box");
    var papers = Subs.matches(sub);
    var listHtml = papers.length
      ? papers.map(function (p) {
          return '<div class="sub-paper" data-id="' + p.id + '">' +
            '<span class="badge ' + (p.s >= 80 ? "l-hot" : p.s >= 60 ? "l-imp" : "l-norm") + '">' + p.s + "</span> " +
            esc(p.t) + ' <span class="pc-date">' + fmtDate(p.d) + " · " + esc(p.src) + "</span></div>";
        }).join("")
      : '<div class="sub-hint">近 90 天暂无匹配论文</div>';
    box.innerHTML =
      "<h3><span class='badge badge-field'>" + kindName[sub.kind] + "</span>" + esc(sub.value) +
      '<button class="sub-remove" title="取消关注">取消关注</button></h3>' +
      '<div class="sub-papers">' + listHtml + "</div>";
    box.querySelector(".sub-remove").onclick = function () { Subs.remove(sub.kind, sub.value); };
    box.addEventListener("click", function (e) {
      var row = e.target.closest && e.target.closest("[data-id]");
      if (row) Pages.openDetail(Number(row.getAttribute("data-id")));
    });
    app.appendChild(box);
  });
};

Pages.subs = function () { Subs.render(); };
