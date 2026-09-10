/*
 * Measures the marketing chrome's rendered geometry and type, on axoflow.com or
 * on this documentation site, and prints one JSON object per menu.
 *
 * Paste into the DevTools console on BOTH sites at the SAME window width, save
 * both outputs, and diff them. It reports boxes and type — not selectors and not
 * declarations — because that is the only thing the two sides have in common:
 * they reproduce the same panel with deliberately different mechanisms (live's
 * 1px rule is its own grid track, ours is a border; live's dark fill is
 * `:last-child`, ours is a named column), and a comparison of CSS text calls
 * every one of those a difference while a comparison of boxes does not.
 *
 * THREE THINGS ARE NORMALIZED so the two sides are comparable at all. Without
 * them the diff is all false positives:
 *
 *   Gaps are measured between CONTENT edges, not border-box edges. Live spends
 *   the gap between two columns as `2rem | 1px divider track | 2rem`; we spend
 *   it as `margin 2rem | border 1px | padding 2rem`. Border-box edges say 65px
 *   against 32px; content edges say 65 against 65, which is the truth.
 *
 *   A SECTION is a heading block and everything under it. Live splits those
 *   into two children of the column (`item-top` then `collection-wrapper`);
 *   ours is one `.axo-nav-group`. Counting children says 2 against 1, so the
 *   profile names what starts a section instead.
 *
 *   A RULE ABOVE A SECTION is a sibling `divider-horizontal` element on live
 *   and a `border-top` on ours. `ruleAbove` asks the question rather than
 *   reading the property.
 *
 * Nothing here writes to the page beyond opening a menu, and every menu it
 * opens it closes again.
 */
(() => {
  'use strict';

  const round = (n) => Math.round(n * 2) / 2; // half-pixel, which is live's own grid

  /* Which site are we on? The docs bar and the marketing bar share no classes,
     which is the whole reason this script exists. */
  const PROFILES = {
    live: {
      bar: '.v3-navbar_component, .v3-navbar_menu',
      megaItem: '.v3-navbar_mega-menu-dropdown',
      megaToggle: '.v3-navbar_mega-dropdown-toggle',
      panel: '.v3-navbar_mega-dropdown-list',
      colsBlock: '.v3-navbar_mega-dropdown-col-right',
      column: '.v3-navbar_mega-dropdown-col',
      highlight: '.v3-navbar_mega-dropdown-col.is-solutions-highlight',
      subcols: '.v3-navbar_mega-dropdown-item-wrapper',
      // A sub-column is an unclassed div in live's wrapper; the heading marks it.
      subcol: '.v3-navbar_mega-dropdown-item-wrapper > div:not([class*="divider"])',
      // What starts a section of a column. Live's heading block and the link
      // collection under it are two siblings; both a heading block and the
      // sub-column wrapper start one.
      section: ':scope > .v3-navbar_mega-dropdown-item-top,'
        + ':scope > .v3-navbar_mega-dropdown-item-wrapper',
      ruleAbove(section) {
        const prev = section.previousElementSibling;
        if (!prev || !/divider-horizontal/.test(prev.className)) return null;
        const s = getComputedStyle(prev);
        return `${s.borderTopWidth} ${s.borderTopColor}`;
      },
      subHeading: '.v2-text-color-tertiary',
      groupTitle: '.v3-navbar_mega-dropdown-item-top .v3-navbar_mega-link',
      groupDesc: '.v3-navbar_mega-dropdown-item-top .text-size-tiny',
      link: 'a.v3-navbar_mega-dropdown_link',
      describedLink: '.v3-navbar_mega-dropdown-item_nested a.v3-navbar_mega-link',
      linkDesc: '.v3-navbar_mega-dropdown-item_nested .text-size-tiny',
      banner: '.v2-banner_component',
      footerColumn: '.v3-footer_row-1_column',
      open(item) {
        const toggle = item.querySelector(this.megaToggle);
        if (!toggle) return false;
        toggle.click();
        const list = item.querySelector(this.panel);
        if (list && !list.classList.contains('w--open')) {
          // Webflow opens on hover as well as click; if neither took, set the
          // state it would have set. Same computed styles either way.
          toggle.classList.add('w--open');
          list.classList.add('w--open');
        }
        return true;
      },
      close(item) {
        const toggle = item.querySelector(this.megaToggle);
        const list = item.querySelector(this.panel);
        if (toggle) toggle.classList.remove('w--open');
        if (list) list.classList.remove('w--open');
      },
    },
    docs: {
      bar: 'nav.td-navbar',
      megaItem: '.axo-nav--bar .axo-nav-item:has(.axo-nav-panel--mega)',
      megaToggle: '.axo-nav-toggle',
      panel: '.axo-nav-panel--mega',
      colsBlock: '.axo-nav-cols',
      column: '.axo-nav-col',
      highlight: '.axo-nav-col--highlight',
      subcols: '.axo-nav-subcols',
      subcol: '.axo-nav-subcol',
      section: ':scope > .axo-nav-group, :scope > .axo-nav-subcols',
      ruleAbove(section) {
        const s = getComputedStyle(section);
        return parseFloat(s.borderTopWidth)
          ? `${s.borderTopWidth} ${s.borderTopColor}` : null;
      },
      subHeading: '.axo-nav-group-title',
      groupTitle: '.axo-nav-group-title',
      groupDesc: '.axo-nav-group-desc',
      link: '.axo-nav-links a',
      describedLink: 'li:has(.axo-nav-link-desc) a',
      linkDesc: '.axo-nav-link-desc',
      banner: '.axo-announcement',
      footerColumn: '.td-footer__column',
      open(item) {
        const toggle = item.querySelector(this.megaToggle);
        if (!toggle) return false;
        // `aria-expanded` is the whole of the state — see the note in
        // assets/js/axo-navbar.js — so this needs no script on the page.
        toggle.setAttribute('aria-expanded', 'true');
        return true;
      },
      close(item) {
        const toggle = item.querySelector(this.megaToggle);
        if (toggle) toggle.setAttribute('aria-expanded', 'false');
      },
    },
  };

  const site = document.querySelector(PROFILES.live.megaItem) ? 'live'
    : document.querySelector('nav.td-navbar') ? 'docs' : null;
  if (!site) {
    console.error('chrome-parity: neither the marketing bar nor the docs bar is '
      + 'on this page. Open axoflow.com or the local docs site.');
    return;
  }
  const P = PROFILES[site];
  const missing = [];

  /* ---------------------------------------------------------------- helpers */

  const box = (el, origin) => {
    if (!el) return null;
    const r = el.getBoundingClientRect();
    return {
      // Relative to the panel, so the page's own gutters and the scrollbar do
      // not enter into it.
      x: round(r.left - (origin ? origin.left : 0)),
      right: round(r.right - (origin ? origin.left : 0)),
      w: round(r.width),
      h: round(r.height),
    };
  };

  /* The content box, which is what makes the two sides comparable: see the
     note at the top about where each spends the gap between two columns. */
  const content = (el, origin) => {
    if (!el) return null;
    const r = el.getBoundingClientRect();
    const s = getComputedStyle(el);
    const left = parseFloat(s.paddingLeft) + parseFloat(s.borderLeftWidth);
    const right = parseFloat(s.paddingRight) + parseFloat(s.borderRightWidth);
    const base = origin ? origin.left : 0;
    return {
      x: round(r.left + left - base),
      right: round(r.right - right - base),
      w: round(r.width - left - right),
    };
  };

  const gap = (a, b, origin) => {
    if (!a || !b) return null;
    return round(content(b, origin).x - content(a, origin).right);
  };

  const type = (el) => {
    if (!el) return null;
    const s = getComputedStyle(el);
    return {
      fontSize: s.fontSize,
      fontWeight: s.fontWeight,
      lineHeight: s.lineHeight,
      color: s.color,
    };
  };

  const edges = (el) => {
    if (!el) return null;
    const s = getComputedStyle(el);
    const pick = (v) => (parseFloat(v) ? v : null);
    return {
      padding: [s.paddingTop, s.paddingRight, s.paddingBottom, s.paddingLeft]
        .map((v) => round(parseFloat(v))).join(' '),
      borderTop: pick(s.borderTopWidth) && `${s.borderTopWidth} ${s.borderTopColor}`,
      borderLeft: pick(s.borderLeftWidth) && `${s.borderLeftWidth} ${s.borderLeftColor}`,
      background: s.backgroundColor === 'rgba(0, 0, 0, 0)' ? null : s.backgroundColor,
    };
  };

  const need = (el, what) => {
    if (!el) missing.push(what);
    return el;
  };

  /* The y-distance between consecutive rows of a link list: the rhythm the
     stylesheet's comments quote ("37.2px centres"), and the thing most likely
     to drift by a few pixels without anyone noticing. */
  const pitch = (nodes) => {
    const tops = nodes.map((n) => n.getBoundingClientRect().top);
    const deltas = tops.slice(1).map((t, i) => round(t - tops[i]));
    return deltas.length ? deltas : null;
  };

  /* ------------------------------------------------------------------- menus */

  const measureColumn = (col, origin) => {
    const sections = Array.from(col.querySelectorAll(P.section))
      .filter((s) => s.offsetHeight || s.offsetWidth);

    const subcolsEl = col.querySelector(P.subcols);
    const subcolEls = subcolsEl
      ? Array.from(subcolsEl.querySelectorAll(P.subcol))
        .filter((el) => el.querySelector(P.subHeading) || el.querySelector(P.link)
          || el.querySelector(P.describedLink))
      : [];

    return {
      title: (col.querySelector(P.groupTitle)?.textContent || '').trim(),
      box: box(col, origin),
      content: content(col, origin),
      edges: edges(col),
      // A section is a heading block and what hangs under it, per the profile —
      // not a child count, which the two sides do not agree on. A column that
      // gained or lost one shows up here before it shows up in a screenshot.
      sectionCount: sections.length,
      sectionTops: sections.map(
        (s) => round(s.getBoundingClientRect().top - origin.top)),
      sectionRules: sections.map((s) => P.ruleAbove(s)),
      titleType: type(col.querySelector(P.groupTitle)),
      descType: type(col.querySelector(P.groupDesc)),
      linkType: type(col.querySelector(P.link)),
      linkPitch: pitch(Array.from(col.querySelectorAll(P.link)).slice(0, 4)),
      describedLinkType: type(col.querySelector(P.describedLink)),
      linkDescType: type(col.querySelector(P.linkDesc)),
      subcols: subcolEls.length ? subcolEls.map((el) => ({
        heading: (el.querySelector(P.subHeading)?.textContent || '').trim(),
        headingType: type(el.querySelector(P.subHeading)),
        content: content(el, origin),
        rowPitch: pitch(Array.from(
          el.querySelectorAll(`${P.describedLink}, ${P.link}`)).slice(0, 3)),
      })) : null,
      subcolGap: subcolEls.length > 1
        ? gap(subcolEls[0], subcolEls[1], origin) : null,
    };
  };

  const results = { site, viewport: `${window.innerWidth}x${window.innerHeight}`, menus: [] };

  document.querySelectorAll(P.megaItem).forEach((item) => {
    const name = (item.querySelector(P.megaToggle)?.textContent || '').trim()
      .split('\n')[0];
    if (!P.open(item)) return;
    const panel = need(item.querySelector(P.panel), `panel for "${name}"`);
    if (!panel) { P.close(item); return; }

    const origin = panel.getBoundingClientRect();
    const colsBlock = item.querySelector(P.colsBlock);
    const highlight = item.querySelector(P.highlight);
    const columns = Array.from(item.querySelectorAll(P.column))
      .filter((c) => c !== highlight);

    results.menus.push({
      name,
      panel: { box: box(panel, origin), edges: edges(panel) },
      columnsBlock: colsBlock
        ? {
          box: box(colsBlock, origin),
          content: content(colsBlock, origin),
          edges: edges(colsBlock),
        } : null,
      columnGap: columns.length > 1 ? gap(columns[0], columns[1], origin) : null,
      columns: columns.map((c) => measureColumn(c, origin)),
      highlight: highlight ? measureColumn(highlight, origin) : null,
      // The dark column as a share of the panel: live's is 25% on the nose.
      highlightShare: highlight
        ? `${round((highlight.getBoundingClientRect().width / origin.width) * 1000) / 10}%`
        : null,
    });
    P.close(item);
  });

  /* -------------------------------------------------------- the rest of it */

  const banner = document.querySelector(P.banner);
  results.banner = banner
    ? { box: box(banner), edges: edges(banner), type: type(banner.querySelector('a') || banner) }
    : null;

  const footerColumns = Array.from(document.querySelectorAll(P.footerColumn));
  results.footer = footerColumns.length ? {
    columnCount: footerColumns.length,
    columns: footerColumns.map((c) => box(c)),
    titleType: type(footerColumns[0].querySelector('p, div')),
    linkType: type(footerColumns[0].querySelector('a')),
    linkPitch: pitch(Array.from(footerColumns[0].querySelectorAll('a')).slice(0, 4)),
  } : null;

  results.missing = missing;

  const out = JSON.stringify(results, null, 2);
  console.log(out);
  if (typeof copy === 'function') {
    copy(out);
    console.log('%cCopied to the clipboard. Save it as '
      + `chrome-parity-${site}-${window.innerWidth}.json`, 'font-weight:bold');
  }
  return results;
})();
