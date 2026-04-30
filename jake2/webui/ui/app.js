const composer = document.getElementById('composer');
const sendBtn = document.getElementById('sendBtn');
const messageList = document.getElementById('messageList');
const statusText = document.getElementById('statusText');
const threadTitle = document.getElementById('threadTitle');
const buildStamp = document.getElementById('buildStamp');
const threadList = document.getElementById('threadList');

const state = {
  history: [],
};

function appendMessage(role, text, rawResult = null) {
  const article = document.createElement('article');
  article.className = `message ${role}`;
  const roleNode = document.createElement('div');
  roleNode.className = 'message-role';
  roleNode.textContent = role === 'user' ? 'You' : 'Jake';
  const body = document.createElement('div');
  body.className = 'message-body';
  body.textContent = text;
  article.appendChild(roleNode);
  article.appendChild(body);
  if (role === 'assistant' && rawResult) {
    const toggle = document.createElement('button');
    toggle.type = 'button';
    toggle.className = 'raw-toggle';
    toggle.textContent = '▶ show raw data';
    const rawBlock = document.createElement('pre');
    rawBlock.className = 'raw-result';
    rawBlock.hidden = true;
    rawBlock.textContent = JSON.stringify(rawResult, null, 2);
    toggle.addEventListener('click', () => {
      const expanded = rawBlock.hidden;
      rawBlock.hidden = !expanded;
      toggle.textContent = expanded ? '▼ hide raw data' : '▶ show raw data';
    });
    article.appendChild(toggle);
    article.appendChild(rawBlock);
  }
  messageList.appendChild(article);
  messageList.scrollTop = messageList.scrollHeight;
}

async function fetchJson(url, options = {}) {
  const response = await fetch(url, options);
  if (!response.ok) {
    throw new Error(`${response.status} ${await response.text()}`);
  }
  return await response.json();
}

async function loadStats() {
  try {
    const stats = await fetchJson('/api/stats');
    threadList.innerHTML = `
      <div class="stat-card"><strong>${stats.online_devices ?? 0}</strong><span>Online devices</span></div>
      <div class="stat-card"><strong>${stats.online_links ?? 0}</strong><span>Online links</span></div>
      <div class="stat-card"><strong>${stats.total_links ?? 0}</strong><span>Total links</span></div>
      <div class="stat-card"><strong>${stats.cpes_online ?? 0}</strong><span>CPEs online</span></div>
      <div class="stat-card"><strong>${stats.alerts_open ?? 0}</strong><span>Alerts open</span></div>
    `;
  } catch (error) {
    threadList.innerHTML = '<div class="stat-card"><strong>0</strong><span>Stats unavailable</span></div>';
  }
}

async function loadBrief() {
  try {
    const payload = await fetchJson('/api/brief');
    buildStamp.textContent = payload.brief ? 'live brief loaded' : 'brief unavailable';
    if (payload.brief) {
      appendMessage('assistant', payload.brief);
    }
  } catch (error) {
    buildStamp.textContent = 'brief unavailable';
  }
}

async function sendMessage() {
  const message = composer.value.trim();
  if (!message) return;
  composer.value = '';
  appendMessage('user', message);
  statusText.textContent = 'Jake is thinking…';
  try {
    const payload = await fetchJson('/api/chat', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ message, history: state.history }),
    });
    const answer = payload.answer || '';
    appendMessage('assistant', answer, payload.raw_result ?? null);
    state.history.push({ role: 'user', content: message });
    state.history.push({ role: 'assistant', content: answer });
  } catch (error) {
    appendMessage('assistant', `Jake encountered an error: ${error.message}`);
  } finally {
    statusText.textContent = '';
  }
}

sendBtn.addEventListener('click', sendMessage);
composer.addEventListener('keydown', (event) => {
  if (event.key === 'Enter' && !event.shiftKey) {
    event.preventDefault();
    void sendMessage();
  }
});

document.querySelectorAll('.chip').forEach((button) => {
  button.addEventListener('click', () => {
    composer.value = button.dataset.prompt || '';
    composer.focus();
  });
});

threadTitle.textContent = 'Cognitive Console';
void loadStats();
void loadBrief();
