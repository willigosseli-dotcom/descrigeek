/* Autocomplétion floue réutilisable (recherche tolérante aux fautes).
   attachFuzzy(input, { champ, getTypeUnite, onSelect }) */
(function () {
  function esc(s) { const d = document.createElement('div'); d.textContent = s || ''; return d.innerHTML; }

  window.attachFuzzy = function (input, opts) {
    opts = opts || {};
    const champ = opts.champ || '';
    let box = null, timer = null, items = [], active = -1;
    input.setAttribute('autocomplete', 'off');

    function close() { if (box) { box.remove(); box = null; } active = -1; }

    function place() {
      const wrap = input.parentElement;
      wrap.style.position = 'relative';
      box.style.top = (input.offsetTop + input.offsetHeight + 2) + 'px';
      box.style.left = input.offsetLeft + 'px';
      box.style.width = input.offsetWidth + 'px';
      wrap.appendChild(box);
    }

    function render(list) {
      close();
      items = list || [];
      if (!items.length) return;
      box = document.createElement('div');
      box.className = 'fuzzy-menu';
      items.forEach((s, i) => {
        const el = document.createElement('div');
        el.className = 'fuzzy-item';
        el.dataset.i = i;
        const sub = [s.marque, s.ligne].filter(Boolean).join(' · ');
        el.innerHTML = '<strong>' + esc(s.modele || s.ligne || s.marque) + '</strong>'
          + (sub ? ' <span class="fuzzy-sub">' + esc(sub) + '</span>' : '');
        el.addEventListener('mousedown', (e) => { e.preventDefault(); choose(i); });
        box.appendChild(el);
      });
      place();
    }

    function choose(i) {
      const s = items[i];
      if (s && opts.onSelect) opts.onSelect(s);
      close();
    }

    function highlight(d) {
      if (!box) return;
      const els = box.querySelectorAll('.fuzzy-item');
      active = (active + d + els.length) % els.length;
      els.forEach((e, i) => e.classList.toggle('active', i === active));
    }

    input.addEventListener('input', () => {
      clearTimeout(timer);
      const q = input.value.trim();
      if (q.length < 2) { close(); return; }
      timer = setTimeout(async () => {
        const tu = opts.getTypeUnite ? (opts.getTypeUnite() || '') : '';
        const url = '/api/evaluation/suggestions?q=' + encodeURIComponent(q)
          + '&champ=' + encodeURIComponent(champ) + '&type_unite=' + encodeURIComponent(tu)
          + '&source=' + encodeURIComponent(opts.source || '');
        try {
          const r = await fetch(url, { headers: { 'Accept': 'application/json' } });
          if (!r.ok) return;
          const data = await r.json();
          render(data.suggestions || []);
        } catch (e) { /* silencieux */ }
      }, 200);
    });

    input.addEventListener('keydown', (e) => {
      if (!box) return;
      if (e.key === 'ArrowDown') { e.preventDefault(); highlight(1); }
      else if (e.key === 'ArrowUp') { e.preventDefault(); highlight(-1); }
      else if (e.key === 'Enter' && active >= 0) { e.preventDefault(); choose(active); }
      else if (e.key === 'Escape') { close(); }
    });

    input.addEventListener('blur', () => setTimeout(close, 150));
  };
})();
