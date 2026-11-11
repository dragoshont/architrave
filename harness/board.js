/* Presentation preferences only. This file never writes project state or invokes an agent. */
(() => {
  "use strict";
  const byId = id => document.getElementById(id);
  const body = document.body;
  const inspectors = [...document.querySelectorAll("[data-inspector]")];
  const taskLinks = [...document.querySelectorAll("[data-task]")];
  const key = "architrave-board:" + body.dataset.project + ":" + body.dataset.scope;
  const status = byId("client-status");
  let saved = {}, selected = null, paused = false, timer = null;
  try {
    const parsed = JSON.parse(sessionStorage.getItem(key) || "{}");
    if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) throw Error("Invalid view preferences");
    saved = parsed;
  }
  catch { status.textContent = "View preferences unavailable. Task facts are still readable."; }
  const store = extra => {
    const prefs = {search: byId("task-search").value, filter: byId("task-filter").value,
      selected, paused, list: byId("task-groups").classList.contains("list-mode"),
      theme: document.documentElement.dataset.theme, scroll: window.scrollY,
      focus: document.activeElement.id, ...extra};
    try { sessionStorage.setItem(key, JSON.stringify(prefs)); }
    catch { status.textContent = "View preferences could not be retained across refresh."; }
  };
  function choose(id) {
    const match = inspectors.find(node => node.dataset.inspector === id);
    if (!match) return false;
    selected = id;
    for (const node of inspectors) { node.hidden = node !== match; node.open = node === match; }
    for (const link of taskLinks) {
      if (link.dataset.task === id) link.setAttribute("aria-current", "true");
      else link.removeAttribute("aria-current");
    }
    return true;
  }
  function filter() {
    const query = byId("task-search").value.toLowerCase();
    const value = byId("task-filter").value;
    const visible = new Set();
    for (const link of taskLinks) {
      const stateMatch = value === "all" || value === "attention" && link.dataset.attention === "yes" ||
        value === "deferred" && link.dataset.disposition === "deferred" || value === link.dataset.progress;
      link.hidden = !stateMatch || !link.dataset.search.includes(query);
      if (!link.hidden) visible.add(link.dataset.task);
    }
    for (const group of document.querySelectorAll(".goal-group"))
      group.hidden = ![...group.querySelectorAll("[data-task]")].some(link => !link.hidden);
    byId("no-matches").hidden = visible.size > 0;
    byId("visible-count").textContent = visible.size + " visible";
    if (visible.size && !visible.has(selected)) choose([...visible][0]);
    byId("task-inspectors").hidden = !visible.size;
    store();
  }
  for (const link of [...taskLinks, ...document.querySelectorAll("[data-select]")])
    link.addEventListener("click", event => {
      const id = link.dataset.task || link.dataset.select;
      if (choose(id)) {
        event.preventDefault();
        history.replaceState(null, "", "#task-" + encodeURIComponent(id));
        const heading = inspectors.find(node => node.dataset.inspector === id).querySelector("h3");
        heading.focus();
        store();
      }
    });
  byId("task-search").value = typeof saved.search === "string" ? saved.search : "";
  if ([...byId("task-filter").options].some(o => o.value === saved.filter)) byId("task-filter").value = saved.filter;
  byId("task-search").addEventListener("input", filter);
  byId("task-filter").addEventListener("change", filter);
  function listMode(enabled) {
    byId("task-groups").classList.toggle("list-mode", enabled);
    byId("list-toggle").setAttribute("aria-pressed", String(enabled));
    byId("list-toggle").textContent = enabled ? "Map view" : "List view";
  }
  byId("list-toggle").onclick = () => {listMode(!byId("task-groups").classList.contains("list-mode")); store();};
  function theme(value) {
    document.documentElement.dataset.theme = value === "light" ? "light" : "dark";
    byId("theme-toggle").textContent = value === "light" ? "Dark theme" : "Light theme";
    document.querySelector('meta[name="theme-color"]').content = value === "light" ? "#f4f6f8" : "#10161e";
  }
  byId("theme-toggle").onclick = () => {
    theme(document.documentElement.dataset.theme === "light" ? "dark" : "light"); store();
  };
  const interval = Number(body.dataset.refresh);
  paused = saved.paused === true;
  function schedule() {
    clearTimeout(timer);
    byId("pause-updates").textContent = paused ? "Resume updates" : "Pause updates";
    if (!paused && interval > 0) timer = setTimeout(() => {
      const editing = document.activeElement !== document.body && document.activeElement !== document.documentElement;
      const reading = [...document.querySelectorAll("details[open]")].some(node => !node.classList.contains("inspector"));
      if (document.hidden || editing || reading || String(window.getSelection()).length) {
        status.textContent = "Refresh due. Your reading position is retained; use Refresh snapshot when ready.";
        schedule();
      } else { store(); location.reload(); }
    }, interval * 1000);
  }
  byId("refresh-now").onclick = () => {store(); location.reload();};
  byId("pause-updates").hidden = interval <= 0;
  byId("pause-updates").onclick = () => {
    paused = !paused;
    status.textContent = paused ? "Display updates paused. Work, ownership and collection are unchanged." : "Display updates resumed.";
    store(); schedule();
  };
  function freshness() {
    const generated = Date.parse(body.dataset.generated);
    if (interval > 0 && Date.now() - generated > (2 * interval + 60) * 1000) {
      byId("freshness").classList.add("stale");
      byId("freshness").textContent = "STALE: refresh overdue; watcher may have stopped. The retained revision is not a live observation.";
    }
    for (const node of document.querySelectorAll("[data-observed]")) {
      const time = Date.parse(node.dataset.observed);
      if (!Number.isFinite(time) || Date.now() < time || Date.now() - time > 120000) {
        node.classList.add("stale-observation");
        node.title = "Last recorded activity only; current activity is unknown.";
      }
    }
  }
  document.documentElement.classList.add("enhanced");
  let hashId = null;
  try { hashId = decodeURIComponent(location.hash.replace(/^#task-/, "")); }
  catch { status.textContent = "Task link is invalid. Select a task from this scope."; }
  choose(hashId) || choose(saved.selected) || (inspectors.length && choose(inspectors[0].dataset.inspector));
  listMode(saved.list === true); theme(saved.theme); filter(); schedule(); freshness();
  if (Number.isFinite(saved.scroll)) requestAnimationFrame(() => window.scrollTo(0, saved.scroll));
  if (typeof saved.focus === "string" && saved.focus) {
    const focused = document.getElementById(saved.focus);
    if (focused && !focused.closest("[hidden]")) focused.focus({preventScroll: true});
  }
  setInterval(freshness, 1000);
  window.addEventListener("pagehide", () => {clearTimeout(timer); store();});
})();
