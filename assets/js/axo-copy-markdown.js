// "Copy page as Markdown" in the page actions (page-meta-links.html).
//
// The control is a link to the page's Markdown copy, so without this script it
// still opens the Markdown. With it, a click fetches that file and puts it on
// the clipboard instead.
//
// The fetch runs inside a `ClipboardItem` promise rather than before
// `writeText`: Safari drops the user gesture across an `await`, and then refuses
// the write. Browsers without `ClipboardItem` get the fetch-then-writeText path.
//
// `hugo server` has no Markdown copies (hugo_to_markdown.py makes them after the
// build), so there the control reports "Copy failed".

(function () {
  function fetchText(url) {
    return fetch(url, { credentials: 'same-origin' }).then(function (res) {
      if (!res.ok) throw new Error(res.status);
      return res.text();
    });
  }

  function copy(url) {
    if (window.ClipboardItem && navigator.clipboard && navigator.clipboard.write) {
      var blob = fetchText(url).then(function (t) {
        return new Blob([t], { type: 'text/plain' });
      });
      return navigator.clipboard.write([new ClipboardItem({ 'text/plain': blob })]);
    }
    if (navigator.clipboard && navigator.clipboard.writeText) {
      return fetchText(url).then(function (t) {
        return navigator.clipboard.writeText(t);
      });
    }
    return Promise.reject(new Error('no clipboard'));
  }

  function attach(link) {
    var label = link.querySelector('span');
    if (!label) return;
    var original = label.textContent;

    var live = document.createElement('span');
    live.className = 'visually-hidden';
    live.setAttribute('aria-live', 'polite');
    link.parentNode.insertBefore(live, link.nextSibling);

    var timer;
    function show(text) {
      label.textContent = text;
      live.textContent = text;
      clearTimeout(timer);
      timer = setTimeout(function () {
        label.textContent = original;
        live.textContent = '';
      }, 2000);
    }

    link.addEventListener('click', function (e) {
      // Keep modified clicks (new tab, save link) doing what links do.
      if (e.button !== 0 || e.metaKey || e.ctrlKey || e.shiftKey || e.altKey) return;
      e.preventDefault();
      copy(link.href).then(
        function () { show(link.dataset.copiedLabel); },
        function () { show(link.dataset.failedLabel); }
      );
    });
  }

  function start() {
    var links = document.querySelectorAll('[data-axo-copy-markdown]');
    Array.prototype.forEach.call(links, attach);
  }

  if (document.readyState === 'loading') {
    window.addEventListener('DOMContentLoaded', start);
  } else {
    start();
  }
})();
