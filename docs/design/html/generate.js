(function () {
  var MAX = 10;
  var TINA_PAGES = [5, 6, 7, 8, 9];
  var pages = [
    { n: 1, ch: "Widget 与 Element", title: "什么是 Widget", preview: "界面都从 Widget 长出来。", q: 0,
      body: "<p>Flutter 里你看见的几乎都是 Widget。StatelessWidget 只描述长什么样。</p>" },
    { n: 2, ch: "Widget 与 Element", title: "StatefulWidget", preview: "会变的那一份 State。", q: 0,
      body: "<p>StatefulWidget 带着一份会变的 State。Widget 可以很便宜地重建。</p>" },
    { n: 3, ch: "Widget 与 Element", title: "Element 落地", preview: "记住这是同一块地方。", q: 0,
      body: "<p>Element 是 Widget 在树上的落地位置，负责记住「这是同一块地方」。</p>" },
    { n: 4, ch: "Widget 与 Element", title: "rebuild 不等于销毁", preview: "节点还在，只是描述换了。", q: 0,
      body: "<p>rebuild 不等于销毁节点。出题会问 Widget 和 Element 的分工。</p>" },
    { n: 5, ch: "生命周期与 build", title: "initState", preview: "一次性初始化。", q: 0,
      body: "<p>initState 适合一次性初始化，不要在 build 里发请求。</p>" },
    { n: 6, ch: "生命周期与 build", title: "build 保持纯净", preview: "被调用的次数很多。", q: 0,
      body: "<p>build 被调用的次数很多。副作用放在 initState 或专门的回调里。</p>" },
    { n: 7, ch: "生命周期与 build", title: "setState", preview: "只是标记这块脏了。", q: 0,
      body: "<p>setState 只是标记脏节点，真正的重建由框架调度。</p>" },
    { n: 8, ch: "生命周期与 build", title: "dispose", preview: "订阅要在这里摘掉。", q: 0,
      body: "<p>dispose 里取消订阅。这一章是 Tina 按目录选中的范围。</p>" },
    { n: 9, ch: "生命周期与 build", title: "不要硬刷不会", preview: "不会单独过。", q: 0,
      body: "<p>「我不会」的题不要混进正确率里硬刷，单独走辅导。</p>" },
    { n: 10, ch: "InheritedWidget 与数据下发", title: "向下共享", preview: "不必层层传参。", q: 0,
      body: "<p>InheritedWidget 让子树按需拿到同一份数据。</p>" },
    { n: 11, ch: "InheritedWidget 与数据下发", title: "dependOn", preview: "声明依赖才会重建。", q: 0,
      body: "<p>只有声明了 dependOn 的节点，在数据变化时才会重建。</p>" },
    { n: 12, ch: "InheritedWidget 与数据下发", title: "和 State 的分工", preview: "各管一层。", q: 0,
      body: "<p>这一章题会问：什么时候用 InheritedWidget，它和 StatefulWidget 各管什么。</p>" }
  ];

  var selected = {};
  var active = 1;
  var running = false;
  var listEl = document.getElementById("page-list");
  var titleEl = document.getElementById("preview-title");
  var metaEl = document.getElementById("preview-meta");
  var bodyEl = document.getElementById("preview-body");
  var btn = document.getElementById("gen-btn");
  var badge = document.getElementById("gen-badge");
  var result = document.getElementById("gen-result");
  var logEl = document.getElementById("gen-log");
  var countEl = document.getElementById("sel-count");
  var tinaEl = document.getElementById("tina-pick");
  var newEl = document.getElementById("gen-new");

  function fromTina() {
    return /(?:from=tina|tina=1)/.test(location.search);
  }

  function pageBy(n) {
    for (var i = 0; i < pages.length; i++) if (pages[i].n === n) return pages[i];
    return null;
  }

  function selectedList() {
    return pages.filter(function (p) { return selected[p.n]; });
  }

  function selectedCount() {
    return selectedList().length;
  }

  function setBadge(kind) {
    badge.className = "text-[10px] px-2 py-0.5 rounded-full ";
    if (kind === "run") {
      badge.className += "bg-[#C17B5A]/15 text-bad";
      badge.textContent = "出题中";
    } else if (kind === "done") {
      badge.className += "bg-ok/15 text-ok";
      badge.textContent = "已出题";
    } else {
      badge.className += "bg-white border border-card-border text-secondary-text";
      badge.textContent = "未出题";
    }
  }

  function updateHint() {
    var n = selectedCount();
    countEl.textContent = String(n);
    btn.disabled = running || n === 0 || n > MAX;
    if (n > MAX) btn.title = "单次最多 " + MAX + " 页";
    else btn.title = "";
  }

  function renderList() {
    var html = "";
    var lastCh = "";
    pages.forEach(function (p) {
      if (p.ch !== lastCh) {
        lastCh = p.ch;
        html += '<p class="px-2 pt-2 pb-1 text-[10px] font-semibold text-secondary-text">' + p.ch + "</p>";
      }
      var on = p.n === active;
      var qtxt = p.q > 0 ? "已出题 " + p.q : "尚未出题";
      html +=
        '<div class="flex items-start gap-1 rounded-xl mb-0.5 ' + (on ? "ch-on" : "") + '">' +
        '<button type="button" data-check="' + p.n + '" class="shrink-0 px-2 py-2.5 text-sage-accent" title="勾选此页">' +
        (selected[p.n]
          ? '<svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z"></path></svg>'
          : '<svg class="w-4 h-4 text-secondary-text" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M8 12h8m4 0a9 9 0 11-18 0 9 9 0 0118 0z"></path></svg>') +
        "</button>" +
        '<button type="button" data-open="' + p.n + '" class="flex-1 min-w-0 text-left px-1 py-2">' +
        '<div class="text-sm font-medium truncate">第 ' + p.n + " 页 · " + p.title + "</div>" +
        '<p class="text-[11px] text-secondary-text">' + qtxt + "</p>" +
        '<p class="text-[11px] text-secondary-text truncate">' + p.preview + "</p>" +
        "</button></div>";
    });
    listEl.innerHTML = html;
    updateHint();
  }

  function showPage(n) {
    var p = pageBy(n);
    if (!p) return;
    active = n;
    titleEl.textContent = "第 " + p.n + " 页 · " + p.title;
    metaEl.textContent = (p.q > 0 ? "已出题 " + p.q : "尚未出题") + " · " + p.ch;
    bodyEl.innerHTML = p.body;
    renderList();
  }

  function addLog(kind, text) {
    if (logEl.querySelector(".text-center")) logEl.innerHTML = "";
    var p = document.createElement("p");
    if (kind === "tool") p.className = "log-tool";
    if (kind === "done") p.className = "log-done";
    if (kind === "status") p.className = "text-secondary-text";
    p.textContent = text;
    logEl.appendChild(p);
    logEl.scrollTop = logEl.scrollHeight;
  }

  function run() {
    var list = selectedList();
    if (running || !list.length || list.length > MAX) return;
    running = true;
    setBadge("run");
    btn.disabled = true;
    btn.innerHTML =
      '<svg class="w-4 h-4 inline spin mr-1" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path d="M12 4v2m0 12v2m8-8h-2M6 12H4" stroke-linecap="round" stroke-width="2"></path></svg>AI 正在出题';
    logEl.innerHTML = "";
    var nums = list.map(function (p) { return p.n; });
    addLog("status", "请求后端出题 · 页码 " + nums.join("、") + "（最多同时 3 路）");
    var i = 0;
    function next() {
      if (i >= list.length) {
        running = false;
        setBadge("done");
        btn.textContent = "继续勾选可再出";
        btn.classList.remove("opacity-70");
        var created = list.length * 2;
        if (newEl) newEl.textContent = String(created);
        result.classList.remove("hidden");
        addLog("done", "全部结束，本批 " + created + " 题。");
        showPage(active);
        if (window.ZhixuTasks) ZhixuTasks.recordExtract();
        return;
      }
      var p = list[i];
      addLog("tool", "第 " + p.n + " 页 · 提交单选题");
      setTimeout(function () {
        p.q = 2;
        addLog("done", "第 " + p.n + " 页完成（2 题）");
        showPage(p.n);
        i += 1;
        setTimeout(next, 450);
      }, 500);
    }
    next();
  }

  listEl.addEventListener("click", function (e) {
    var check = e.target.closest("[data-check]");
    var open = e.target.closest("[data-open]");
    if (check) {
      var n = Number(check.getAttribute("data-check"));
      selected[n] = !selected[n];
      showPage(n);
      return;
    }
    if (open) showPage(Number(open.getAttribute("data-open")));
  });

  document.getElementById("sel-all").addEventListener("click", function () {
    var cap = Math.min(pages.length, MAX);
    pages.forEach(function (p, i) {
      selected[p.n] = i < cap;
    });
    renderList();
  });
  document.getElementById("sel-none").addEventListener("click", function () {
    selected = {};
    renderList();
  });
  btn.addEventListener("click", run);

  if (fromTina()) {
    TINA_PAGES.forEach(function (n) { selected[n] = true; });
    tinaEl.classList.remove("hidden");
    showPage(5);
  } else {
    showPage(1);
  }
})();
