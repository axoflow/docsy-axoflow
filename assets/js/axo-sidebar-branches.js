// Unfolding a branch of the compact sidebar that the page does not carry.
//
// With `sidebar_menu_compact`, the page renders only the branches on the way to
// the current page (layouts/_partials/sidebar-tree-section.html); every other
// branch is an empty `<ul data-axo-branch>` under its heading and fold
// checkbox, named by its row's id (`<id>-li`). Its rows are in the chapter's
// branch file, which `data-axo-branches` on the chapter's row names: one
// <template data-for="<id>"> per branch. Opening the checkbox fills the list in; the stylesheet's own
// `input:checked ~ ul` rule shows it, so nothing here draws anything.
//
// The rows in a template are one level deep and their own branches are
// placeholders again, so each branch is stored once; `fill` walks down and
// fills them from the same file straight away, and a filled branch folds and
// unfolds like any other from then on.
//
// The current chapter's file is fetched when the browser is idle, and another
// chapter's when the pointer first moves over it, so a click almost never
// waits. Without the script, the heading is still a link to the branch's page.

const nav = document.getElementById('td-section-nav');
const files = new Map();

function load(url) {
  if (!files.has(url)) {
    files.set(url, fetch(url)
      .then((response) => (response.ok ? response.text() : Promise.reject(response.status)))
      .then((html) => new DOMParser().parseFromString(html, 'text/html'))
      // Forget a failed fetch, so the next attempt tries again.
      .catch((error) => { files.delete(url); throw error; }));
  }
  return files.get(url);
}

function fill(list, doc) {
  const id = list.parentElement.id.replace(/-li$/, '');
  const template = doc.querySelector(`template[data-for="${id}"]`);
  if (!template) return;
  list.removeAttribute('data-axo-branch');
  list.append(document.importNode(template.content, true));
  list.querySelectorAll('ul[data-axo-branch]').forEach((inner) => fill(inner, doc));
}

function sourceOf(element) {
  const chapter = element.closest('[data-axo-branches]');
  return chapter && chapter.dataset.axoBranches;
}

if (nav) {
  nav.addEventListener('change', (event) => {
    const box = event.target;
    if (box.type !== 'checkbox' || !box.checked) return;
    const list = box.parentElement.querySelector(':scope > ul[data-axo-branch]');
    const url = list && sourceOf(list);
    if (url) load(url).then((doc) => fill(list, doc)).catch(() => {});
  });

  nav.addEventListener('pointerover', (event) => {
    const url = sourceOf(event.target);
    if (url) load(url).catch(() => {});
  }, { passive: true });

  const current = nav.querySelector('.active-path[data-axo-branches]');
  if (current) {
    (window.requestIdleCallback || ((fn) => window.setTimeout(fn, 200)))(() =>
      load(current.dataset.axoBranches).catch(() => {}));
  }
}
