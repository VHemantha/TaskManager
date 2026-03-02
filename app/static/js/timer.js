/* ══════════════════════════════════════════════════════════════════════════════
   Obsidian Workspace — Live Timer
   ══════════════════════════════════════════════════════════════════════════════ */

window.tmTimer = (function () {
  'use strict';

  let state = null;    // { taskId, taskNo, startMs }
  let tickInterval = null;

  const widget   = document.getElementById('timerWidget');
  const display  = document.getElementById('timerDisplay');

  function _pad(n) { return String(n).padStart(2, '0'); }

  function _fmt(ms) {
    const totalSec = Math.floor(ms / 1000);
    const h = Math.floor(totalSec / 3600);
    const m = Math.floor((totalSec % 3600) / 60);
    const s = totalSec % 60;
    return `${_pad(h)}:${_pad(m)}:${_pad(s)}`;
  }

  function _csrf() {
    const meta = document.querySelector('meta[name="csrf-token"]');
    return meta ? meta.content : '';
  }

  function _updateWidget() {
    if (!state || !widget) return;
    const elapsed = Date.now() - state.startMs;
    if (display) display.textContent = _fmt(elapsed);
    widget.classList.add('running');
    widget.style.opacity = '1';
  }

  function start(taskId, taskNo) {
    fetch('/api/timer/start', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'X-CSRFToken': _csrf() },
      body: JSON.stringify({ task_id: taskId }),
    })
    .then(r => r.json())
    .then(data => {
      if (data.success) {
        state = { taskId, taskNo, startMs: Date.now() };
        _startTick();
        _syncBtn(taskId, true);
      }
    })
    .catch(() => {});
  }

  function stop() {
    fetch('/api/timer/stop', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'X-CSRFToken': _csrf() },
    })
    .then(r => r.json())
    .then(data => {
      if (data.success) {
        const taskId = state ? state.taskId : null;
        state = null;
        _stopTick();
        _resetWidget();
        _syncBtn(taskId, false);
        if (data.hours) {
          _showToast(`⏱ ${data.hours.toFixed(2)}h logged automatically.`);
        }
      }
    })
    .catch(() => {});
  }

  function toggle(taskId, taskNo) {
    if (state && state.taskId === taskId) {
      stop();
    } else if (state) {
      // Stop current first, then start new
      stop();
      setTimeout(() => start(taskId, taskNo), 400);
    } else {
      start(taskId, taskNo);
    }
  }

  function openStopDialog() {
    if (!state) return;
    if (confirm(`Stop timer for ${state.taskNo}? Hours will be logged automatically.`)) {
      stop();
    }
  }

  function restoreFromServer(serverTimer) {
    if (!serverTimer || !serverTimer.task_id) return;
    const startMs = new Date(serverTimer.start_time).getTime();
    state = { taskId: serverTimer.task_id, taskNo: serverTimer.task_no, startMs };
    _startTick();
    _syncBtn(serverTimer.task_id, true);
  }

  function _startTick() {
    if (tickInterval) clearInterval(tickInterval);
    _updateWidget();
    tickInterval = setInterval(_updateWidget, 1000);
  }

  function _stopTick() {
    if (tickInterval) { clearInterval(tickInterval); tickInterval = null; }
  }

  function _resetWidget() {
    if (!widget) return;
    widget.classList.remove('running');
    widget.style.opacity = '0.45';
    if (display) display.textContent = '--:--:--';
  }

  function _syncBtn(taskId, running) {
    const btn = document.getElementById('btnStartTimer');
    const label = document.getElementById('timerBtnLabel');
    if (!btn || !label) return;
    const btnTaskId = parseInt(btn.dataset.taskId);
    if (btnTaskId !== taskId) return;
    if (running) {
      btn.innerHTML = '<i class="bi bi-stop-fill me-1"></i><span id="timerBtnLabel">Stop Timer</span>';
    } else {
      btn.innerHTML = '<i class="bi bi-play-fill me-1"></i><span id="timerBtnLabel">Start Timer</span>';
    }
  }

  function _showToast(msg) {
    const el = document.createElement('div');
    el.className = 'alert alert-success alert-dismissible fade show position-fixed';
    el.style.cssText = 'top:80px;right:20px;z-index:9999;min-width:260px;box-shadow:0 4px 20px rgba(0,0,0,0.15)';
    el.innerHTML = `${msg}<button type="button" class="btn-close" data-bs-dismiss="alert"></button>`;
    document.body.appendChild(el);
    setTimeout(() => el.remove(), 5000);
  }

  return { start, stop, toggle, openStopDialog, restoreFromServer };
})();
