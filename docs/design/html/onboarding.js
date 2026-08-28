(function () {
  var thread = document.getElementById("thread");
  var log = document.getElementById("log");
  var form = document.getElementById("composer");
  var input = document.getElementById("input");
  var sendBtn = document.getElementById("send");
  var fileInput = document.getElementById("file");
  var busy = false;
  var phase = "name";
  var profile = { name: "", role: "", goal: "", goalFollow: 0, file: "" };

  var STEPS = [
    { id: "meet", label: "认识你", desc: "名字、职业，先聊起来" },
    { id: "goal", label: "确认学习目标", desc: "工具：确认学习目标" },
    { id: "docs", label: "添加资料", desc: "工具：添加资料" },
    { id: "done", label: "开始使用", desc: "回首页，之后在 Tina 栏找我" },
  ];
  var rail = { meet: "on", goal: "", docs: "", done: "" };

  function renderRail() {
    var nav = document.getElementById("step-nav");
    if (!nav) return;
    nav.innerHTML = STEPS.map(function (s, i) {
      var st = rail[s.id];
      var on = st === "on";
      var mark = st === "done" ? "✓" : st === "skip" ? "–" : String(i + 1);
      return (
        '<li class="step-card flex gap-3 rounded-xl p-3 ' + (on ? "is-on" : "") + '">' +
        '<span class="w-8 h-8 rounded-full border border-card-border bg-white text-xs font-semibold flex items-center justify-center shrink-0 ' +
        (on ? "text-sage-accent" : "text-secondary-text") + '">' + mark + "</span>" +
        '<span><span class="block text-xs font-semibold">' + s.label + "</span>" +
        '<span class="block text-[11px] text-secondary-text mt-0.5">' + s.desc + "</span>" +
        (on && (s.id === "goal" || s.id === "docs")
          ? '<span class="block text-[11px] text-sage-accent mt-0.5">Tina 正在调用工具</span>'
          : on
            ? '<span class="block text-[11px] text-sage-accent mt-0.5">当前</span>'
            : "") +
        (st === "done" ? '<span class="block text-[11px] text-secondary-text mt-0.5">已完成</span>' : "") +
        (st === "skip" ? '<span class="block text-[11px] text-secondary-text mt-0.5">已跳过</span>' : "") +
        "</span></li>"
      );
    }).join("");
  }

  function setRail(id, status) {
    if (status === "on") {
      STEPS.forEach(function (s) {
        if (rail[s.id] === "on") rail[s.id] = "";
      });
    }
    rail[id] = status;
    renderRail();
  }

  function scrollBottom() {
    log.scrollTop = log.scrollHeight;
  }

  function el(html) {
    var wrap = document.createElement("div");
    wrap.innerHTML = html.trim();
    var node = wrap.firstElementChild;
    thread.appendChild(node);
    scrollBottom();
    return node;
  }

  function addUser(text) {
    el('<div class="msg-user"></div>').textContent = text;
  }

  function streamTina(text, then) {
    busy = true;
    sendBtn.disabled = true;
    var p = el('<p class="msg-tina is-stream"></p>');
    var i = 0;
    var timer = setInterval(function () {
      i += 1;
      p.textContent = text.slice(0, i);
      scrollBottom();
      if (i >= text.length) {
        clearInterval(timer);
        p.classList.remove("is-stream");
        busy = false;
        sendBtn.disabled = false;
        input.focus();
        if (then) then();
      }
    }, 22);
  }

  function addGoalCard(goal) {
    var card = el(
      '<div class="tool-card">' +
        '<div class="text-[10px] font-semibold tracking-wide text-sage-accent mb-2">Tina 调用工具 · 确认学习目标</div>' +
        '<h4 class="text-sm font-semibold mb-1">是这个目标吗？</h4>' +
        '<p class="text-sm leading-relaxed mb-3" data-goal></p>' +
        '<p class="text-[11px] text-secondary-text mb-4">确认后我会按这个方向帮你排练习、看进度。也可以说得更具体一点。</p>' +
        '<div class="flex flex-wrap gap-2">' +
          '<button type="button" data-act="confirm" class="h-8 px-3 rounded-full bg-sage-accent text-white text-xs">确认，就是这个</button>' +
          '<button type="button" data-act="edit" class="h-8 px-3 rounded-full border border-card-border bg-white text-xs text-secondary-text">还想改一下</button>' +
        "</div></div>"
    );
    card.querySelector("[data-goal]").textContent = goal;
    card.addEventListener("click", function (e) {
      var btn = e.target.closest("[data-act]");
      if (!btn || phase !== "goal-card") return;
      var act = btn.getAttribute("data-act");
      card.querySelectorAll("button").forEach(function (b) { b.disabled = true; });
      if (act === "confirm") {
        phase = "ask-docs";
        saveProfile();
        setRail("goal", "done");
        streamTina(
          "好，目标我记下了。接下来：你手头有学习用的资料吗？讲义、课件、PDF 都可以。有的话我帮你收进资料架，之后可以提取题目。没有也可以先跳过。",
          function () {
            setRail("docs", "on");
            addDocCard();
          }
        );
      } else {
        phase = "goal";
        setRail("goal", "on");
        streamTina("没问题。你再讲一遍：最想先做成哪一件事？时间、程度都可以带上。");
      }
    });
  }

  function addDocCard() {
    var card = el(
      '<div class="tool-card">' +
        '<div class="text-[10px] font-semibold tracking-wide text-sage-accent mb-2">Tina 调用工具 · 添加资料</div>' +
        '<h4 class="text-sm font-semibold mb-1">你有学习使用的资料吗？</h4>' +
        '<p class="text-[11px] text-secondary-text mb-3">拖进来或点选一份。设计稿不会真正传到服务器。</p>' +
        '<div data-drop class="drop-zone">' +
          '<div class="w-10 h-10 rounded-xl bg-[#F3F6F5] text-sage-accent mx-auto mb-2 flex items-center justify-center">' +
            '<svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path d="M7 16a4 4 0 01-.88-7.903A5 5 0 1115.9 6L16 6a5 5 0 011 9.9M15 13l-3-3m0 0l-3 3m3-3v12" stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5"></path></svg>' +
          "</div>" +
          '<p data-drop-title class="text-sm font-medium mb-0.5">把文件拖到这里，或点选上传</p>' +
          '<p data-drop-hint class="text-[11px] text-secondary-text">PDF、TXT、MD、DOCX</p>' +
        "</div>" +
        '<button type="button" data-act="skip" class="mt-3 h-8 px-3 rounded-full border border-card-border bg-white text-xs text-secondary-text">先跳过</button>' +
      "</div>"
    );
    var drop = card.querySelector("[data-drop]");
    var title = card.querySelector("[data-drop-title]");
    var hint = card.querySelector("[data-drop-hint]");
    var skip = card.querySelector("[data-act=skip]");
    var used = false;

    function takeFile(f) {
      if (used || phase !== "ask-docs" || !f) return;
      used = true;
      profile.file = f.name;
      drop.classList.remove("is-over");
      drop.classList.add("is-done");
      title.textContent = f.name;
      hint.textContent = "已选择（演示，未上传）";
      skip.disabled = true;
      finishOnboard("收到了。这份资料会留在对话记录里，之后可以在资料页继续处理。", "done");
    }

    drop.addEventListener("click", function () {
      if (used || phase !== "ask-docs") return;
      fileInput.click();
    });
    fileInput.onchange = function () {
      takeFile(fileInput.files && fileInput.files[0]);
    };
    ["dragenter", "dragover"].forEach(function (ev) {
      drop.addEventListener(ev, function (e) {
        e.preventDefault();
        e.stopPropagation();
        if (!used) drop.classList.add("is-over");
      });
    });
    ["dragleave", "drop"].forEach(function (ev) {
      drop.addEventListener(ev, function (e) {
        e.preventDefault();
        e.stopPropagation();
        drop.classList.remove("is-over");
      });
    });
    drop.addEventListener("drop", function (e) {
      var files = e.dataTransfer && e.dataTransfer.files;
      takeFile(files && files[0]);
    });
    skip.addEventListener("click", function () {
      if (used || phase !== "ask-docs") return;
      used = true;
      skip.disabled = true;
      finishOnboard("好，先不传也行。资料随时可以补。", "skip");
    });
  }

  function addLeaveButton() {
    if (document.getElementById("leave-chat")) return;
    var wrap = el(
      '<div id="leave-chat">' +
        '<button type="button" class="h-8 px-4 rounded-full bg-sage-accent text-white text-xs font-medium hover:bg-sage-dark">不想聊了</button>' +
      "</div>"
    );
    wrap.querySelector("button").addEventListener("click", function () {
      wrap.querySelector("button").disabled = true;
      phase = "leaving";
      setRail("done", "on");
      streamTina("好。我们先回首页，以后可以在 Tina 这个栏找到我哦。", function () {
        setRail("done", "done");
        el('<a href="index.html" class="inline-flex h-8 px-4 rounded-full bg-sage-accent text-white text-xs items-center w-fit">去首页</a>');
        setTimeout(function () {
          window.location.href = "index.html";
        }, 1800);
      });
    });
  }

  function saveProfile() {
    try {
      localStorage.setItem("zhixu-profile", JSON.stringify({
        name: profile.name || "",
        role: profile.role || "",
        goal: profile.goal || "",
        file: profile.file || "",
      }));
    } catch (e) {}
  }

  function finishOnboard(lead, docsStatus) {
    localStorage.setItem("zhixu-onboarding-done", "1");
    saveProfile();
    phase = "free";
    setRail("docs", docsStatus || "done");
    setRail("done", "on");
    streamTina(
      lead +
        " 引导这部分就够了。后面你说的话都会留在这条对话里。现在还可以继续问我，不想聊了也可以说一声。",
      addLeaveButton
    );
  }

  function onUser(text) {
    if (busy || !text) return;
    addUser(text);

    if (phase === "name") {
      profile.name = text;
      phase = "role";
      streamTina("你好，" + text + "。你的性别和当前职业是？比如：女，大二学生 / 男，前端实习生。");
      return;
    }
    if (phase === "role") {
      profile.role = text;
      phase = "goal";
      setRail("meet", "on");
      streamTina(
        "记下了。那现在最想实现的目标是什么呢？不用一次说得很完整。先说你最近真正卡着、或最想先做成的那一件事就行，我帮你收成一句能盯着的目标。"
      );
      return;
    }
    if (phase === "goal") {
      profile.goal = text;
      profile.goalFollow += 1;
      if (profile.goalFollow < 2 && text.length < 18) {
        streamTina(
          "这个方向很好。能再具体一点吗？比如想在什么时候、达到什么程度？有一本书或一门课也可以说。"
        );
        return;
      }
      phase = "goal-card";
      streamTina("我把它收成下面这张目标卡片。对的话确认，不对就改。", function () {
        setRail("meet", "done");
        setRail("goal", "on");
        addGoalCard(profile.goal);
      });
      return;
    }
    if (phase === "goal-card") {
      profile.goal = text;
      streamTina("按你刚说的更新了。看这张还对不对。", function () {
        setRail("goal", "on");
        addGoalCard(profile.goal);
      });
      return;
    }
    if (phase === "ask-docs") {
      streamTina("资料可以拖进下面那块区域，也可以点它选文件。不想传就点跳过。");
      return;
    }
    if (phase === "free") {
      if (/不想聊/.test(text)) {
        document.querySelector("#leave-chat button")?.click();
        return;
      }
      streamTina(
        "这段会留在聊天记录里。正式产品里我会按你确认过的目标来建议下一步。不想聊了可以点下面的按钮。"
      );
    }
  }

  form.addEventListener("submit", function (e) {
    e.preventDefault();
    var text = input.value.trim();
    if (!text || busy) return;
    input.value = "";
    onUser(text);
  });
  input.addEventListener("keydown", function (e) {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      form.requestSubmit();
    }
  });

  phase = "name";
  renderRail();
  streamTina(
    "欢迎来到知序。为了更好地服务你，接下来我会问你几个问题。\n\n你的名字是？"
  );
})();
