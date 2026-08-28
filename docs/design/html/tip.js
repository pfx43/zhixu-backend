(function () {
  var STORAGE_KEY = "zhixu-tips";
  var DOCS = ["Flutter 核心组件", "Dart 语言导论"];
  var THEMES = ["Widget 生命周期", "State 管理", "InheritedWidget", "异步编程"];
  var TAGS = ["Flutter", "Widget", "build", "刷题"];

  var selectedText = "";
  var selectedTags = ["Flutter"];
  var selectedTheme = THEMES[0];

  function escapeHtml(str) {
    return String(str)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  function loadTips() {
    try {
      return JSON.parse(sessionStorage.getItem(STORAGE_KEY) || "[]");
    } catch (e) {
      return [];
    }
  }

  function saveTips(list) {
    sessionStorage.setItem(STORAGE_KEY, JSON.stringify(list));
  }

  window.ZhixuTips = { load: loadTips, key: STORAGE_KEY };

  function sourceLabel() {
    return document.body.getAttribute("data-tip-source") || "当前页面";
  }

  function defaultDoc() {
    return document.body.getAttribute("data-tip-doc") || DOCS[0];
  }

  function mount() {
    var fab = document.createElement("button");
    fab.id = "tip-fab";
    fab.type = "button";
    fab.innerHTML =
      '<svg fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M11 5H6a2 2 0 00-2 2v11a2 2 0 002 2h11a2 2 0 002-2v-5m-1.414-9.414a2 2 0 112.828 2.828L11.828 15H9v-2.828l8.586-8.586z"></path></svg><span>tip</span>';

    var overlay = document.createElement("div");
    overlay.id = "tip-overlay";
    overlay.innerHTML =
      '<div id="tip-panel" role="dialog" aria-labelledby="tip-title">' +
      "<header><h3 id=\"tip-title\">收入 tip</h3><p>划选的内容会进笔记页的 tip 堆叠，之后可以翻着看。</p></header>" +
      '<div class="tip-body">' +
      '<div><label>划选内容</label><div id="tip-quote"></div></div>' +
      '<div><label for="tip-name">标题</label><input id="tip-name" type="text" maxlength="40"></div>' +
      '<div><label for="tip-doc">关联资料</label><select id="tip-doc"></select></div>' +
      '<div><label>主题</label><div id="tip-themes" class="chip-row"></div></div>' +
      '<div><label>Tag</label><div id="tip-tags" class="chip-row"></div></div>' +
      "</div>" +
      '<footer><button type="button" class="btn-ghost" id="tip-cancel">取消</button>' +
      '<button type="button" class="btn-go" id="tip-save">收入 tip</button></footer>' +
      "</div>";

    document.body.appendChild(fab);
    document.body.appendChild(overlay);

    var docSelect = overlay.querySelector("#tip-doc");
    docSelect.innerHTML =
      DOCS.map(function (name) {
        return "<option value=\"" + escapeHtml(name) + "\">" + escapeHtml(name) + "</option>";
      }).join("") + '<option value="">不关联资料</option>';

    overlay.querySelector("#tip-themes").innerHTML = THEMES.map(function (name) {
      return '<button type="button" class="chip" data-theme="' + escapeHtml(name) + '">' + escapeHtml(name) + "</button>";
    }).join("");

    overlay.querySelector("#tip-tags").innerHTML = TAGS.map(function (name) {
      return '<button type="button" class="chip" data-tag="' + escapeHtml(name) + '">' + escapeHtml(name) + "</button>";
    }).join("");

    fab.addEventListener("mousedown", function (e) {
      e.preventDefault();
    });
    fab.addEventListener("click", openModal);

    overlay.addEventListener("click", function (e) {
      if (e.target === overlay) closeModal();
    });
    overlay.querySelector("#tip-cancel").addEventListener("click", closeModal);
    overlay.querySelector("#tip-save").addEventListener("click", commit);

    overlay.querySelector("#tip-themes").addEventListener("click", function (e) {
      var btn = e.target.closest("[data-theme]");
      if (!btn) return;
      selectedTheme = btn.getAttribute("data-theme");
      syncChips();
    });
    overlay.querySelector("#tip-tags").addEventListener("click", function (e) {
      var btn = e.target.closest("[data-tag]");
      if (!btn) return;
      var tag = btn.getAttribute("data-tag");
      if (selectedTags.indexOf(tag) >= 0) {
        selectedTags = selectedTags.filter(function (t) {
          return t !== tag;
        });
        if (!selectedTags.length) selectedTags = ["Flutter"];
      } else {
        selectedTags.push(tag);
      }
      syncChips();
    });

    document.addEventListener("mouseup", maybeShow);
    document.addEventListener("keyup", function (e) {
      if (e.key === "Escape") {
        closeModal();
        hideFab();
        return;
      }
      maybeShow();
    });
    document.addEventListener("mousedown", function (e) {
      if (e.target.closest("#tip-fab, #tip-overlay, #app-sidebar")) return;
      window.setTimeout(function () {
        if (!window.getSelection().toString().trim()) hideFab();
      }, 0);
    });
    document.addEventListener("scroll", hideFab, true);

    function syncChips() {
      overlay.querySelectorAll("[data-theme]").forEach(function (el) {
        el.classList.toggle("is-on", el.getAttribute("data-theme") === selectedTheme);
      });
      overlay.querySelectorAll("[data-tag]").forEach(function (el) {
        el.classList.toggle("is-on", selectedTags.indexOf(el.getAttribute("data-tag")) >= 0);
      });
    }

    function hideFab() {
      fab.style.display = "none";
    }

    function maybeShow() {
      if (overlay.classList.contains("is-open")) return;
      var sel = window.getSelection();
      if (!sel || sel.isCollapsed || !sel.rangeCount) {
        hideFab();
        return;
      }
      var node = sel.anchorNode && sel.anchorNode.parentElement;
      if (node && node.closest("#app-sidebar, #tip-overlay, input, textarea, select")) {
        hideFab();
        return;
      }
      var text = sel.toString().replace(/\s+/g, " ").trim();
      if (text.length < 4) {
        hideFab();
        return;
      }
      selectedText = text;
      var rect = sel.getRangeAt(0).getBoundingClientRect();
      var top = rect.top - 44;
      if (top < 12) top = rect.bottom + 8;
      fab.style.left = Math.min(Math.max(rect.left + rect.width / 2, 56), window.innerWidth - 56) + "px";
      fab.style.top = top + "px";
      fab.style.display = "inline-flex";
    }

    function guessTitle(text) {
      var clipped = text.length > 16 ? text.slice(0, 16) + "…" : text;
      return "tip · " + clipped;
    }

    function guessTheme(text) {
      if (/Inherited|下传|共享数据/.test(text)) return "InheritedWidget";
      if (/State|状态/.test(text)) return "State 管理";
      if (/Future|async|异步/.test(text)) return "异步编程";
      return "Widget 生命周期";
    }

    function openModal() {
      hideFab();
      overlay.querySelector("#tip-quote").textContent = selectedText;
      overlay.querySelector("#tip-name").value = guessTitle(selectedText);
      overlay.querySelector("#tip-doc").value = defaultDoc();
      selectedTheme = guessTheme(selectedText);
      selectedTags = ["Flutter"];
      if (/Flutter|Widget|build/.test(selectedText)) selectedTags.push("Flutter");
      syncChips();
      overlay.classList.add("is-open");
      overlay.querySelector("#tip-name").focus();
      overlay.querySelector("#tip-name").select();
    }

    function closeModal() {
      overlay.classList.remove("is-open");
    }

    function commit() {
      var title = overlay.querySelector("#tip-name").value.trim() || guessTitle(selectedText);
      var doc = overlay.querySelector("#tip-doc").value;
      var tip = {
        id: "tip-" + Date.now(),
        title: title,
        content: selectedText,
        doc: doc,
        theme: selectedTheme,
        tags: selectedTags.slice(),
        source: sourceLabel(),
        createdAt: Date.now(),
      };
      var list = loadTips();
      list.unshift(tip);
      saveTips(list);
      window.location.href = "notes.html#tips";
    }
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", mount);
  } else {
    mount();
  }
})();
