/* 高动效版 · 壳层交互
   只做渐进增强，内容在无 JS / 减少动态效果时始终可见。 */
(function () {
  var root = document.documentElement;
  var reduced = false;
  try {
    reduced = window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  } catch (e) {}

  function $(sel, ctx) { return (ctx || document).querySelector(sel); }
  function $$(sel, ctx) { return Array.prototype.slice.call((ctx || document).querySelectorAll(sel)); }
  function raf(fn) { return window.requestAnimationFrame ? requestAnimationFrame(fn) : setTimeout(fn, 16); }
  function clamp(v, min, max) { return Math.min(max, Math.max(min, v)); }

  /* ---------- 入场 ---------- */
  function showAll() {
    $$('.reveal').forEach(function (el) { el.classList.add('is-in'); });
  }
  if (!reduced && 'IntersectionObserver' in window) {
    var io = new IntersectionObserver(function (entries) {
      entries.forEach(function (entry) {
        if (entry.isIntersecting) {
          entry.target.classList.add('is-in');
          io.unobserve(entry.target);
        }
      });
    }, { rootMargin: '0px 0px -8% 0px', threshold: 0.08 });
    $$('.reveal').forEach(function (el) { io.observe(el); });
    setTimeout(function () {
      if (!document.querySelector('.reveal.is-in')) showAll();
    }, 1800);
  } else {
    showAll();
  }

  /* ---------- 标题按词入场 ---------- */
  function splitTitle(el) {
    if (!el || el.dataset.split === '1') return;
    el.dataset.split = '1';
    var nodes = Array.prototype.slice.call(el.childNodes);
    var frag = document.createDocumentFragment();
    nodes.forEach(function (node) {
      if (node.nodeType === 3) {
        node.textContent.split(/(\s+)/).forEach(function (part) {
          if (!part) return;
          if (/^\s+$/.test(part)) { frag.appendChild(document.createTextNode(part)); return; }
          var word = document.createElement('span');
          word.className = 'word';
          var inner = document.createElement('span');
          inner.textContent = part;
          word.appendChild(inner);
          frag.appendChild(word);
        });
      } else {
        frag.appendChild(node);
      }
    });
    el.innerHTML = '';
    el.appendChild(frag);
  }
  $$('.hero-title').forEach(function (el) {
    splitTitle(el.querySelector('a') || el);
  });
  setTimeout(function () { root.classList.add('ready'); }, 80);

  /* ---------- 滚动进度 ---------- */
  var line = $('#scroll-i');
  var ticking = false;
  function paintScroll() {
    ticking = false;
    if (!line) return;
    var max = document.documentElement.scrollHeight - window.innerHeight;
    var p = max > 0 ? clamp(window.scrollY / max, 0, 1) : 0;
    line.style.width = (p * 100).toFixed(2) + '%';
  }
  window.addEventListener('scroll', function () {
    if (ticking) return;
    ticking = true;
    raf(paintScroll);
  }, { passive: true });
  paintScroll();

  /* ---------- 磁吸按钮 ---------- */
  if (!reduced && window.matchMedia && window.matchMedia('(pointer:fine)').matches) {
    $$('.magnet').forEach(function (el) {
      var strength = Number(el.dataset.magnet || 14);
      el.addEventListener('pointermove', function (e) {
        var r = el.getBoundingClientRect();
        var x = (e.clientX - r.left - r.width / 2) / (r.width / 2);
        var y = (e.clientY - r.top - r.height / 2) / (r.height / 2);
        el.style.transform = 'translate(' + (x * strength).toFixed(1) + 'px,' + (y * strength * 0.6).toFixed(1) + 'px)';
      });
      el.addEventListener('pointerleave', function () { el.style.transform = ''; });
    });
  }

  /* ---------- 封面 3D 倾斜 ---------- */
  if (!reduced && window.matchMedia && window.matchMedia('(pointer:fine)').matches) {
    $$('[data-tilt]').forEach(function (el) {
      el.addEventListener('pointermove', function (e) {
        var r = el.getBoundingClientRect();
        var x = (e.clientX - r.left) / r.width - 0.5;
        var y = (e.clientY - r.top) / r.height - 0.5;
        el.style.transform = 'perspective(900px) rotateY(' + (x * 7).toFixed(2) + 'deg) rotateX(' + (-y * 7).toFixed(2) + 'deg) translateZ(0)';
      });
      el.addEventListener('pointerleave', function () { el.style.transform = ''; });
    });
  }

  /* ---------- 数字滚动 ---------- */
  if (!reduced) {
    $$('[data-count]').forEach(function (el) {
      var target = Number(el.dataset.count);
      if (!isFinite(target)) return;
      var suffix = el.dataset.suffix || '';
      var start = null;
      var dur = Number(el.dataset.duration || 900);
      function step(ts) {
        if (!start) start = ts;
        var p = clamp((ts - start) / dur, 0, 1);
        var eased = 1 - Math.pow(1 - p, 3);
        el.textContent = Math.round(target * eased) + suffix;
        if (p < 1) raf(step);
      }
      raf(step);
    });
  }

  /* ---------- 光标环 ---------- */
  var cursor = $('#cursor');
  if (cursor && !reduced && window.matchMedia && window.matchMedia('(pointer:fine)').matches) {
    var cx = 0, cy = 0, tx = 0, ty = 0;
    document.addEventListener('pointermove', function (e) {
      tx = e.clientX; ty = e.clientY;
      cursor.style.opacity = '.6';
    }, { passive: true });
    (function loop() {
      cx += (tx - cx) * 0.18;
      cy += (ty - cy) * 0.18;
      cursor.style.transform = 'translate(' + cx + 'px,' + cy + 'px) translate(-50%,-50%)';
      raf(loop);
    })();
    $$('a, button, .issue-row, .magnet').forEach(function (el) {
      el.addEventListener('pointerenter', function () { cursor.classList.add('is-link'); });
      el.addEventListener('pointerleave', function () { cursor.classList.remove('is-link'); });
    });
  }

  /* ---------- 往期卡片轮播 ---------- */
  var deck = $('.deck-stage');
  var deckRail = $('.deck-ring');
  $$('[data-deck-prev]').forEach(function (btn) {
    btn.addEventListener('click', function () {
      if (deckRail && window.innerWidth <= 820) {
        deckRail.scrollBy({ left: -(deckRail.clientWidth * 0.72 + 14), behavior: 'smooth' });
      }
    });
  });
  $$('[data-deck-next]').forEach(function (btn) {
    btn.addEventListener('click', function () {
      if (deckRail && window.innerWidth <= 820) {
        deckRail.scrollBy({ left: deckRail.clientWidth * 0.72 + 14, behavior: 'smooth' });
      }
    });
  });
  if (deck && !reduced && window.innerWidth > 820) {
    var deckCards = $$('.deck-card', deck);
    var deckN = deckCards.length;
    if (deckN > 2) {
      var deckMid = Math.floor(deckN / 2);
      var deckShift = deckMid;
      var deckTimer = null;
      var paintDeck = function () {
        deckCards.forEach(function (card, i) {
          var pos = ((i + deckShift) % deckN + deckN) % deckN - deckMid;
          var abs = Math.abs(pos);
          card.style.setProperty('--pos', pos);
          card.style.setProperty('--abs', abs);
          card.setAttribute('aria-hidden', abs > 2 ? 'true' : 'false');
          card.tabIndex = abs > 2 ? -1 : 0;
        });
      };
      var startDeck = function () {
        if (deckTimer) return;
        deckTimer = setInterval(function () { deckShift += 1; paintDeck(); }, 2600);
      };
      var stopDeck = function () {
        if (deckTimer) { clearInterval(deckTimer); deckTimer = null; }
      };
      var stepDeck = function (step) {
        deckShift += step;
        paintDeck();
        stopDeck();
        if (!deck.matches(':hover') && !deck.contains(document.activeElement)) startDeck();
      };
      $$('[data-deck-prev]', deck.parentNode).forEach(function (btn) {
        btn.addEventListener('click', function () { stepDeck(-1); });
      });
      $$('[data-deck-next]', deck.parentNode).forEach(function (btn) {
        btn.addEventListener('click', function () { stepDeck(1); });
      });
      deck.addEventListener('mouseenter', stopDeck);
      deck.addEventListener('mouseleave', startDeck);
      deck.addEventListener('focusin', stopDeck);
      deck.addEventListener('focusout', function (e) {
        if (!deck.contains(e.relatedTarget)) startDeck();
      });
      paintDeck();
      startDeck();
    }
  }

  /* ---------- 白天 / 黑夜 ---------- */
  var themeBtns = $$('[data-theme-toggle]');
  function themeNow() { return root.dataset.theme === 'day' ? 'day' : 'night'; }
  function paintTheme() {
    var day = themeNow() === 'day';
    themeBtns.forEach(function (btn) {
      var icon = $('[data-theme-icon]', btn);
      var text = $('[data-theme-text]', btn);
      if (icon) icon.textContent = day ? '☾' : '☀';
      if (text) text.textContent = day ? '黑夜' : '白天';
      btn.setAttribute('aria-pressed', String(day));
      btn.setAttribute('aria-label', day ? '切换到黑夜模式' : '切换到白天模式');
    });
    var meta = document.getElementById('theme-color');
    if (meta) meta.setAttribute('content', day ? '#efe7d6' : '#08090b');
  }
  function setTheme(next) {
    root.dataset.theme = next === 'day' ? 'day' : 'night';
    try { localStorage.setItem('bilmag.siteTheme', root.dataset.theme); } catch (e) {}
    paintTheme();
  }
  themeBtns.forEach(function (btn) {
    btn.addEventListener('click', function () { setTheme(themeNow() === 'day' ? 'night' : 'day'); });
  });
  paintTheme();

  /* ---------- 页面幕布 ---------- */
  setTimeout(function () { root.classList.add('veil-done'); }, 60);
  setTimeout(function () { root.classList.add('veil-gone'); }, 900);

})();
