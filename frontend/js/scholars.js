/* 学者画像页：窗口内 ≥2 篇论文的作者聚合 */
"use strict";

var Pages = Pages || {};

Pages.scholars = function () {
  var app = qs("#app");
  var data = window.EI_SCHOLARS || [];
  app.innerHTML = "";
  app.appendChild(el("h2", null, "学者画像"));
  app.appendChild(el("p", "range-note", "窗口内发表 ≥2 篇论文的作者（按论文数排序）。点击查看其论文。"));
  if (!data.length) {
    app.appendChild(el("div", "empty", "暂无学者数据"));
    return;
  }
  var grid = el("div", "grid");
  data.forEach(function (s) {
    var chips = (s.f || []).map(function (f) { return '<span class="sc-chip">' + esc(f) + "</span>"; }).join("");
    var srcs = (s.src || []).map(function (x) { return '<span class="sc-chip">' + esc(x) + "</span>"; }).join("");
    var card = el("div", "scholar-card", "");
    card.innerHTML =
      '<div class="sc-name">' + esc(s.n) + "</div>" +
      '<div class="sc-meta">' + s.c + " 篇论文 · 平均重要性 " + s.avg + "</div>" +
      '<div>' + chips + "</div>" +
      (srcs ? '<div class="sc-meta">来源：' + srcs + "</div>" : "");
    card.onclick = function () {
      App.filters.q = s.n.split(",")[0].trim(); // 姓氏检索
      qs("#f-q").value = App.filters.q;
      location.hash = "#/";
      Pages.renderPapers();
    };
    grid.appendChild(card);
  });
  app.appendChild(grid);
};
