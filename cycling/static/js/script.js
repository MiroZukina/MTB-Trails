function escHtml(s) {
  return String(s)
    .replace(/&/g, '&amp;').replace(/</g, '&lt;')
    .replace(/>/g, '&gt;').replace(/"/g, '&quot;');
}

var TRAIL_DIFF_BADGE = {
  green: '<span style="display:inline-block;padding:.15rem .5rem;border-radius:999px;font-size:.65rem;font-weight:700;text-transform:uppercase;background:rgba(34,197,94,.18);color:#22c55e;border:1px solid rgba(34,197,94,.4);">Easy</span>',
  blue:  '<span style="display:inline-block;padding:.15rem .5rem;border-radius:999px;font-size:.65rem;font-weight:700;text-transform:uppercase;background:rgba(59,130,246,.18);color:#3b82f6;border:1px solid rgba(59,130,246,.4);">Moderate</span>',
  red:   '<span style="display:inline-block;padding:.15rem .5rem;border-radius:999px;font-size:.65rem;font-weight:700;text-transform:uppercase;background:rgba(239,68,68,.18);color:#ef4444;border:1px solid rgba(239,68,68,.4);">Difficult</span>',
  black: '<span style="display:inline-block;padding:.15rem .5rem;border-radius:999px;font-size:.65rem;font-weight:700;text-transform:uppercase;background:#0a0a0a;color:#fff;border:1px solid rgba(255,255,255,.35);">Severe</span>',
};

// Shared Leaflet + CyclOSM renderer for a list of trail posts (routes + pins).
// Used by both the explore page and rider profile pages.
function renderTrailMap(elementId, posts, mapOptions) {
  var el = document.getElementById(elementId);
  if (!el) return null;

  var map = L.map(elementId, mapOptions || { center: [53.35, -6.26], zoom: 6 });
  L.tileLayer('https://{s}.tile-cyclosm.openstreetmap.fr/cyclosm/{z}/{x}/{y}.png', {
    maxZoom: 20,
    attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors | <a href="https://www.cyclosm.org">CyclOSM</a>'
  }).addTo(map);

  if (!posts || !posts.length) return map;

  var bounds = [];

  posts.forEach(function (p) {
    var badge = p.difficulty ? (TRAIL_DIFF_BADGE[p.difficulty] || '') : '';
    var html = '<div class="ep-title">' + escHtml(p.body) + '</div>' +
               '<div class="ep-meta">' +
               (p.location ? '&#128205; ' + escHtml(p.location) + '<br>' : '') +
               '&#128101; @' + escHtml(p.author) +
               (p.length_km ? '&nbsp;&nbsp;&#128692; ' + p.length_km.toFixed(1) + ' km' : '') +
               (badge ? '&nbsp;&nbsp;' + badge : '') +
               '</div>' +
               '<a class="ep-link" href="' + p.url + '">View post &rarr;</a>';

    var lineColor = p.diff_color || '#e03030';

    if (p.route && p.route.length > 1) {
      var poly = L.polyline(p.route, { color: lineColor, weight: 3, opacity: 0.85 }).addTo(map);
      poly.bindPopup(html);
      bounds.push(poly.getBounds());
      L.marker([p.route[0][0], p.route[0][1]]).addTo(map).bindPopup(html);
    } else {
      var marker = L.marker([p.lat, p.lng]).addTo(map);
      marker.bindPopup(html);
      bounds.push([[p.lat, p.lng]]);
    }
  });

  if (bounds.length) {
    var combined = L.latLngBounds([]);
    bounds.forEach(function (b) {
      if (b.extend) combined.extend(b);
      else b.forEach(function (pt) { combined.extend(pt); });
    });
    if (combined.isValid()) map.fitBounds(combined, { padding: [40, 40] });
  }

  return map;
}

// Dropzone-style file inputs: a styled label triggers the (visually hidden)
// native <input type=file>, and the chosen filename shows as a removable chip.
// Django's ClearableFileInput markup (Currently/Clear/Change) is left as-is
// inside .dropzone-field so existing clear/change behavior keeps working.
function initDropzones() {
  document.querySelectorAll('[data-dropzone]').forEach(function (dz) {
    var input = dz.querySelector('input[type="file"]');
    if (!input || dz.dataset.dropzoneReady) return;
    dz.dataset.dropzoneReady = '1';

    var chip = document.createElement('div');
    chip.className = 'chip';
    chip.hidden = true;
    chip.innerHTML = '<span class="chip-icon">📎</span>' +
      '<span class="chip-name"></span>' +
      '<button type="button" class="chip-remove" aria-label="Remove selected file">&times;</button>';
    dz.appendChild(chip);

    var nameEl = chip.querySelector('.chip-name');
    var removeBtn = chip.querySelector('.chip-remove');

    input.addEventListener('change', function () {
      if (input.files && input.files[0]) {
        nameEl.textContent = input.files[0].name;
        chip.hidden = false;
      } else {
        chip.hidden = true;
      }
    });

    removeBtn.addEventListener('click', function () {
      input.value = '';
      chip.hidden = true;
    });
  });
}

// Collapsed post composer: click the trigger pill to reveal the full form.
function initComposerToggle() {
  document.querySelectorAll('.composer').forEach(function (composer) {
    var trigger = composer.querySelector('.composer-trigger');
    if (!trigger) return;
    trigger.addEventListener('click', function () {
      composer.classList.add('is-open');
      var firstField = composer.querySelector('.composer-body textarea, .composer-body input');
      if (firstField) firstField.focus();
    });
  });
}

// Compact comment composer: the 🔗 icon reveals a small URL input.
function initCommentLinkToggles() {
  document.querySelectorAll('.comment-link-toggle').forEach(function (toggle) {
    var form = toggle.closest('form');
    var row = form ? form.querySelector('.comment-link-row') : null;
    if (!row) return;
    toggle.addEventListener('click', function () {
      row.hidden = !row.hidden;
      if (!row.hidden) {
        var input = row.querySelector('input');
        if (input) input.focus();
      }
    });
  });
}

document.addEventListener('DOMContentLoaded', function () {
  initDropzones();
  initComposerToggle();
  initCommentLinkToggles();
});
