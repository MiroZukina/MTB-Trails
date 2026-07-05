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

// Collapsed post composer: click the trigger pill to reveal the full card.
// On narrow screens the expanded card becomes a full-screen sheet (see CSS),
// so also lock/unlock background scroll and wire the header's close button.
function initComposerToggle() {
  document.querySelectorAll('.composer').forEach(function (composer) {
    var trigger = composer.querySelector('.composer-trigger');
    var closeBtn = composer.querySelector('.composer-close');
    var isMobileSheet = function () {
      return window.matchMedia('(max-width: 767.98px)').matches;
    };

    function open() {
      composer.classList.add('is-open');
      if (isMobileSheet()) document.body.style.overflow = 'hidden';
      var firstField = composer.querySelector('.composer-body textarea, .composer-body input');
      if (firstField) firstField.focus();
    }
    function close() {
      composer.classList.remove('is-open');
      document.body.style.overflow = '';
    }

    if (trigger) trigger.addEventListener('click', open);
    if (closeBtn) closeBtn.addEventListener('click', close);
  });
}

// Facebook-style "Add to your post" row: each icon toggles a section below
// it (photo/video, media link, attachment, location, difficulty). A section
// stays visually "active" on its icon either while open or once it holds
// content, so users can see at a glance what they've attached even after
// collapsing it again.
function initComposerSections() {
  var card = document.querySelector('.composer-card');
  if (!card) return;

  // Scoped to the composer's own form: PostForm and CommentForm share field
  // names (media_url, attachment), so a page-wide getElementById would pick
  // up whichever comment's field happens to come first in the DOM.
  var scope = card.querySelector('#post-form') || card;
  var hasContent = {
    media: function () {
      var el = scope.querySelector('[name="post_media"]');
      return !!(el && el.files && el.files.length);
    },
    link: function () {
      var el = scope.querySelector('[name="media_url"]');
      return !!(el && el.value.trim());
    },
    attachment: function () {
      var el = scope.querySelector('[name="attachment"]');
      return !!(el && el.files && el.files.length);
    },
    location: function () {
      var lat = scope.querySelector('[name="latitude"]');
      var route = scope.querySelector('[name="route"]');
      return !!((lat && lat.value) || (route && route.value));
    },
    difficulty: function () {
      var el = scope.querySelector('[name="difficulty"]');
      return !!(el && el.value);
    }
  };

  var buttons = card.querySelectorAll('.composer-action-btn[data-toggle-section]');

  function refreshButtons() {
    buttons.forEach(function (btn) {
      var name = btn.dataset.toggleSection;
      var section = card.querySelector('.composer-section[data-section="' + name + '"]');
      var isOpen = section && !section.hidden;
      var content = hasContent[name] ? hasContent[name]() : false;
      btn.classList.toggle('is-active', !!isOpen || content);
    });
  }

  buttons.forEach(function (btn) {
    var name = btn.dataset.toggleSection;
    var section = card.querySelector('.composer-section[data-section="' + name + '"]');
    if (!section) return;
    btn.addEventListener('click', function () {
      section.hidden = !section.hidden;
      if (!section.hidden) {
        var firstField = section.querySelector('input:not([type=hidden]):not([type=file]), textarea, select');
        if (firstField) firstField.focus();
        if (name === 'location') {
          // The Leaflet map was created while its container was hidden (0x0),
          // so it needs a nudge to size itself correctly now that it's shown.
          setTimeout(function () { window.dispatchEvent(new Event('resize')); }, 50);
        }
      }
      refreshButtons();
    });
  });

  card.addEventListener('input', refreshButtons);
  card.addEventListener('change', refreshButtons);
  refreshButtons();
}

// Post button stays disabled until there's something to post — mirrors the
// server-side rule (text, a photo/video, a media link, or an attachment).
function initComposerSubmitGate() {
  var form = document.getElementById('post-form');
  if (!form) return;
  var submitBtn = form.querySelector('.composer-submit');
  if (!submitBtn) return;
  var bodyEl = form.querySelector('[name="body"]');
  var mediaEl = form.querySelector('[name="post_media"]');
  var urlEl = form.querySelector('[name="media_url"]');
  var attachEl = form.querySelector('[name="attachment"]');

  function hasFile(el) { return !!(el && el.files && el.files.length); }

  function refresh() {
    var ok = !!(bodyEl && bodyEl.value.trim()) ||
      hasFile(mediaEl) ||
      !!(urlEl && urlEl.value.trim()) ||
      hasFile(attachEl);
    submitBtn.disabled = !ok;
  }

  form.addEventListener('input', refresh);
  form.addEventListener('change', refresh);
  refresh();
}

// Large borderless textarea in the composer card grows with its content
// instead of scrolling internally.
function initComposerAutosize() {
  var textarea = document.querySelector('.composer-card textarea.form-control');
  if (!textarea) return;
  function resize() {
    textarea.style.height = 'auto';
    textarea.style.height = textarea.scrollHeight + 'px';
  }
  textarea.addEventListener('input', resize);
  resize();
}

// Media URL field shows its value as a removable chip, same component used
// by the file dropzones, once a link has been entered.
function initMediaUrlChip() {
  var form = document.getElementById('post-form');
  var chip = document.getElementById('media-url-chip');
  var input = form ? form.querySelector('[name="media_url"]') : null;
  if (!input || !chip) return;
  var nameEl = chip.querySelector('.chip-name');
  var removeBtn = chip.querySelector('.chip-remove');

  function refresh() {
    var v = input.value.trim();
    nameEl.textContent = v;
    chip.hidden = !v;
  }
  input.addEventListener('input', refresh);
  removeBtn.addEventListener('click', function () {
    input.value = '';
    input.dispatchEvent(new Event('input', { bubbles: true }));
  });
  refresh();
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
  initComposerSections();
  initComposerSubmitGate();
  initComposerAutosize();
  initMediaUrlChip();
  initCommentLinkToggles();
});
