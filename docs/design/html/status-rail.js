(function () {
  var KEY = "zhixu-status-open";
  var T = window.ZhixuTasks;
  var tasks = T ? T.list() : [];

  function row(label, value, valueId) {
    return (
      '<div class="flex items-center justify-between">' +
      '<span class="text-xs text-secondary-text">' +
      label +
      "</span>" +
      '<span class="text-sm font-bold"' +
      (valueId ? ' id="' + valueId + '"' : "") +
      ">" +
      value +
      "</span></div>"
    );
  }
  function link(href, label) {
    return (
      '<a class="flex items-center justify-between p-3 rounded-xl hover:bg-white transition-colors" href="' +
      href +
      '"><span class="text-xs text-secondary-text">' +
      label +
      '</span><svg class="w-4 h-4 text-secondary-text" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path d="M14 5l7 7m0 0l-7 7m7-7H3" stroke-linecap="round" stroke-linejoin="round" stroke-width="2"></path></svg></a>'
    );
  }

  var pending = T ? T.pendingCount() : tasks.length;
  var railCards = T ? tasks.map(T.railCard).join("") : "";

  var layer = document.createElement("div");
  layer.id = "status-layer";
  layer.className = "is-closed";
  layer.innerHTML =
    '<div id="status-backdrop"></div>' +
    '<aside id="status-rail"><div class="status-inner">' +
    "<section><h4 class=\"text-sm font-bold mb-4\">今日状态</h4>" +
    '<div class="space-y-3">' +
    row("学习时长", "42 分钟") +
    row("连续打卡", "5 天") +
    row("待完成", pending + " 件任务", "status-pending-count") +
    row("新 tip", "2 张") +
    "</div></section>" +
    "<section><div class=\"flex items-end justify-between mb-3\">" +
    '<h5 class="text-xs font-bold text-secondary-text uppercase">当前任务</h5>' +
    '<span class="text-[11px] text-secondary-text">Tina 按目标排的</span></div>' +
    '<div id="status-task-list" class="space-y-2">' +
    railCards +
    "</div></section>" +
    "<section><h5 class=\"text-xs font-bold text-secondary-text uppercase mb-3\">根据作答</h5>" +
    '<div class="bg-white border border-card-border rounded-2xl p-3">' +
    '<div class="flex items-center justify-between mb-1"><span class="text-sm font-medium">build</span>' +
    '<span class="text-[10px] px-2 py-0.5 rounded-full bg-[#C17B5A]/10 text-[#C17B5A]">50%</span></div>' +
    '<p class="text-[11px] text-secondary-text leading-relaxed">错 3 · 不会 1。tag 已经能看出来，适合今天补。</p>' +
    "</div></section>" +
    '<section><div class="flex items-center space-x-2 text-sage-accent mb-3">' +
    '<svg class="w-4 h-4" fill="currentColor" viewBox="0 0 20 20"><path d="M11 3a1 1 0 10-2 0v1a1 1 0 102 0V3zM15.657 5.757a1 1 0 00-1.414-1.414l-.707.707a1 1 0 001.414 1.414l.707-.707zM18 10a1 1 0 01-1 1h-1a1 1 0 110-2h1a1 1 0 011 1zM5.05 6.464A1 1 0 106.464 5.05l-.707-.707a1 1 0 00-1.414 1.414l.707.707zM5 10a1 1 0 01-1 1H3a1 1 0 110-2h1a1 1 0 011 1zM8 16v-1a1 1 0 112 0v1a1 1 0 11-2 0z"></path></svg>' +
    '<h4 class="text-sm font-bold">Tina 建议</h4></div>' +
    '<div class="bg-[#F3F6F5] p-4 rounded-2xl border border-card-border"><ul class="text-xs text-secondary-text space-y-2">' +
    '<li class="flex items-start"><span class="w-1.5 h-1.5 rounded-full bg-sage-accent mt-1 mr-2 flex-shrink-0"></span><span>先过 build 相关 tip，再刷 5 道同一 tag</span></li>' +
    '<li class="flex items-start"><span class="w-1.5 h-1.5 rounded-full bg-sage-accent mt-1 mr-2 flex-shrink-0"></span><span>「我不会」的题不要混进正确率里硬刷</span></li>' +
    "</ul></div></section>" +
    '<section><h4 class="text-sm font-bold mb-3">快捷入口</h4><div class="space-y-1">' +
    link("index.html", "回首页看任务") +
    link("notes.html#tips", "去 tip") +
    link("path.html", "学习路径") +
    link("onboarding.html?replay=1", "新手指引") +
    "</div></section></div></aside>";

  document.body.appendChild(layer);
  if (T) T.renderAll();

  var header = document.querySelector("main > header");
  var entry = document.createElement("a");
  entry.id = "onboard-entry";
  entry.href = "onboarding.html?replay=1";
  entry.title = "打开新手指引";
  entry.innerHTML =
    '<svg fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z"></path></svg>' +
    "<span>新手指引</span>";
  var btn = document.createElement("button");
  btn.id = "status-toggle";
  btn.type = "button";
  btn.innerHTML =
    '<svg fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z"></path></svg>' +
    "<span>今日状态</span>";
  if (header) {
    header.appendChild(entry);
    header.appendChild(btn);
  }

  function apply(open) {
    layer.classList.toggle("is-closed", !open);
    btn.classList.toggle("is-on", open);
    btn.setAttribute("aria-expanded", String(open));
    btn.title = open ? "关闭今日状态" : "打开今日状态";
  }

  apply(localStorage.getItem(KEY) === "1");
  btn.addEventListener("click", function () {
    var next = layer.classList.contains("is-closed");
    localStorage.setItem(KEY, next ? "1" : "0");
    apply(next);
  });
  layer.querySelector("#status-backdrop").addEventListener("click", function () {
    localStorage.setItem(KEY, "0");
    apply(false);
  });
  document.addEventListener("keydown", function (e) {
    if (e.key === "Escape" && !layer.classList.contains("is-closed")) {
      localStorage.setItem(KEY, "0");
      apply(false);
    }
  });
})();
