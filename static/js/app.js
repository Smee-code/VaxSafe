/* VaxSafe: small enhancements on top of server-rendered pages. */
(function () {
  'use strict';

  // Mobile sidebar
  document.querySelectorAll('[data-nav-toggle]').forEach(function (btn) {
    btn.addEventListener('click', function () {
      document.body.classList.toggle('nav-open');
    });
  });
  document.addEventListener('click', function (e) {
    if (document.body.classList.contains('nav-open') && !e.target.closest('.sidebar') && !e.target.closest('[data-nav-toggle]')) {
      document.body.classList.remove('nav-open');
    }
  });

  // Dismissible messages
  document.querySelectorAll('.message button').forEach(function (btn) {
    btn.addEventListener('click', function () { btn.closest('.message').remove(); });
  });

  // Close the user menu when clicking elsewhere
  document.addEventListener('click', function (e) {
    document.querySelectorAll('details.user-menu[open]').forEach(function (d) {
      if (!d.contains(e.target)) d.removeAttribute('open');
    });
  });

  // Label each cell with its column heading, so tables can stack into rows on phones
  document.querySelectorAll('table.table').forEach(function (table) {
    var heads = Array.prototype.map.call(table.querySelectorAll('thead th'), function (th) { return th.textContent.trim(); });
    if (!heads.length) return;
    table.querySelectorAll('tbody tr, tfoot tr').forEach(function (row) {
      Array.prototype.forEach.call(row.children, function (cell, i) {
        if (!cell.hasAttribute('data-label')) cell.setAttribute('data-label', heads[i] || '');
      });
    });
  });

  // Close the phone drawer with Escape
  document.addEventListener('keydown', function (e) {
    if (e.key === 'Escape') document.body.classList.remove('nav-open');
  });

  // Clickable table rows
  document.querySelectorAll('tr[data-href]').forEach(function (row) {
    row.classList.add('row-link');
    row.addEventListener('click', function (e) {
      if (e.target.closest('a, button, form, input, select')) return;
      window.location = row.dataset.href;
    });
  });

  // Confirm destructive actions
  document.querySelectorAll('form[data-confirm]').forEach(function (form) {
    form.addEventListener('submit', function (e) {
      if (!window.confirm(form.dataset.confirm)) e.preventDefault();
    });
  });

  // Auto-submit filter selects
  document.querySelectorAll('[data-autosubmit]').forEach(function (el) {
    el.addEventListener('change', function () { el.form.submit(); });
  });

  // Form behaviour, applied to the page and to every form loaded into the modal
  function enhanceForm(root) {
    // Show "If other, specify" only when the animal is "Other"
    var animal = root.querySelector('#id_animal_type');
    var other = root.querySelector('#id_animal_type_other');
    if (animal && other) {
      var wrap = other.closest('.field');
      var sync = function () { wrap.style.display = animal.value === 'OTHER' ? '' : 'none'; };
      animal.addEventListener('change', sync);
      sync();
    }
  }
  enhanceForm(document);

  // Modal forms ------------------------------------------------------------
  // Links to these pages open as a dialog instead of a new page. Visiting the
  // URL directly still shows the full page, so nothing depends on JavaScript.
  var MODAL_ROUTES = [
    /^\/patients\/new\/$/, /^\/patients\/\d+\/edit\/$/, /^\/patients\/\d+\/visits\/new\/$/,
    /^\/visits\/\d+\/(edit|assessment|schedule)\/$/,
    /^\/doses\/\d+\/(record|reschedule)\/$/,
    /^\/inventory\/(receive|adjust|temperature\/new)\/$/,
    /^\/accounts\/users\/(new|\d+\/edit|\d+\/reset-password)\/$/, /^\/accounts\/password\/$/,
    /^\/settings\/[\w-]+\/(new|\d+\/edit)\/$/
  ];

  function isModalUrl(href) {
    var url;
    try { url = new URL(href, window.location.href); } catch (err) { return false; }
    if (url.origin !== window.location.origin) return false;
    return MODAL_ROUTES.some(function (re) { return re.test(url.pathname); });
  }

  var dialog = document.createElement('dialog');
  dialog.className = 'modal';
  dialog.setAttribute('aria-labelledby', 'modal-title');
  dialog.innerHTML = '<div class="modal-scroll"></div>';
  document.body.appendChild(dialog);
  var scroller = dialog.firstChild;
  var opener = null;

  function closeModal() {
    if (dialog.open) dialog.close();
  }
  dialog.addEventListener('close', function () {
    scroller.innerHTML = '';
    dialog.classList.remove('is-wide', 'is-busy');
    document.body.classList.remove('modal-open');
    if (opener && document.contains(opener)) opener.focus();
  });
  dialog.addEventListener('click', function (e) {
    if (e.target.closest('[data-modal-close]')) { closeModal(); return; }
    // Clicking the backdrop (outside the sheet) closes it
    if (e.target === dialog) {
      var r = dialog.getBoundingClientRect();
      if (e.clientX < r.left || e.clientX > r.right || e.clientY < r.top || e.clientY > r.bottom) closeModal();
    }
  });

  function render(html) {
    var doc = new DOMParser().parseFromString(html, 'text/html');
    var root = doc.querySelector('[data-modal-root]');
    scroller.innerHTML = '';
    scroller.appendChild(document.importNode(root, true));
    dialog.classList.toggle('is-wide', !!scroller.querySelector('.form-layout.has-aside'));
    dialog.classList.remove('is-busy');
    if (!dialog.open) dialog.showModal();
    document.body.classList.add('modal-open');
    scroller.scrollTop = 0;
    enhanceForm(scroller);
    var firstError = scroller.querySelector('.has-error .input, .form-errors');
    var first = firstError || scroller.querySelector('.form-card .input:not([type=hidden])');
    if (first && first.focus) first.focus({ preventScroll: !!firstError });
    if (firstError) firstError.scrollIntoView({ block: 'center' });
  }

  function handle(response, fallbackUrl) {
    if (!response.ok) { window.location.href = fallbackUrl; return Promise.resolve(); }
    var type = response.headers.get('Content-Type') || '';
    if (type.indexOf('application/json') !== -1) {
      return response.json().then(function (data) {
        if (!data.redirect) { window.location.reload(); return; }
        // Next step is another form (e.g. visit → assessment → schedule): stay in the dialog
        if (isModalUrl(data.redirect)) return openModal(data.redirect);
        closeModal();
        window.location.href = data.redirect;
      });
    }
    return response.text().then(function (html) {
      if (html.indexOf('data-modal-root') === -1) { window.location.href = fallbackUrl; return; }
      render(html);
    });
  }

  function openModal(url) {
    dialog.classList.add('is-busy');
    return fetch(url, { headers: { 'X-Modal': '1' }, credentials: 'same-origin' })
      .then(function (res) { return handle(res, url); })
      .catch(function () { window.location.href = url; });
  }

  document.addEventListener('click', function (e) {
    var link = e.target.closest('a[href]');
    if (!link || e.defaultPrevented || e.button !== 0 || e.ctrlKey || e.metaKey || e.shiftKey || e.altKey || link.target) return;
    if (!isModalUrl(link.href)) return;
    e.preventDefault();
    opener = dialog.open ? opener : link;
    document.body.classList.remove('nav-open');
    openModal(link.href);
  });

  dialog.addEventListener('submit', function (e) {
    var form = e.target;
    if (!form.matches('[data-modal-form]')) return;
    e.preventDefault();
    if (dialog.classList.contains('is-busy')) return;
    var data = new FormData(form);
    if (e.submitter && e.submitter.name) data.append(e.submitter.name, e.submitter.value);
    dialog.classList.add('is-busy');
    fetch(form.action, { method: 'POST', body: data, headers: { 'X-Modal': '1' }, credentials: 'same-origin' })
      .then(function (res) { return handle(res, form.action); })
      .catch(function () { dialog.classList.remove('is-busy'); window.alert('Could not save. Check the connection to the server and try again.'); });
  });

  // Charts
  var dataEl = document.getElementById('chart-data');
  if (!dataEl || typeof Chart === 'undefined') return;

  var css = getComputedStyle(document.documentElement);
  var v = function (name) { return css.getPropertyValue(name).trim(); };
  var named = {
    brand: v('--chart-1'), ok: v('--ok'), danger: v('--danger'), warn: v('--warn'),
    muted: '#c9d2db', info: v('--info')
  };
  var series = [v('--chart-1'), v('--chart-2'), v('--chart-3'), v('--chart-4'), v('--chart-5'), v('--chart-6')];
  var byLabel = {
    'Category I': v('--cat-1'), 'Category II': v('--cat-2'), 'Category III': v('--cat-3'),
    'Not assessed': '#c9d2db', 'Completed': named.ok, 'Ongoing': '#9fb6d3', 'With missed dose': named.danger,
    'Dog': v('--chart-1'), 'Cat': v('--chart-2'), 'Other': v('--chart-6')
  };

  Chart.defaults.font.family = getComputedStyle(document.body).fontFamily;
  Chart.defaults.font.size = 12;
  Chart.defaults.color = v('--muted');
  Chart.defaults.borderColor = v('--rule-soft');
  Chart.defaults.plugins.legend.labels.boxWidth = 10;
  Chart.defaults.plugins.legend.labels.boxHeight = 10;
  Chart.defaults.plugins.legend.labels.useBorderRadius = true;
  Chart.defaults.plugins.legend.labels.borderRadius = 3;
  Chart.defaults.maintainAspectRatio = false;

  JSON.parse(dataEl.textContent).forEach(function (spec) {
    var canvas = document.getElementById('chart-' + spec.id);
    if (!canvas) return;
    var colorFor = function (ds, i) {
      if (spec.colors && spec.colors[i]) return named[spec.colors[i]] || spec.colors[i];
      return byLabel[ds.label] || series[i % series.length];
    };
    var datasets;
    if (spec.type === 'doughnut') {
      datasets = spec.datasets.map(function (ds) {
        return {
          label: ds.label, data: ds.data, borderWidth: 2, borderColor: '#fff',
          backgroundColor: spec.labels.map(function (label, i) {
            if (spec.colors && spec.colors[i]) return named[spec.colors[i]];
            return byLabel[label] || series[i % series.length];
          })
        };
      });
    } else if (spec.type === 'line') {
      var n = 0;
      datasets = spec.datasets.map(function (ds) {
        if (ds.limit) {
          return { label: ds.label, data: ds.data, borderColor: named.danger, borderDash: [5, 4], borderWidth: 1.2, pointRadius: 0, fill: false };
        }
        var c = series[n++ % series.length];
        return { label: ds.label, data: ds.data, borderColor: c, backgroundColor: c, borderWidth: 2, pointRadius: 2, tension: .25, spanGaps: true };
      });
    } else {
      datasets = spec.datasets.map(function (ds, i) {
        var c = colorFor(ds, i);
        return { label: ds.label, data: ds.data, backgroundColor: c, borderRadius: 3, maxBarThickness: 38 };
      });
    }

    var options = { plugins: { legend: { position: 'bottom' } } };
    if (spec.type !== 'doughnut') {
      options.scales = {
        x: { stacked: !!spec.stacked, grid: { display: !!spec.horizontal }, ticks: { precision: 0 } },
        y: { stacked: !!spec.stacked, grid: { display: !spec.horizontal }, ticks: { precision: 0 }, beginAtZero: spec.type !== 'line' }
      };
      if (spec.horizontal) options.indexAxis = 'y';
    } else {
      options.cutout = '62%';
      options.plugins.legend.position = canvas.parentNode.clientWidth < 520 ? 'bottom' : 'right';
    }
    var empty = spec.datasets.every(function (ds) { return ds.limit || ds.data.every(function (x) { return !x; }); });
    if (empty) {
      canvas.parentNode.innerHTML = '<div class="empty"><strong>No data</strong>Nothing to chart for the selected filters.</div>';
      return;
    }
    new Chart(canvas, { type: spec.type, data: { labels: spec.labels, datasets: datasets }, options: options });
  });
})();
