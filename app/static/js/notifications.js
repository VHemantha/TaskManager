// ── Real-time notification client ─────────────────────────────────────────────
(function () {
  if (typeof io === 'undefined') return;

  const notifSocket = io('/notifications', { transports: ['websocket', 'polling'] });

  notifSocket.on('connect', () => {
    console.debug('[Notif] Connected');
  });

  notifSocket.on('new_notification', data => {
    updateBadge(data);
    showToast(data);
  });

  notifSocket.on('unread_count', data => {
    refreshBadge(data.count);
  });

  function updateBadge(data) {
    const badge = document.getElementById('notifBadge');
    if (!badge) return;
    const current = parseInt(badge.textContent) || 0;
    const newCount = current + 1;
    badge.textContent = newCount > 99 ? '99+' : newCount;
    badge.classList.remove('d-none');
  }

  function refreshBadge(count) {
    const badge = document.getElementById('notifBadge');
    if (!badge) return;
    if (count > 0) {
      badge.textContent = count > 99 ? '99+' : count;
      badge.classList.remove('d-none');
    } else {
      badge.classList.add('d-none');
    }
  }

  function showToast(data) {
    // Create Bootstrap toast
    const container = document.getElementById('toastContainer') || createToastContainer();
    const toastEl = document.createElement('div');
    toastEl.className = 'toast align-items-center text-bg-primary border-0';
    toastEl.setAttribute('role', 'alert');
    toastEl.innerHTML = `
      <div class="d-flex">
        <div class="toast-body">
          <strong>${escapeHtml(data.title)}</strong>
          ${data.message ? '<br><small>' + escapeHtml(data.message) + '</small>' : ''}
          ${data.task_id ? '<br><a href="/tasks/' + data.task_id + '" class="text-white-50 small">View Task</a>' : ''}
        </div>
        <button type="button" class="btn-close btn-close-white me-2 m-auto" data-bs-dismiss="toast"></button>
      </div>`;
    container.appendChild(toastEl);
    const toast = new bootstrap.Toast(toastEl, { delay: 5000 });
    toast.show();
    toastEl.addEventListener('hidden.bs.toast', () => toastEl.remove());
  }

  function createToastContainer() {
    const div = document.createElement('div');
    div.id = 'toastContainer';
    div.className = 'toast-container position-fixed top-0 end-0 p-3';
    div.style.zIndex = '1090';
    document.body.appendChild(div);
    return div;
  }

  function escapeHtml(str) {
    return String(str || '').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
  }
})();
