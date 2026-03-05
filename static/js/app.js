/* ═══════════════════════════════════════════════
   CricClubs AI Agent — Frontend JS
═══════════════════════════════════════════════ */

// ── Tab switching ────────────────────────────
function switchTab(name, el) {
  document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
  document.querySelectorAll('.tab-content').forEach(t => t.classList.remove('active'));
  el.classList.add('active');
  document.getElementById(`tab-${name}`).classList.add('active');
}

// ── Status helpers ───────────────────────────
function setStatus(state, text) {
  const dot  = document.getElementById('status-dot');
  const msg  = document.getElementById('status-text');
  dot.className = `status-dot ${state}`;
  msg.textContent = text;
}

function showSteps() {
  document.getElementById('steps').style.display = 'flex';
}

function setStep(id, state, label) {
  const step = document.getElementById(`step-${id}`);
  const lbl  = document.getElementById(`step-${id}-state`);
  step.className = `step ${state}`;
  if (label) lbl.textContent = label;
}

function disableButtons(disabled) {
  document.querySelectorAll('.btn-primary').forEach(b => b.disabled = disabled);
}

// ── Show states ──────────────────────────────
function showLoading(text) {
  document.getElementById('empty-state').style.display   = 'none';
  document.getElementById('report-content').style.display = 'none';
  document.getElementById('error-state').style.display   = 'none';
  document.getElementById('copy-btn').style.display      = 'none';
  const ls = document.getElementById('loading-state');
  ls.style.display = 'flex';
  document.getElementById('loading-text').textContent = text || 'Loading...';
}

function showReport(html, title) {
  document.getElementById('loading-state').style.display = 'none';
  document.getElementById('error-state').style.display   = 'none';
  document.getElementById('empty-state').style.display   = 'none';
  const rc = document.getElementById('report-content');
  rc.style.display = 'block';
  rc.innerHTML = html;
  document.getElementById('report-title').textContent = title || 'Report';
  document.getElementById('copy-btn').style.display = 'inline-flex';
}

function showError(msg) {
  document.getElementById('loading-state').style.display  = 'none';
  document.getElementById('report-content').style.display = 'none';
  document.getElementById('empty-state').style.display    = 'none';
  document.getElementById('error-state').style.display    = 'flex';
  document.getElementById('error-msg').textContent = msg;
  setStatus('error', 'Error');
}

// ── Report text → HTML renderer ──────────────
function renderReport(text) {
  // Split by numbered section headers like "1. MATCH OVERVIEW —"
  // or bold headers like "**MATCH OVERVIEW**"
  const sectionPattern = /(?:^|\n)(?:\d+\.\s+)?([A-Z][A-Z\s\/]+(?:\s*—\s*.*)?)\n/g;

  // Clean up markdown bold
  text = text.replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>');

  // Split into sections on headers that look like "WORD WORD —" or numbered
  const parts = text.split(/\n(?=(?:\d+\.\s+)?[A-Z][A-Z\s]+(?:\s*[—\-–]|\n))/);

  if (parts.length <= 1) {
    // No clear sections — render as single block with nice formatting
    return `<div class="section">
      <div class="section-body">${formatBody(text)}</div>
    </div>`;
  }

  return parts.map(part => {
    part = part.trim();
    if (!part) return '';

    // Try to extract a header from first line
    const lines = part.split('\n');
    const firstLine = lines[0].trim();
    const isHeader = /^(\d+\.\s+)?[A-Z][A-Z\s\-—–\/]+$/.test(firstLine.replace(/\s*[—\-–].*$/, '').trim());

    if (isHeader) {
      const title = firstLine.replace(/^\d+\.\s+/, '').replace(/\s*[—\-–].*$/, '').trim();
      const body  = lines.slice(1).join('\n').trim();
      return `<div class="section">
        <div class="section-title">${title}</div>
        <div class="section-body">${formatBody(body)}</div>
      </div>`;
    } else {
      return `<div class="section">
        <div class="section-body">${formatBody(part)}</div>
      </div>`;
    }
  }).join('');
}

function formatBody(text) {
  // Bold already replaced, now handle line breaks and stat highlighting
  return text
    .replace(/\n\n/g, '</p><p>')
    .replace(/\n/g, '<br>')
    .replace(/<p><\/p>/g, '');
}

// ── Copy report ──────────────────────────────
function copyReport() {
  const text = document.getElementById('report-content').innerText;
  navigator.clipboard.writeText(text).then(() => {
    const btn = document.getElementById('copy-btn');
    btn.textContent = '✓ Copied!';
    setTimeout(() => btn.textContent = '⎘ Copy', 2000);
  });
}

// ── Reset session ────────────────────────────
async function resetSession() {
  await fetch('/api/reset', { method: 'POST' });
  document.getElementById('empty-state').style.display    = 'flex';
  document.getElementById('loading-state').style.display  = 'none';
  document.getElementById('report-content').style.display = 'none';
  document.getElementById('error-state').style.display    = 'none';
  document.getElementById('copy-btn').style.display       = 'none';
  document.getElementById('steps').style.display          = 'none';
  setStatus('idle', 'Ready');
  // Reset chat
  document.getElementById('chat-messages').innerHTML = `
    <div class="chat-bubble bot">
      <span class="bubble-author">AI Analyst</span>
      <span class="bubble-text">Session reset. Load a new match or league report to get started.</span>
    </div>`;
}

// ── Scorecard mode ───────────────────────────
async function runScorecard() {
  const matchId = document.getElementById('match-id-input').value.trim();
  if (!matchId) { alert('Please enter a Match ID.'); return; }

  disableButtons(true);
  showLoading('Launching browser & scraping CricClubs...');
  setStatus('loading', 'Scraping...');
  showSteps();
  setStep('scrape', 'active', 'running...');
  setStep('ai', '', 'waiting');
  setStep('done', '', 'waiting');

  const body = new FormData();
  body.append('match_id', matchId);

  try {
    document.getElementById('loading-text').textContent = 'Scraping match data...';
    setStep('scrape', 'active', 'fetching...');

    const res = await fetch('/api/scorecard', { method: 'POST', body });
    const data = await res.json();

    if (data.status !== 'ok') throw new Error(data.message);

    setStep('scrape', 'done', 'done ✓');
    setStep('ai', 'active', 'analysing...');
    document.getElementById('loading-text').textContent = 'AI generating report...';

    // Small visual delay so user sees the AI step
    await delay(400);
    setStep('ai', 'done', 'done ✓');
    setStep('done', 'done', 'ready ✓');
    setStatus('done', `Match ${matchId} loaded`);

    showReport(renderReport(data.report), `Match Report — #${matchId}`);

    addChatBubble('bot', `Match ${matchId} loaded! Ask me anything about it — top scorers, bowling analysis, fantasy picks, or anything else.`);

  } catch (err) {
    showError(`Failed: ${err.message}`);
    setStep('scrape', '', 'failed');
  } finally {
    disableButtons(false);
  }
}

// ── League mode ──────────────────────────────
async function runLeague() {
  disableButtons(true);
  showLoading('Scraping league data (results, standings, batting, bowling)...');
  setStatus('loading', 'Scraping league...');
  showSteps();
  setStep('scrape', 'active', 'running...');
  setStep('ai', '', 'waiting');
  setStep('done', '', 'waiting');

  try {
    const res  = await fetch('/api/league', { method: 'POST' });
    const data = await res.json();

    if (data.status !== 'ok') throw new Error(data.message);

    setStep('scrape', 'done', 'done ✓');
    setStep('ai', 'done', 'done ✓');
    setStep('done', 'done', 'ready ✓');
    setStatus('done', 'League loaded');

    showReport(renderReport(data.report), 'League Overview');
    addChatBubble('bot', 'League data loaded! I can answer questions about standings, top performers, form guides, and more.');

  } catch (err) {
    showError(`Failed: ${err.message}`);
  } finally {
    disableButtons(false);
  }
}

// ── Multi match mode ─────────────────────────
async function runMulti() {
  const ids = document.getElementById('multi-ids-input').value.trim();
  if (!ids) { alert('Please enter at least two match IDs.'); return; }

  disableButtons(true);
  showLoading(`Scraping ${ids.split(',').length} matches...`);
  setStatus('loading', 'Scraping matches...');
  showSteps();
  setStep('scrape', 'active', 'running...');
  setStep('ai', '', 'waiting');
  setStep('done', '', 'waiting');

  const body = new FormData();
  body.append('match_ids', ids);

  try {
    const res  = await fetch('/api/multi', { method: 'POST', body });
    const data = await res.json();

    if (data.status !== 'ok') throw new Error(data.message);

    setStep('scrape', 'done', 'done ✓');
    setStep('ai', 'done', 'done ✓');
    setStep('done', 'done', 'ready ✓');
    setStatus('done', `${data.match_ids.length} matches loaded`);

    showReport(renderReport(data.report), `Multi-Match Analysis — ${data.match_ids.join(', ')}`);
    addChatBubble('bot', `Loaded ${data.match_ids.length} matches. Ask me to compare teams, find the best performers, or pick a fantasy XI!`);

  } catch (err) {
    showError(`Failed: ${err.message}`);
  } finally {
    disableButtons(false);
  }
}

// ── Chat ─────────────────────────────────────
async function sendChat() {
  const input = document.getElementById('chat-input');
  const msg   = input.value.trim();
  if (!msg) return;

  input.value = '';
  addChatBubble('user', msg);

  // Typing indicator
  const typingId = addTypingBubble();
  document.getElementById('btn-send').disabled = true;

  const body = new FormData();
  body.append('message', msg);

  try {
    const res  = await fetch('/api/chat', { method: 'POST', body });
    const data = await res.json();
    removeTypingBubble(typingId);

    if (data.status !== 'ok') {
      addChatBubble('bot', `⚠️ ${data.message}`);
    } else {
      addChatBubble('bot', data.reply);
    }
  } catch (err) {
    removeTypingBubble(typingId);
    addChatBubble('bot', `⚠️ Error: ${err.message}`);
  } finally {
    document.getElementById('btn-send').disabled = false;
    input.focus();
  }
}

function addChatBubble(role, text) {
  const msgs = document.getElementById('chat-messages');
  const div  = document.createElement('div');
  div.className = `chat-bubble ${role}`;
  div.innerHTML = `
    <span class="bubble-author">${role === 'user' ? 'You' : 'AI Analyst'}</span>
    <span class="bubble-text">${escHtml(text)}</span>`;
  msgs.appendChild(div);
  msgs.scrollTop = msgs.scrollHeight;
  return div;
}

function addTypingBubble() {
  const msgs = document.getElementById('chat-messages');
  const id   = 'typing-' + Date.now();
  const div  = document.createElement('div');
  div.id        = id;
  div.className = 'chat-bubble bot bubble-typing';
  div.innerHTML = `<span class="bubble-author">AI Analyst</span><span class="bubble-text"></span>`;
  msgs.appendChild(div);
  msgs.scrollTop = msgs.scrollHeight;
  return id;
}

function removeTypingBubble(id) {
  const el = document.getElementById(id);
  if (el) el.remove();
}

function escHtml(str) {
  return str
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/\n/g, '<br>');
}


function delay(ms) { return new Promise(r => setTimeout(r, ms)); }
