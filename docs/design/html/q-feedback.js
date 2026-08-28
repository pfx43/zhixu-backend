(function () {
  var overlay = document.createElement("div");
  overlay.id = "q-feedback-overlay";
  overlay.innerHTML =
    '<div class="q-feedback-panel" role="dialog">' +
    "<header><h3>这题不对</h3><p>提取出来的题如果有问题，反馈后这题暂时不计入 tag 统计。</p></header>" +
    '<div class="q-feedback-body">' +
    '<label>哪里不对</label>' +
    '<div class="chip-row">' +
    '<button type="button" class="chip is-on" data-reason="题干有误">题干有误</button>' +
    '<button type="button" class="chip" data-reason="答案或解析不对">答案或解析不对</button>' +
    '<button type="button" class="chip" data-reason="和资料对不上">和资料对不上</button>' +
    '<button type="button" class="chip" data-reason="其他">其他</button>' +
    "</div>" +
    '<label for="q-feedback-note">补充（选填）</label>' +
    '<textarea id="q-feedback-note" rows="3" placeholder="比如：原文没有这个说法，或选项 B 才对。"></textarea>' +
    "</div>" +
    '<footer><button type="button" class="btn-ghost" id="q-feedback-cancel">取消</button>' +
    '<button type="button" class="btn-go" id="q-feedback-send">提交反馈</button></footer>' +
    "</div>";
  document.body.appendChild(overlay);

  var reason = "题干有误";
  overlay.querySelector(".chip-row").addEventListener("click", function (e) {
    var chip = e.target.closest("[data-reason]");
    if (!chip) return;
    reason = chip.getAttribute("data-reason");
    overlay.querySelectorAll(".chip").forEach(function (el) {
      el.classList.toggle("is-on", el === chip);
    });
  });

  function open() {
    overlay.classList.add("is-open");
  }
  function close() {
    overlay.classList.remove("is-open");
  }

  overlay.addEventListener("click", function (e) {
    if (e.target === overlay) close();
  });
  overlay.querySelector("#q-feedback-cancel").addEventListener("click", close);
  overlay.querySelector("#q-feedback-send").addEventListener("click", function () {
    close();
    var done = document.getElementById("q-feedback-done");
    if (done) {
      done.hidden = false;
      var btn = document.getElementById("q-feedback-open");
      if (btn) btn.hidden = true;
    }
  });

  document.addEventListener("click", function (e) {
    var btn = e.target.closest("[data-q-feedback]");
    if (btn) open();
  });
})();
