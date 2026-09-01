// The full label on hover, but only where the row had to cut it.
//
// The trail clips in CSS rather than in the template, so the whole label is
// already in the DOM and a screen reader reads it in full -- what a pointer user
// loses is the part past the ellipsis. This puts that part back as the native
// tooltip, and only on the items that are actually cut: a tooltip repeating a
// label already fully on screen is noise.
//
// A ResizeObserver on the list rather than a `resize` listener on the window,
// because three things change this row's width and only one of them fires
// `resize`: the window, `axo-wide.js` toggling `data-axo-wide` on <html>, and the
// webfont landing and re-measuring the text. The observer sees all three.
//
// `title` is deliberately native. It has the browser's ~1s delay and no
// keyboard or touch equivalent -- stated rather than worked around, because a
// custom tooltip would need focus handling, dismissal and a live region to be
// worth more than this, and the label is not the only way to the parent page:
// the crumb is a link, and the navigation column holds the same ancestry.
(function () {
    'use strict';

    var nav = document.querySelector('.td-main .td-breadcrumbs');
    if (!nav) {
        return;
    }
    var list = nav.querySelector('.breadcrumb');
    if (!list) {
        return;
    }

    // The icon crumb has no text to cut, and its `<a>` is `overflow: visible`.
    var links = Array.prototype.filter.call(
        nav.querySelectorAll('.breadcrumb-item > a'),
        function (a) {
            return !a.parentNode.classList.contains('breadcrumb-item--icon');
        }
    );
    if (!links.length) {
        return;
    }

    function sync() {
        links.forEach(function (a) {
            // 1px of slack: sub-pixel text metrics make scrollWidth exceed
            // clientWidth by a fraction on rows that are not actually cut.
            if (a.scrollWidth > a.clientWidth + 1) {
                var full = a.textContent.trim();
                if (a.getAttribute('title') !== full) {
                    a.setAttribute('title', full);
                }
            } else if (a.hasAttribute('title')) {
                // Idempotent: a row that stops clipping loses the tooltip again.
                a.removeAttribute('title');
            }
        });
    }

    sync();

    if (typeof ResizeObserver === 'function') {
        new ResizeObserver(sync).observe(list);
    } else {
        window.addEventListener('resize', sync);
    }

    if (document.fonts && document.fonts.ready) {
        document.fonts.ready.then(sync);
    }
}());
