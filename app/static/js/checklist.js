/* ══════════════════════════════════════════════════════════════════════════════
   Obsidian Workspace — Checklist + Subtask interactions
   ══════════════════════════════════════════════════════════════════════════════ */

(function () {
  'use strict';

  function _csrf() {
    const m = document.querySelector('meta[name="csrf-token"]');
    return m ? m.content : '';
  }

  function _post(url, body) {
    return fetch(url, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'X-CSRFToken': _csrf() },
      body: JSON.stringify(body),
    }).then(r => r.json());
  }

  function _updateProgress(done, total) {
    const bar = document.getElementById('checklistProgressBar');
    const badge = document.getElementById('checklistCount');
    const pct = total ? Math.round(done / total * 100) : 0;
    if (bar) {
      bar.style.width = pct + '%';
      bar.setAttribute('aria-valuenow', pct);
    }
    if (badge) badge.textContent = `${done}/${total}`;
  }

  const container   = document.getElementById('checklistContainer');
  const addBtn      = document.getElementById('btnAddChecklist');
  const addForm     = document.getElementById('addChecklistForm');
  const addInput    = document.getElementById('checklistInput');
  const saveBtn     = document.getElementById('btnSaveChecklist');
  const noChecklist = document.getElementById('noChecklist');
  const TASK_ID     = document.body.dataset.taskId;

  if (!TASK_ID || !container) return;

  // Toggle add form
  if (addBtn && addForm) {
    addBtn.addEventListener('click', () => {
      addForm.classList.toggle('d-none');
      if (!addForm.classList.contains('d-none') && addInput) addInput.focus();
    });
  }

  // Save new checklist item
  if (saveBtn && addInput) {
    saveBtn.addEventListener('click', addItem);
    addInput.addEventListener('keydown', e => { if (e.key === 'Enter') { e.preventDefault(); addItem(); } });
  }

  function addItem() {
    const content = (addInput.value || '').trim();
    if (!content) return;
    _post(`/tasks/${TASK_ID}/checklist`, { content })
      .then(item => {
        if (item.error) return;
        if (noChecklist) noChecklist.classList.add('d-none');
        const el = _makeItemEl(item);
        if (addForm) container.insertBefore(el, addForm);
        else container.appendChild(el);
        addInput.value = '';
        _refreshProgress();
      });
  }

  // Toggle item
  container.addEventListener('change', e => {
    if (!e.target.matches('.checklist-toggle')) return;
    const id = e.target.dataset.id;
    _post(`/tasks/${TASK_ID}/checklist/${id}/toggle`, {})
      .then(data => {
        const label = e.target.closest('.checklist-item')?.querySelector('.checklist-label');
        if (label) label.classList.toggle('text-decoration-line-through', data.is_done);
        if (label) label.classList.toggle('text-muted', data.is_done);
        _updateProgress(data.done, data.total);
      });
  });

  // Delete item
  container.addEventListener('click', e => {
    const btn = e.target.closest('.checklist-delete');
    if (!btn) return;
    const id = btn.dataset.id;
    _post(`/tasks/${TASK_ID}/checklist/${id}/delete`, {})
      .then(data => {
        btn.closest('.checklist-item')?.remove();
        _updateProgress(data.done, data.total);
        const remaining = container.querySelectorAll('.checklist-item').length;
        if (!remaining && noChecklist) noChecklist.classList.remove('d-none');
      });
  });

  function _refreshProgress() {
    const items = container.querySelectorAll('.checklist-item');
    const done  = container.querySelectorAll('.checklist-toggle:checked').length;
    _updateProgress(done, items.length);
  }

  function _makeItemEl(item) {
    const div = document.createElement('div');
    div.className = 'checklist-item d-flex align-items-center gap-2 py-1';
    div.dataset.id = item.id;
    div.innerHTML = `
      <i class="bi bi-grip-vertical text-muted grip-handle" style="cursor:grab;"></i>
      <input type="checkbox" class="form-check-input checklist-toggle mt-0"
             data-id="${item.id}" ${item.is_done ? 'checked' : ''}>
      <span class="small flex-grow-1 checklist-label ${item.is_done ? 'text-decoration-line-through text-muted' : ''}">
        ${_esc(item.content)}
      </span>
      <button class="btn btn-xs text-muted border-0 checklist-delete" data-id="${item.id}">
        <i class="bi bi-x"></i>
      </button>
    `;
    return div;
  }

  function _esc(s) {
    return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
  }

  // Drag-to-reorder with SortableJS
  if (window.Sortable && container) {
    Sortable.create(container, {
      handle: '.grip-handle',
      animation: 150,
      onEnd() {
        const order = [...container.querySelectorAll('.checklist-item')].map((el, i) => ({
          id: parseInt(el.dataset.id), position: i + 1,
        }));
        _post(`/tasks/${TASK_ID}/checklist/reorder`, order).catch(() => {});
      },
    });
  }

  // ── Subtask quick-add ──────────────────────────────────────────────────────
  const btnAddSubtask  = document.getElementById('btnAddSubtask');
  const subtaskForm    = document.getElementById('subtaskForm');
  const subtaskInput   = document.getElementById('subtaskTitle');
  const btnSaveSubtask = document.getElementById('btnSaveSubtask');
  const subtaskList    = document.getElementById('subtaskList');
  const noSubtasks     = document.getElementById('noSubtasks');

  if (btnAddSubtask && subtaskForm) {
    btnAddSubtask.addEventListener('click', () => {
      subtaskForm.classList.toggle('d-none');
      if (!subtaskForm.classList.contains('d-none') && subtaskInput) subtaskInput.focus();
    });
  }

  if (btnSaveSubtask && subtaskInput) {
    btnSaveSubtask.addEventListener('click', addSubtask);
    subtaskInput.addEventListener('keydown', e => { if (e.key === 'Enter') { e.preventDefault(); addSubtask(); } });
  }

  function addSubtask() {
    const title = (subtaskInput.value || '').trim();
    if (!title) return;
    _post(`/tasks/${TASK_ID}/subtask`, { title })
      .then(data => {
        if (data.error) return;
        if (noSubtasks) noSubtasks.classList.add('d-none');
        const el = document.createElement('a');
        el.href = data.url;
        el.className = 'd-flex align-items-center gap-3 px-3 py-2 border-bottom text-decoration-none';
        el.innerHTML = `
          <span class="badge bg-${data.status_color}" style="font-size:0.62rem;">${_esc(data.status_label)}</span>
          <span class="small">${_esc(data.title)}</span>
          <span class="ms-auto x-small text-muted fw-mono">${_esc(data.task_no)}</span>
        `;
        if (subtaskForm) subtaskList.insertBefore(el, subtaskForm.nextSibling);
        else subtaskList.insertBefore(el, subtaskList.firstChild);
        subtaskInput.value = '';

        // Update badge count
        const badge = document.querySelector('.subtask-count-badge');
        if (badge) badge.textContent = parseInt(badge.textContent || 0) + 1;
      });
  }

})();
