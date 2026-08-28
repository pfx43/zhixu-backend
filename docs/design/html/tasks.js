(function (global) {
  var STORE = "zhixu-task-progress";

  function profile() {
    try {
      return JSON.parse(localStorage.getItem("zhixu-profile") || "{}");
    } catch (e) {
      return {};
    }
  }

  function emptyProgress() {
    return {
      done: {},
      quizAnswered: 0,
      unknownAnswered: 0,
      uploaded: false,
      extracted: false,
      hintDismissed: false,
    };
  }

  function load() {
    try {
      return Object.assign(emptyProgress(), JSON.parse(localStorage.getItem(STORE) || "{}"));
    } catch (e) {
      return emptyProgress();
    }
  }

  function save(p) {
    localStorage.setItem(STORE, JSON.stringify(p));
  }

  function catalog() {
    var p = profile();
    var third =
      p.goal && !p.file
        ? {
            id: "upload_doc",
            title: "先上传一份学习资料",
            desc: "有资料才能从里面提取题目。没有也没关系，随时可以补。",
            href: "upload.html",
            action: "去上传",
            mins: 8,
            checker: "uploaded",
          }
        : {
            id: "extract_chapter",
            title: "从资料再提取一章题",
            desc: "目标覆盖还不够。出题就是从资料提取，提完就能刷。",
            href: "generate.html?from=tina",
            action: "去出题",
            mins: 8,
            checker: "extracted",
          };
    return [
      {
        id: "quiz_measure",
        title: "刷 8 道 Widget 相关题",
        desc: "先测量现在卡在哪。对、错、不会都会进 tag，不靠你自己说会了。",
        href: "practice.html",
        action: "去刷题",
        mins: 15,
        checker: "quiz_n",
        need: 8,
      },
      {
        id: "quiz_remediate",
        title: "把 build 里「不会」的 3 题过一遍",
        desc: "今日状态里这个 tag 大约 50%。不要混进正确率里硬刷。",
        href: "practice.html",
        action: "去刷题",
        mins: 10,
        checker: "unknown_n",
        need: 3,
      },
      third,
    ];
  }

  function list() {
    var prog = load();
    return catalog().map(function (t) {
      t.done = !!prog.done[t.id];
      return t;
    });
  }

  function pendingCount() {
    return list().filter(function (t) {
      return !t.done;
    }).length;
  }

  function isUnfamiliar() {
    var prog = load();
    if (prog.hintDismissed) return false;
    return Object.keys(prog.done).length === 0;
  }

  function dismissHint() {
    var prog = load();
    prog.hintDismissed = true;
    save(prog);
  }

  function ensureLayer() {
    if (document.getElementById("task-done-layer")) return;
    var layer = document.createElement("div");
    layer.id = "task-done-layer";
    layer.innerHTML =
      '<div class="task-done-card" role="dialog" aria-label="任务完成">' +
      '<div class="task-done-mark">✓</div>' +
      '<p class="text-sm font-semibold mb-1">该任务已经完成！</p>' +
      '<p id="task-done-title" class="text-xs text-secondary-text leading-relaxed"></p>' +
      '<button type="button" id="task-done-ok" class="mt-5 h-8 px-4 rounded-full bg-sage-accent text-white text-xs font-medium">好</button>' +
      "</div>";
    document.body.appendChild(layer);
    function hide() {
      layer.classList.remove("is-on");
    }
    layer.addEventListener("click", function (e) {
      if (e.target === layer) hide();
    });
    layer.querySelector("#task-done-ok").addEventListener("click", hide);
  }

  function showDone(task) {
    ensureLayer();
    var layer = document.getElementById("task-done-layer");
    var title = document.getElementById("task-done-title");
    if (title) title.textContent = task.title;
    layer.classList.add("is-on");
    clearTimeout(showDone._t);
    showDone._t = setTimeout(function () {
      layer.classList.remove("is-on");
    }, 2600);
  }

  function markDone(id, extra) {
    var prog = load();
    if (prog.done[id]) return null;
    var task = catalog().filter(function (t) {
      return t.id === id;
    })[0];
    if (!task) return null;
    if (task.checker === "quiz_n" && prog.quizAnswered < (task.need || 8)) return null;
    if (task.checker === "unknown_n" && prog.unknownAnswered < (task.need || 3)) return null;
    if (task.checker === "uploaded" && !prog.uploaded) return null;
    if (task.checker === "extracted" && !prog.extracted) return null;
    prog.done[id] = extra || { at: Date.now() };
    save(prog);
    return task;
  }

  function evaluate(hint) {
    var newly = [];
    catalog().forEach(function (t) {
      if (hint && t.checker !== hint) return;
      var done = markDone(t.id, { checker: t.checker });
      if (done) newly.push(done);
    });
    newly.forEach(function (t, i) {
      setTimeout(function () {
        showDone(t);
      }, i * 700);
    });
    if (newly.length) renderAll();
    return newly;
  }

  function homeCard(t, i) {
    return (
      '<div class="task-card flex items-center gap-4 bg-white rounded-2xl shadow-soft border border-card-border p-4' +
      (t.done ? " is-done" : "") +
      '">' +
      '<span class="w-8 h-8 rounded-full border border-card-border bg-foggy-bg text-xs font-semibold flex items-center justify-center shrink-0 ' +
      (t.done ? "text-sage-accent" : "text-sage-accent") +
      '">' +
      (t.done ? "✓" : String(i + 1)) +
      "</span>" +
      '<div class="min-w-0 flex-1">' +
      '<p class="text-sm font-semibold">' +
      t.title +
      "</p>" +
      '<p class="text-[11px] text-secondary-text mt-1 leading-relaxed">' +
      t.desc +
      "</p>" +
      '<p class="text-[11px] text-secondary-text mt-1.5">' +
      (t.done ? "已完成" : "约 " + t.mins + " 分钟") +
      "</p></div>" +
      (t.done
        ? '<span class="task-action shrink-0 h-8 px-4 rounded-full text-xs font-medium">已完成</span>'
        : '<a href="' +
          t.href +
          '" class="task-action shrink-0 h-8 px-4 rounded-full bg-sage-accent text-white text-xs font-medium hover:bg-sage-dark">' +
          t.action +
          "</a>") +
      "</div>"
    );
  }

  function railCard(t, i) {
    return (
      '<div class="task-card bg-white border border-card-border rounded-2xl p-3' +
      (t.done ? " is-done" : "") +
      '">' +
      '<div class="flex items-start justify-between gap-2">' +
      '<p class="text-xs font-semibold leading-snug min-w-0">' +
      (t.done ? "✓ " : i + 1 + ". ") +
      t.title +
      "</p>" +
      (t.done
        ? '<span class="task-action shrink-0 h-7 px-3 rounded-full text-[11px] leading-7">已完成</span>'
        : '<a href="' +
          t.href +
          '" class="task-action shrink-0 h-7 px-3 rounded-full bg-sage-accent text-white text-[11px] leading-7 hover:bg-sage-dark">' +
          t.action +
          "</a>") +
      "</div></div>"
    );
  }

  function renderAll() {
    var tasks = list();
    var home = document.getElementById("home-tasks");
    if (home) home.innerHTML = tasks.map(homeCard).join("");
    var count = document.getElementById("home-task-count");
    if (count) {
      var left = pendingCount();
      count.textContent = left ? "还剩 " + left + " 件" : "今天的任务都完成了";
    }
    var rail = document.getElementById("status-task-list");
    if (rail) rail.innerHTML = tasks.map(railCard).join("");
    var pending = document.getElementById("status-pending-count");
    if (pending) pending.textContent = pendingCount() + " 件任务";
    var hint = document.getElementById("tina-hint");
    if (hint) hint.classList.toggle("hidden", !isUnfamiliar());
  }

  function recordQuiz(kind) {
    var prog = load();
    prog.quizAnswered += 1;
    if (kind === "unknown") prog.unknownAnswered += 1;
    save(prog);
    evaluate("quiz_n");
    if (kind === "unknown") evaluate("unknown_n");
    return load();
  }

  function recordUpload(filename) {
    var prog = load();
    prog.uploaded = true;
    save(prog);
    try {
      var p = profile();
      p.file = filename || p.file || "资料.pdf";
      localStorage.setItem("zhixu-profile", JSON.stringify(p));
    } catch (e) {}
    return evaluate("uploaded");
  }

  function recordExtract() {
    var prog = load();
    prog.extracted = true;
    save(prog);
    return evaluate("extracted");
  }

  global.ZhixuTasks = {
    list: list,
    pendingCount: pendingCount,
    isUnfamiliar: isUnfamiliar,
    dismissHint: dismissHint,
    renderAll: renderAll,
    homeCard: homeCard,
    railCard: railCard,
    recordQuiz: recordQuiz,
    recordUpload: recordUpload,
    recordExtract: recordExtract,
    progress: load,
  };

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", ensureLayer);
  } else {
    ensureLayer();
  }
})(window);
