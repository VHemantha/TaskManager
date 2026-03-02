/* ══════════════════════════════════════════════════════════════════════════════
   Obsidian Workspace — Sidebar + Command Palette
   ══════════════════════════════════════════════════════════════════════════════ */

(function () {
  'use strict';

  // ── Sidebar collapse ─────────────────────────────────────────────────────────
  const body = document.body;
  const toggleBtn = document.getElementById('sidebarToggle');
  const mobileToggle = document.getElementById('mobileSidebarToggle');
  const sidebar = document.getElementById('tmSidebar');

  // Restore collapse state
  if (localStorage.getItem('tmSidebarCollapsed') === '1') {
    body.classList.add('sidebar-collapsed');
  }

  if (toggleBtn) {
    toggleBtn.addEventListener('click', () => {
      body.classList.toggle('sidebar-collapsed');
      localStorage.setItem('tmSidebarCollapsed', body.classList.contains('sidebar-collapsed') ? '1' : '0');
    });
  }

  if (mobileToggle && sidebar) {
    mobileToggle.addEventListener('click', () => {
      sidebar.classList.toggle('mobile-open');
    });
    // Close sidebar when clicking outside on mobile
    document.addEventListener('click', (e) => {
      if (sidebar.classList.contains('mobile-open') &&
          !sidebar.contains(e.target) && !mobileToggle.contains(e.target)) {
        sidebar.classList.remove('mobile-open');
      }
    });
  }

  // ── Command Palette ──────────────────────────────────────────────────────────
  const overlay = document.getElementById('cmdPalette');
  const paletteInput = document.getElementById('paletteInput');
  const paletteResults = document.getElementById('paletteResults');
  const searchInput = document.getElementById('globalSearchInput');

  let debounceTimer = null;
  let focusedIdx = -1;

  function openPalette() {
    if (!overlay) return;
    overlay.classList.remove('d-none');
    if (paletteInput) {
      paletteInput.value = '';
      paletteInput.focus();
    }
    focusedIdx = -1;
    showEmptyState();
  }

  function closePalette() {
    if (!overlay) return;
    overlay.classList.add('d-none');
    focusedIdx = -1;
  }

  function showEmptyState() {
    if (!paletteResults) return;
    paletteResults.innerHTML = '<div class="tm-palette-empty text-muted text-center py-4 small">Start typing to search…</div>';
  }

  function renderResults(results) {
    if (!paletteResults) return;
    if (!results.length) {
      paletteResults.innerHTML = '<div class="tm-palette-empty text-muted text-center py-4 small">No results found.</div>';
      return;
    }
    paletteResults.innerHTML = results.map((r, i) => `
      <a href="${r.url}" class="tm-palette-result" data-idx="${i}">
        <div class="tm-palette-icon ${r.type}">
          <i class="bi bi-${r.icon}"></i>
        </div>
        <div class="tm-palette-result-text">
          <div class="tm-palette-result-title">${escHtml(r.title)}</div>
          <div class="tm-palette-result-sub">${escHtml(r.subtitle || '')}</div>
        </div>
        <span class="tm-palette-kbd">↵ Open</span>
      </a>
    `).join('');
  }

  function escHtml(s) {
    return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
  }

  function doSearch(q) {
    if (q.length < 2) { showEmptyState(); return; }
    fetch(`/api/search?q=${encodeURIComponent(q)}`, {
      headers: { 'X-Requested-With': 'XMLHttpRequest' }
    })
      .then(r => r.ok ? r.json() : [])
      .then(data => renderResults(data))
      .catch(() => {});
  }

  if (paletteInput) {
    paletteInput.addEventListener('input', () => {
      clearTimeout(debounceTimer);
      debounceTimer = setTimeout(() => doSearch(paletteInput.value.trim()), 220);
    });

    paletteInput.addEventListener('keydown', (e) => {
      const items = paletteResults ? paletteResults.querySelectorAll('.tm-palette-result') : [];
      if (e.key === 'ArrowDown') {
        e.preventDefault();
        focusedIdx = Math.min(focusedIdx + 1, items.length - 1);
        updateFocus(items);
      } else if (e.key === 'ArrowUp') {
        e.preventDefault();
        focusedIdx = Math.max(focusedIdx - 1, -1);
        updateFocus(items);
      } else if (e.key === 'Enter' && focusedIdx >= 0 && items[focusedIdx]) {
        items[focusedIdx].click();
      } else if (e.key === 'Escape') {
        closePalette();
      }
    });
  }

  function updateFocus(items) {
    items.forEach((el, i) => {
      el.classList.toggle('focused', i === focusedIdx);
      if (i === focusedIdx) el.scrollIntoView({ block: 'nearest' });
    });
  }

  if (overlay) {
    overlay.addEventListener('click', (e) => {
      if (e.target === overlay) closePalette();
    });
  }

  // Global search input opens palette
  if (searchInput) {
    searchInput.addEventListener('focus', () => openPalette());
    searchInput.addEventListener('keydown', (e) => {
      if (e.key === 'Escape') closePalette();
    });
  }

  // Ctrl+K shortcut
  document.addEventListener('keydown', (e) => {
    if ((e.ctrlKey || e.metaKey) && e.key === 'k') {
      e.preventDefault();
      if (overlay && overlay.classList.contains('d-none')) {
        openPalette();
      } else {
        closePalette();
      }
    }
    if (e.key === 'Escape' && overlay && !overlay.classList.contains('d-none')) {
      closePalette();
    }
  });

})();
