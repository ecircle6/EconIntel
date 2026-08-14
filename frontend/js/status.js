/* 数据源状态页：各源健康度、摘要覆盖率、总量统计 */
"use strict";

var Pages = Pages || {};

Pages.status = function () {
  var app = qs("#app");
  var meta = App.meta;
  app.innerHTML = "";
  app.appendChild(el("h2", null, "数据源状态"));

  if (!meta) {
    app.appendChild(el("div", "empty", "元数据缺失"));
    return;
  }

  // KPI
  var t = meta.totals || {};
  var kpi = el("div", "kpi-row");
  [
    ["论文总数", t.papers || 0],
    ["🔥 热点", t.hot || 0],
    ["⭐ 重要", t.important || 0],
    ["期刊论文", t.journal || 0],
    ["工作论文", t.working || 0],
  ].forEach(function (k) {
    kpi.appendChild(el("div", "kpi", "<b>" + k[1] + "</b><span>" + k[0] + "</span>"));
  });
  app.appendChild(kpi);

  // 源健康表
  var table = el("table", "status-table");
  table.innerHTML =
    "<thead><tr><th>来源</th><th>可信度</th><th>状态</th><th>最近抓取</th><th>窗口内论文</th><th>摘要覆盖率</th></tr></thead>";
  var tbody = el("tbody");
  (meta.sources || []).forEach(function (s) {
    var status = s.status === "ok"
      ? '<span class="stat-ok">正常</span>'
      : '<span class="stat-err">异常</span>';
    var cov = s.abstract_coverage || 0;
    var tr = el("tr");
    tr.innerHTML =
      "<td><b>" + esc(s.name) + "</b> <span class='pc-date'>(" + esc(s.key) + ")</span></td>" +
      "<td>" + (s.credibility === "A" ? "A 官方机构" : s.credibility === "B" ? "B 学术数据库" : "C 预印本") + "</td>" +
      "<td>" + status + "</td>" +
      "<td>" + (s.last_fetch || "-") + "</td>" +
      "<td>" + s.count + "</td>" +
      '<td><span class="cov-bar"><i style="width:' + Math.round(cov * 100) + '%"></i></span> ' +
      Math.round(cov * 100) + "%</td>";
    tbody.appendChild(tr);
  });
  table.appendChild(tbody);
  app.appendChild(table);

  app.appendChild(el("p", "sub-hint",
    "更新时间：" + meta.generated_at + "（UTC）· " + meta.update_schedule +
    " · 数据窗口：" + meta.window_start + " ~ " + meta.window_end +
    " · 分片：" + meta.blocks.join(", ")));
};
