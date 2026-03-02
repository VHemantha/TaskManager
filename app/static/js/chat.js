// ── Team Chat & Task Assignment Interface ──────────────────────────────────────
(function () {
  if (typeof io === 'undefined' || typeof CHANNEL === 'undefined') return;

  const socket = io('/chat', { transports: ['websocket', 'polling'] });
  const msgInput = document.getElementById('msgInput');
  const chatWindow = document.getElementById('chatWindow');
  const dropdownEl = document.getElementById('autocompleteDropdown');

  // Task preview elements (leaders/admins only)
  const previewCard = document.getElementById('taskPreviewCard');
  const previewBody = document.getElementById('previewBody');

  // Task-detect indicator bar (leaders/admins only)
  const taskDetectBar = document.getElementById('taskDetectBar');
  const taskDetectSummary = document.getElementById('taskDetectSummary');

  // Send button
  const btnSend = document.getElementById('btnSendChat');
  const btnSendText = document.getElementById('btnSendText');
  const btnSendIcon = document.getElementById('btnSendIcon');

  // File upload
  const fileInput = document.getElementById('chatFileInput');
  const pendingFileBar = document.getElementById('pendingFileBar');
  const pendingFileName = document.getElementById('pendingFileName');
  const btnClearFile = document.getElementById('btnClearFile');

  let parsedData = null;
  let typingTimer = null;

  // ── CSRF ────────────────────────────────────────────────────────────────────
  function getCsrf() {
    const meta = document.querySelector('meta[name="csrf-token"]');
    return meta ? meta.getAttribute('content') : '';
  }

  // ── Connect & join channel ─────────────────────────────────────────────────
  socket.on('connect', () => {
    socket.emit('join_channel', { channel: CHANNEL });
  });

  // ── Messages from OTHER users (SocketIO broadcast) ─────────────────────────
  socket.on('new_message', msg => {
    if (msg.sender_id === CURRENT_USER_ID) return; // own messages already appended
    appendMessage(msg);
  });

  // ── Typing indicator ───────────────────────────────────────────────────────
  socket.on('user_typing', data => {
    if (data.user_id === CURRENT_USER_ID) return;
    const indicator = document.getElementById('typingIndicator');
    const typingText = document.getElementById('typingText');
    if (indicator && typingText) {
      typingText.textContent = `${data.name} is typing…`;
      indicator.classList.remove('d-none');
      clearTimeout(typingTimer);
      typingTimer = setTimeout(() => indicator.classList.add('d-none'), 2500);
    }
  });

  // ── Real-time tag detection: update UI as user types ──────────────────────
  msgInput.addEventListener('input', () => {
    if (IS_LEADER) updateTaskDetectBar();
    handleAutocomplete();
    socket.emit('typing', { channel: CHANNEL });
  });

  function updateTaskDetectBar() {
    const text = msgInput.value.trim();
    const hasMention = /@\w+/.test(text);

    if (!hasMention || !taskDetectBar) {
      if (taskDetectBar) taskDetectBar.classList.add('d-none');
      if (btnSendText) btnSendText.textContent = 'Send';
      if (btnSendIcon) btnSendIcon.className = 'bi bi-send me-1';
      if (btnSend) btnSend.classList.replace('btn-success', 'btn-primary');
      return;
    }

    // Show task detect bar with a quick summary from visible tags
    const mentions = [...text.matchAll(/@(\w+)/g)].map(m => '@' + m[1]);
    const category = (text.match(/#(\w+)/) || [])[1];
    const priority = (text.match(/!(urgent|high|medium|low)/i) || [])[1];
    const due = (text.match(/~(\S+)/) || [])[1];

    let summary = mentions.join(', ');
    if (category) summary += ` · #${category}`;
    if (priority) summary += ` · ${priority}`;
    if (due) summary += ` · ~${due}`;

    if (taskDetectSummary) taskDetectSummary.textContent = summary;
    taskDetectBar.classList.remove('d-none');

    // Change Send button to indicate task creation
    if (btnSendText) btnSendText.textContent = 'Assign Task';
    if (btnSendIcon) btnSendIcon.className = 'bi bi-check2-circle me-1';
    if (btnSend) { btnSend.classList.replace('btn-primary', 'btn-success'); }
  }

  // ── Send button ────────────────────────────────────────────────────────────
  btnSend.addEventListener('click', sendMessage);

  msgInput.addEventListener('keydown', e => {
    if (e.key === 'Enter' && e.ctrlKey && IS_LEADER) {
      e.preventDefault();
      const btn = document.getElementById('btnPreview');
      if (btn) btn.click();
    }
  });

  // ── Main send dispatch ────────────────────────────────────────────────────
  function sendMessage() {
    const text = msgInput.value.trim();
    const hasFile = fileInput && fileInput.files.length > 0;

    if (!text && !hasFile) return;

    if (hasFile) {
      uploadFile(text); // text is used as caption
      return;
    }

    // Leaders: if message contains @mention → auto-create a task
    if (IS_LEADER && /@\w+/.test(text)) {
      autoCreateTask(text);
      return;
    }

    // Plain message
    sendPlainMessage(text);
  }

  // ── Auto-create task from tagged message ───────────────────────────────────
  function autoCreateTask(text) {
    setSendLoading(true);

    fetch('/api/chat/parse', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'X-CSRFToken': getCsrf() },
      body: JSON.stringify({ text }),
    })
      .then(r => r.json())
      .then(parsed => {
        if (parsed.error || !parsed.assignees || parsed.assignees.length === 0) {
          // Parser didn't find valid assignees — fall back to plain message
          setSendLoading(false);
          sendPlainMessage(text);
          return null;
        }
        // Show brief inline preview before creating
        showInlinePreview(parsed);

        return fetch('/api/tasks/from-chat', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json', 'X-CSRFToken': getCsrf() },
          body: JSON.stringify({
            channel: CHANNEL,
            title: parsed.clean_message,
            clean_message: parsed.clean_message,
            assignee_ids: parsed.assignees.map(u => u.id),
            category_name: parsed.categories.length > 0 ? parsed.categories[0] : null,
            priority: parsed.priority,
            due_date: parsed.due_date,
            client_id: parsed.client ? parsed.client.id : null,
            estimated_hours: parsed.estimated_hours,
            raw_message: parsed.raw_message,
          }),
        });
      })
      .then(r => r ? r.json() : null)
      .then(data => {
        if (!data) return;
        if (data.error) { showAlert(data.error, 'danger'); return; }

        msgInput.value = '';
        hidePreview();
        if (taskDetectBar) taskDetectBar.classList.add('d-none');
        resetSendButton();

        // Success banner — stays until redirect
        showAlert(
          `<i class="bi bi-check-circle-fill me-2"></i>` +
          `<strong>${data.task_no}</strong> created &amp; assigned! ` +
          `<a href="${data.task_url}" class="alert-link fw-bold">View Task →</a>`,
          'success',
          false
        );
        // Redirect to new task after 2.5s so user can see the confirmation
        setTimeout(() => { window.location.href = data.task_url; }, 2500);
      })
      .catch(() => {
        showAlert('Could not create task. Please try again.', 'danger');
        setSendLoading(false);
      })
      .finally(() => setSendLoading(false));
  }

  // Show a compact inline preview in the chat window while task is being created
  function showInlinePreview(parsed) {
    const assigneeNames = parsed.assignees.map(u => u.name).join(', ');
    const div = document.createElement('div');
    div.className = 'text-center text-muted small py-2 px-3';
    div.id = 'inlineCreating';
    div.innerHTML =
      `<span class="spinner-border spinner-border-sm me-2"></span>` +
      `Creating task for <strong>${escapeHtml(assigneeNames)}</strong>…`;
    const typingEl = document.getElementById('typingIndicator');
    chatWindow.insertBefore(div, typingEl);
    chatWindow.scrollTop = chatWindow.scrollHeight;
  }

  // ── Plain message via HTTP POST ────────────────────────────────────────────
  function sendPlainMessage(text) {
    fetch('/chat/send', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'X-CSRFToken': getCsrf() },
      body: JSON.stringify({ channel: CHANNEL, content: text }),
    })
      .then(r => r.json())
      .then(msg => {
        if (msg.error) { showAlert(msg.error, 'danger'); return; }
        appendMessage(msg);
        msgInput.value = '';
        hidePreview();
        resetSendButton();
        if (taskDetectBar) taskDetectBar.classList.add('d-none');
      })
      .catch(() => showAlert('Failed to send message.', 'danger'));
  }

  // ── File upload ────────────────────────────────────────────────────────────
  document.getElementById('btnAttachFile').addEventListener('click', () => fileInput.click());

  if (fileInput) {
    fileInput.addEventListener('change', () => {
      const file = fileInput.files[0];
      if (!file) return;
      if (pendingFileBar && pendingFileName) {
        pendingFileName.textContent = `${file.name} (${formatBytes(file.size)})`;
        pendingFileBar.classList.remove('d-none');
      }
    });
  }
  if (btnClearFile) {
    btnClearFile.addEventListener('click', () => {
      fileInput.value = '';
      if (pendingFileBar) pendingFileBar.classList.add('d-none');
    });
  }

  function uploadFile(caption) {
    const formData = new FormData();
    formData.append('file', fileInput.files[0]);
    formData.append('channel', CHANNEL);
    if (caption) formData.append('caption', caption);

    setSendLoading(true);
    fetch('/chat/upload', {
      method: 'POST',
      headers: { 'X-CSRFToken': getCsrf() },
      body: formData,
    })
      .then(r => r.json())
      .then(msg => {
        if (msg.error) { showAlert(msg.error, 'danger'); return; }
        appendMessage(msg);
        msgInput.value = '';
        fileInput.value = '';
        if (pendingFileBar) pendingFileBar.classList.add('d-none');
      })
      .catch(() => showAlert('File upload failed.', 'danger'))
      .finally(() => setSendLoading(false));
  }

  // ── Preview button (optional verification step) ────────────────────────────
  const btnPreview = document.getElementById('btnPreview');
  if (btnPreview) {
    btnPreview.addEventListener('click', () => {
      const text = msgInput.value.trim();
      if (!text) return;
      btnPreview.disabled = true;
      fetch('/api/chat/parse', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'X-CSRFToken': getCsrf() },
        body: JSON.stringify({ text }),
      })
        .then(r => r.json())
        .then(data => {
          if (data.error) { showAlert(data.error, 'danger'); return; }
          parsedData = data;
          renderPreview(data);
          if (previewCard) previewCard.classList.remove('d-none');
        })
        .catch(() => showAlert('Failed to parse message.', 'danger'))
        .finally(() => { btnPreview.disabled = false; });
    });
  }

  // ── Confirm from preview card ──────────────────────────────────────────────
  const btnConfirmTask = document.getElementById('btnConfirmTask');
  if (btnConfirmTask) {
    btnConfirmTask.addEventListener('click', () => {
      if (!parsedData) return;
      btnConfirmTask.disabled = true;
      btnConfirmTask.innerHTML =
        '<span class="spinner-border spinner-border-sm me-1"></span>Creating…';

      fetch('/api/tasks/from-chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'X-CSRFToken': getCsrf() },
        body: JSON.stringify({
          channel: CHANNEL,
          title: parsedData.clean_message,
          clean_message: parsedData.clean_message,
          assignee_ids: parsedData.assignees.map(u => u.id),
          category_name: parsedData.categories.length > 0 ? parsedData.categories[0] : null,
          priority: parsedData.priority,
          due_date: parsedData.due_date,
          client_id: parsedData.client ? parsedData.client.id : null,
          estimated_hours: parsedData.estimated_hours,
          raw_message: parsedData.raw_message,
        }),
      })
        .then(r => r.json())
        .then(data => {
          if (data.error) { showAlert(data.error, 'danger'); return; }
          hidePreview();
          msgInput.value = '';
          resetSendButton();
          if (taskDetectBar) taskDetectBar.classList.add('d-none');
          showAlert(
            `<i class="bi bi-check-circle-fill me-2"></i>` +
            `<strong>${data.task_no}</strong> created! ` +
            `<a href="${data.task_url}" class="alert-link">View Task →</a>`,
            'success', false
          );
          setTimeout(() => { window.location.href = data.task_url; }, 2500);
        })
        .catch(() => showAlert('Failed to create task.', 'danger'))
        .finally(() => {
          btnConfirmTask.disabled = false;
          btnConfirmTask.innerHTML =
            '<i class="bi bi-check-lg me-1"></i>Confirm &amp; Create Task';
        });
    });
  }

  const btnCancelPreview = document.getElementById('btnCancelPreview');
  if (btnCancelPreview) btnCancelPreview.addEventListener('click', hidePreview);

  // ── Load older messages ────────────────────────────────────────────────────
  const btnLoadMore = document.getElementById('btnLoadMore');
  if (btnLoadMore) {
    btnLoadMore.addEventListener('click', () => {
      const firstEl = chatWindow.querySelector('[data-msg-id]');
      const beforeId = firstEl ? firstEl.dataset.msgId : '';
      const url = `/chat/history?channel=${encodeURIComponent(CHANNEL)}${beforeId ? '&before_id=' + beforeId : ''}`;
      fetch(url)
        .then(r => r.json())
        .then(msgs => {
          if (!msgs.length) {
            btnLoadMore.disabled = true;
            btnLoadMore.title = 'No more messages';
            return;
          }
          const scrollBottom = chatWindow.scrollHeight - chatWindow.scrollTop;
          msgs.reverse().forEach(msg => prependMessage(msg));
          chatWindow.scrollTop = chatWindow.scrollHeight - scrollBottom;
        });
    });
  }

  // ── Autocomplete ───────────────────────────────────────────────────────────
  function handleAutocomplete() {
    const val = msgInput.value;
    const pos = msgInput.selectionStart;
    const before = val.substring(0, pos);
    const atMatch = before.match(/@(\w*)$/);
    const hashMatch = before.match(/#(\w*)$/);

    if (atMatch) fetchUsers(atMatch[1]);
    else if (hashMatch && IS_LEADER) fetchCategories(hashMatch[1]);
    else dropdownEl.classList.add('d-none');
  }

  function fetchUsers(q) {
    fetch(`/api/users/search?q=${encodeURIComponent(q)}`)
      .then(r => r.json())
      .then(users => {
        if (!users.length) { dropdownEl.classList.add('d-none'); return; }
        dropdownEl.innerHTML = users.map(u =>
          `<div class="autocomplete-item" data-name="${u.name}" data-type="user">
            <span class="fw-bold">${escapeHtml(u.name)}</span>
            <span class="text-muted small ms-1">${escapeHtml(u.role)}</span>
           </div>`
        ).join('');
        dropdownEl.classList.remove('d-none');
        bindAutocompleteClicks('@');
      });
  }

  function fetchCategories(q) {
    fetch('/api/categories')
      .then(r => r.json())
      .then(cats => {
        const filtered = cats.filter(c => c.name.toLowerCase().startsWith(q.toLowerCase()));
        if (!filtered.length) { dropdownEl.classList.add('d-none'); return; }
        dropdownEl.innerHTML = filtered.map(c =>
          `<div class="autocomplete-item" data-name="${c.name}" data-type="cat">
            <span style="color:${c.color_code}" class="fw-bold">#${c.name}</span>
           </div>`
        ).join('');
        dropdownEl.classList.remove('d-none');
        bindAutocompleteClicks('#');
      });
  }

  function bindAutocompleteClicks(prefix) {
    dropdownEl.querySelectorAll('.autocomplete-item').forEach(item => {
      item.addEventListener('click', () => {
        const name = item.dataset.name;
        const val = msgInput.value;
        const pos = msgInput.selectionStart;
        const before = val.substring(0, pos);
        const tag = prefix === '@' ? `@${name.split(' ')[0].toLowerCase()}` : `#${name}`;
        const replaced = before.replace(prefix === '@' ? /@(\w*)$/ : /#(\w*)$/, tag + ' ');
        msgInput.value = replaced + val.substring(pos);
        msgInput.focus();
        dropdownEl.classList.add('d-none');
        if (IS_LEADER) updateTaskDetectBar();
      });
    });
  }

  document.addEventListener('click', e => {
    if (!dropdownEl.contains(e.target) && e.target !== msgInput) {
      dropdownEl.classList.add('d-none');
    }
  });

  // ── DOM helpers ────────────────────────────────────────────────────────────
  function appendMessage(msg) {
    const isOwn = msg.sender_id === CURRENT_USER_ID;
    const div = buildMessageEl(msg, isOwn);
    const typingEl = document.getElementById('typingIndicator');
    const creating = document.getElementById('inlineCreating');
    chatWindow.insertBefore(div, creating || typingEl);
    if (creating) creating.remove();
    chatWindow.scrollTop = chatWindow.scrollHeight;
    const placeholder = chatWindow.querySelector('.text-center.text-muted.py-5');
    if (placeholder) placeholder.remove();
  }

  function prependMessage(msg) {
    const isOwn = msg.sender_id === CURRENT_USER_ID;
    chatWindow.insertBefore(buildMessageEl(msg, isOwn), chatWindow.firstChild);
  }

  function buildMessageEl(msg, isOwn) {
    const div = document.createElement('div');
    div.className = `d-flex mb-3 ${isOwn ? 'justify-content-end msg-own' : 'msg-other'}`;
    div.dataset.msgId = msg.id;

    const avatarHtml = !isOwn
      ? `<span class="avatar-initials avatar-sm bg-secondary text-white me-2 flex-shrink-0"
              title="${escapeHtml(msg.sender_name)}">${escapeHtml(msg.sender_initials || '??')}</span>`
      : '';
    const senderHtml = !isOwn
      ? `<div class="x-small fw-bold mb-1">${escapeHtml(msg.sender_name)}</div>` : '';

    let attachHtml = '';
    if (msg.attachment_filename) {
      const icon = (msg.attachment_mimetype || '').startsWith('image/')
        ? 'bi-image'
        : (msg.attachment_mimetype || '').includes('pdf') ? 'bi-file-pdf' : 'bi-paperclip';
      attachHtml = `
        <div class="mt-1">
          <a href="/chat/attachment/${escapeHtml(msg.attachment_path)}"
             class="attach-chip" target="_blank" rel="noopener">
            <i class="bi ${icon}"></i>
            ${escapeHtml(msg.attachment_filename)}
            <span class="opacity-75">${escapeHtml(msg.attachment_size_display || '')}</span>
          </a>
        </div>`;
    }

    const taskHtml = msg.linked_task_id
      ? `<div class="mt-1">
           <a href="/tasks/${msg.linked_task_id}"
              class="badge bg-success text-white text-decoration-none">
             <i class="bi bi-check2 me-1"></i>Task Created
           </a>
         </div>` : '';

    const timeStr = (msg.created_at || '').substring(11, 16);
    const timeCls = isOwn ? 'text-white-50' : 'text-muted';

    div.innerHTML = `
      ${avatarHtml}
      <div class="msg-bubble p-2 rounded-3">
        ${senderHtml}
        <div class="small">${escapeHtml(msg.content)}</div>
        ${attachHtml}
        ${taskHtml}
        <div class="x-small ${timeCls} mt-1">${timeStr}</div>
      </div>`;
    return div;
  }

  function renderPreview(data) {
    if (!previewBody) return;
    const assigneeHtml = data.assignees.length > 0
      ? data.assignees.map(u => `<span class="badge bg-primary me-1">${escapeHtml(u.name)}</span>`).join('')
      : '<span class="text-muted">None</span>';
    const catHtml = data.categories.length > 0
      ? data.categories.map(c => `<span class="badge bg-success me-1">#${escapeHtml(c)}</span>`).join('')
      : '<span class="text-muted">None</span>';
    previewBody.innerHTML = `
      <div class="mb-2"><strong>Title:</strong> ${escapeHtml(data.clean_message)}</div>
      <div class="mb-2"><strong>Assignees:</strong> ${assigneeHtml}</div>
      <div class="mb-2"><strong>Category:</strong> ${catHtml}</div>
      <div class="mb-2"><strong>Priority:</strong>
        <span class="badge bg-warning text-dark">${escapeHtml(data.priority)}</span></div>
      <div class="mb-2"><strong>Due:</strong> ${escapeHtml(data.due_date || '—')}</div>
      <div class="mb-2"><strong>Client:</strong> ${data.client ? escapeHtml(data.client.name) : '—'}</div>
      <div class="mb-0"><strong>Est. Hours:</strong> ${data.estimated_hours ? data.estimated_hours + 'h' : '—'}</div>`;
  }

  function hidePreview() {
    if (previewCard) previewCard.classList.add('d-none');
    parsedData = null;
  }

  // ── Button state helpers ───────────────────────────────────────────────────
  function setSendLoading(loading) {
    if (!btnSend) return;
    btnSend.disabled = loading;
    if (loading) {
      btnSend.innerHTML =
        '<span class="spinner-border spinner-border-sm me-1"></span>Processing…';
    } else {
      resetSendButton();
    }
  }

  function resetSendButton() {
    if (!btnSend) return;
    btnSend.disabled = false;
    btnSend.className = 'btn btn-sm btn-primary';
    btnSend.innerHTML = '<i class="bi bi-send me-1"></i><span id="btnSendText">Send</span>';
  }

  function showAlert(msg, type, autoDismiss = true) {
    const div = document.createElement('div');
    div.className = `alert alert-${type} alert-dismissible fade show position-fixed top-0 start-50 translate-middle-x mt-5`;
    div.style.zIndex = '1100';
    div.style.minWidth = '340px';
    div.innerHTML = `${msg}<button type="button" class="btn-close" data-bs-dismiss="alert"></button>`;
    document.body.appendChild(div);
    if (autoDismiss) setTimeout(() => div.remove(), 4500);
  }

  function formatBytes(bytes) {
    if (bytes < 1024) return bytes + ' B';
    if (bytes < 1048576) return (bytes / 1024).toFixed(1) + ' KB';
    return (bytes / 1048576).toFixed(1) + ' MB';
  }

  function escapeHtml(str) {
    return String(str || '').replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
  }
})();
