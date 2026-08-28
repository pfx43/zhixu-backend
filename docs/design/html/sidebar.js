(function () {
  var KEY = "zhixu-sidebar-collapsed";
  var aside = document.getElementById("app-sidebar");
  if (!aside) return;

  var brand = aside.firstElementChild;
  if (brand) {
    brand.classList.add("brand-block");
    var brandText = brand.querySelector("div:last-child");
    if (brandText) brandText.classList.add("brand-text");
  }

  aside.querySelectorAll(":scope > nav p").forEach(function (p) {
    p.classList.add("nav-group-title");
  });

  aside.querySelectorAll(":scope > nav a").forEach(function (a) {
    var label = (a.textContent || "").replace(/\s+/g, " ").trim();
    if (label) a.title = label;
  });

  var user = aside.querySelector(":scope > .border-t, :scope > [class*='border-t']");
  if (user) {
    user.classList.add("user-footer");
    var name = Array.prototype.find.call(user.querySelectorAll("p"), function (p) {
      return p.textContent.trim() === "啊噗";
    });
    if (name && name.parentElement) name.parentElement.classList.add("user-meta");
    var extra = user.querySelector("button");
    if (extra) extra.classList.add("user-extra");
  }

  var btn = document.getElementById("sidebar-toggle");
  if (!btn) {
    btn = document.createElement("button");
    btn.id = "sidebar-toggle";
    btn.type = "button";
    btn.innerHTML = '<svg fill="none" stroke="currentColor" viewBox="0 0 24 24"><path d="M15 19l-7-7 7-7" stroke-linecap="round" stroke-linejoin="round" stroke-width="2"></path></svg>';
    aside.appendChild(btn);
  }

  function apply(collapsed) {
    aside.classList.toggle("is-collapsed", collapsed);
    btn.setAttribute("aria-expanded", collapsed ? "false" : "true");
    btn.title = collapsed ? "展开侧栏" : "收起侧栏";
    btn.setAttribute("aria-label", btn.title);
  }

  apply(localStorage.getItem(KEY) === "1");
  btn.addEventListener("click", function () {
    var next = !aside.classList.contains("is-collapsed");
    localStorage.setItem(KEY, next ? "1" : "0");
    apply(next);
  });
})();
