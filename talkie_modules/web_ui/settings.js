// Talkie Settings — Client-side logic

let config = {};
let models = { stt: {}, llm: {} };

// Must match DEFAULT_CONFIG["system_prompt"] in config_manager.py
const DEFAULT_SYSTEM_PROMPT =
    'You are an expert transcriber. Transcribe the following audio based on the ' +
    'provided <previous_context>. If the context ends mid-sentence, continue it ' +
    'logically with appropriate capitalization and spacing. If context ends with a ' +
    'period, start the next sentence with an uppercase letter. Remove filler words, ' +
    'self-corrections, and apply custom vocabulary spellings. Expand the following ' +
    'snippets: {snippets}. Output ONLY the final processed text.';

// ---- Navigation ----

document.querySelectorAll('.nav-item').forEach(item => {
    item.addEventListener('click', () => {
        document.querySelectorAll('.nav-item').forEach(i => i.classList.remove('active'));
        document.querySelectorAll('.section').forEach(s => s.classList.remove('active'));
        item.classList.add('active');
        const section = document.getElementById(item.dataset.section);
        if (section) section.classList.add('active');
    });
});

// ---- API Helpers ----

async function api(method, path, body = null) {
    const opts = { method, headers: { 'Content-Type': 'application/json' } };
    if (body) opts.body = JSON.stringify(body);
    const res = await fetch(path, opts);
    return res.json();
}

// ---- Load Config ----

async function loadConfig() {
    config = await api('GET', '/api/config');
    models = await api('GET', '/api/models');
    populateUI();
}

function populateUI() {
    // Providers
    setVal('stt-provider', config.stt_provider || 'openai');
    setVal('llm-provider', config.api_provider || 'openai');
    updateModelDropdowns();

    // Quick Start providers (synced)
    setVal('qs-stt-provider', config.stt_provider || 'openai');
    setVal('qs-llm-provider', config.api_provider || 'openai');

    // Hotkey
    document.getElementById('hotkey-display').value = config.hotkey || 'ctrl+win';
    document.getElementById('qs-hotkey').textContent = config.hotkey || 'Ctrl+Win';

    // Sliders
    const minHold = config.min_hold_seconds || 1.0;
    const silence = config.silence_rms_threshold || 0.005;
    document.getElementById('min-hold').value = minHold;
    document.getElementById('min-hold-value').textContent = minHold.toFixed(1) + 's';
    document.getElementById('silence-threshold').value = silence;
    document.getElementById('silence-value').textContent = silence.toFixed(3);

    // API key statuses
    loadKeyStatuses();

    // Snippets
    populateSnippets();

    // Vocabulary
    const vocab = config.custom_vocabulary || [];
    document.getElementById('vocab-text').value = vocab.join(', ');

    // System Prompt
    document.getElementById('system-prompt-text').value = config.system_prompt || DEFAULT_SYSTEM_PROMPT;
    const temp = config.temperature !== undefined ? config.temperature : 0;
    document.getElementById('temperature').value = temp;
    document.getElementById('temperature-value').textContent = parseFloat(temp).toFixed(1);

    // Quick Start badges
    updateQuickStartBadges();

    // About
    api('GET', '/api/about').then(data => {
        document.getElementById('about-version').textContent = data.version;
    });

    // If missing keys, show Quick Start
    if (config._missing_keys && config._missing_keys.length > 0) {
        showSection('quickstart');
    }
}

function setVal(id, value) {
    const el = document.getElementById(id);
    if (el) el.value = value;
}

// ---- Model Dropdowns ----

function updateModelDropdowns() {
    const sttProv = document.getElementById('stt-provider').value;
    const llmProv = document.getElementById('llm-provider').value;

    fillSelect('stt-model', models.stt[sttProv] || [], getModel('stt', sttProv));
    fillSelect('llm-model', models.llm[llmProv] || [], getModel('llm', llmProv));
}

function getModel(type, provider) {
    const key = `${provider}_${type}`;
    return (config.models || {})[key] || '';
}

function fillSelect(id, options, selected) {
    const el = document.getElementById(id);
    el.innerHTML = '';
    options.forEach(opt => {
        const o = document.createElement('option');
        o.value = opt;
        o.textContent = opt;
        if (opt === selected) o.selected = true;
        el.appendChild(o);
    });
}

document.getElementById('stt-provider').addEventListener('change', updateModelDropdowns);
document.getElementById('llm-provider').addEventListener('change', updateModelDropdowns);

// Sync QS providers with main providers
document.getElementById('qs-stt-provider').addEventListener('change', e => {
    document.getElementById('stt-provider').value = e.target.value;
    updateModelDropdowns();
});
document.getElementById('qs-llm-provider').addEventListener('change', e => {
    document.getElementById('llm-provider').value = e.target.value;
    updateModelDropdowns();
});

// ---- Save Providers ----

document.getElementById('save-providers').addEventListener('click', async () => {
    const sttProv = document.getElementById('stt-provider').value;
    const llmProv = document.getElementById('llm-provider').value;
    const sttModel = document.getElementById('stt-model').value;
    const llmModel = document.getElementById('llm-model').value;

    await api('POST', '/api/config', {
        stt_provider: sttProv,
        api_provider: llmProv,
        models: {
            [`${sttProv}_stt`]: sttModel,
            [`${llmProv}_llm`]: llmModel,
        },
    });
    config.stt_provider = sttProv;
    config.api_provider = llmProv;
    updateQuickStartBadges();
});

// ---- API Keys ----

async function loadKeyStatuses() {
    for (const provider of ['openai', 'groq', 'anthropic']) {
        const data = await api('GET', `/api/keys/${provider}`);
        const statusEl = document.getElementById(`${provider}-key-status`);
        if (data.exists) {
            statusEl.textContent = data.masked;
            statusEl.className = 'key-status ok';
        } else {
            statusEl.textContent = 'not set';
            statusEl.className = 'key-status';
        }
    }
}

async function saveKey(provider) {
    const input = document.getElementById(`${provider}-key`);
    const key = input.value.trim();
    if (!key) return;

    const result = await api('POST', `/api/keys/${provider}`, { key });
    const statusEl = document.getElementById(`${provider}-key-status`);

    if (result.status === 'ok') {
        statusEl.textContent = result.masked;
        statusEl.className = 'key-status ok';
        input.value = '';
        updateQuickStartBadges();
    } else {
        statusEl.textContent = result.message;
        statusEl.className = 'key-status error';
    }
}

async function testKey(provider) {
    const statusEl = document.getElementById(`${provider}-key-status`);
    statusEl.textContent = 'testing...';
    statusEl.className = 'key-status testing';

    const input = document.getElementById(`${provider}-key`);
    const key = input.value.trim() || undefined;

    const result = await api('POST', '/api/test-connection', { provider, key });
    if (result.status === 'ok') {
        statusEl.textContent = 'connected';
        statusEl.className = 'key-status ok';
    } else {
        statusEl.textContent = result.message;
        statusEl.className = 'key-status error';
    }
}

// Make functions available globally for onclick handlers
window.saveKey = saveKey;
window.testKey = testKey;

// ---- Hotkey ----

let hotkeyPollTimer = null;

document.getElementById('record-hotkey-btn').addEventListener('click', async () => {
    const btn = document.getElementById('record-hotkey-btn');
    btn.disabled = true;
    btn.textContent = 'Press keys...';

    await api('POST', '/api/record-hotkey');

    // Poll for result
    hotkeyPollTimer = setInterval(async () => {
        const result = await api('GET', '/api/record-hotkey');
        if (!result.recording) {
            clearInterval(hotkeyPollTimer);
            btn.disabled = false;
            btn.textContent = 'Record';
            if (result.result) {
                document.getElementById('hotkey-display').value = result.result;
            }
        }
    }, 200);
});

document.getElementById('save-hotkey').addEventListener('click', async () => {
    await api('POST', '/api/config', {
        hotkey: document.getElementById('hotkey-display').value,
        min_hold_seconds: parseFloat(document.getElementById('min-hold').value),
        silence_rms_threshold: parseFloat(document.getElementById('silence-threshold').value),
    });
});

// Slider value display
document.getElementById('min-hold').addEventListener('input', e => {
    document.getElementById('min-hold-value').textContent = parseFloat(e.target.value).toFixed(1) + 's';
});
document.getElementById('silence-threshold').addEventListener('input', e => {
    document.getElementById('silence-value').textContent = parseFloat(e.target.value).toFixed(3);
});

// ---- Snippets ----

function populateSnippets() {
    const container = document.getElementById('snippets-list');
    container.innerHTML = '';
    const snippets = config.snippets || {};
    for (const [trigger, expansion] of Object.entries(snippets)) {
        addSnippetRow(trigger, expansion);
    }
}

function addSnippetRow(trigger = '', expansion = '') {
    const container = document.getElementById('snippets-list');
    const row = document.createElement('div');
    row.className = 'snippet-row';
    row.innerHTML = `
        <input type="text" class="trigger" placeholder="trigger" value="${escHtml(trigger)}">
        <input type="text" class="expansion" placeholder="expansion text" value="${escHtml(expansion)}">
        <button class="btn btn-sm btn-danger" onclick="this.parentElement.remove()">X</button>
    `;
    container.appendChild(row);
}

document.getElementById('add-snippet').addEventListener('click', () => addSnippetRow());

document.getElementById('save-snippets').addEventListener('click', async () => {
    const rows = document.querySelectorAll('#snippets-list .snippet-row');
    const snippets = {};
    const statusEl = document.getElementById('snippets-status');
    const seen = new Set();

    for (const row of rows) {
        const trigger = row.querySelector('.trigger').value.trim();
        const expansion = row.querySelector('.expansion').value.trim();
        if (!trigger && !expansion) continue;
        if (!trigger) {
            statusEl.textContent = 'A snippet has an expansion but no trigger.';
            statusEl.className = 'save-status error';
            return;
        }
        if (seen.has(trigger)) {
            statusEl.textContent = `Duplicate trigger: '${trigger}'`;
            statusEl.className = 'save-status error';
            return;
        }
        seen.add(trigger);
        snippets[trigger] = expansion;
    }

    await api('POST', '/api/config', { snippets });
    statusEl.textContent = 'Saved';
    statusEl.className = 'save-status ok';
    setTimeout(() => { statusEl.textContent = ''; }, 2000);
});

// ---- Vocabulary ----

document.getElementById('save-vocab').addEventListener('click', async () => {
    const text = document.getElementById('vocab-text').value;
    const words = text.split(',').map(w => w.trim()).filter(w => w);
    await api('POST', '/api/config', { custom_vocabulary: words });
});

// ---- System Prompt ----

document.getElementById('save-prompt').addEventListener('click', async () => {
    const text = document.getElementById('system-prompt-text').value;
    const statusEl = document.getElementById('prompt-status');

    if (!text.trim()) {
        statusEl.textContent = 'Prompt cannot be empty';
        statusEl.className = 'save-status error';
        return;
    }

    const temperature = parseFloat(document.getElementById('temperature').value);
    await api('POST', '/api/config', { system_prompt: text, temperature });
    statusEl.textContent = 'Saved';
    statusEl.className = 'save-status ok';
    setTimeout(() => { statusEl.textContent = ''; }, 2000);
});

document.getElementById('reset-prompt').addEventListener('click', () => {
    document.getElementById('system-prompt-text').value = DEFAULT_SYSTEM_PROMPT;
    const statusEl = document.getElementById('prompt-status');
    statusEl.textContent = 'Reset — click Save to apply';
    statusEl.className = 'save-status';
    setTimeout(() => { statusEl.textContent = ''; }, 3000);
});

document.getElementById('temperature').addEventListener('input', e => {
    document.getElementById('temperature-value').textContent = parseFloat(e.target.value).toFixed(1);
});

// ---- Quick Start Badges ----

async function updateQuickStartBadges() {
    // Step 1: Providers — always done (they have defaults)
    setBadge('providers', true);

    // Step 2: Keys — check if required keys exist
    const sttProv = document.getElementById('stt-provider').value || config.stt_provider || 'openai';
    const llmProv = document.getElementById('llm-provider').value || config.api_provider || 'openai';

    const providers = new Set([sttProv, llmProv]);
    let allKeysSet = true;

    for (const p of providers) {
        const data = await api('GET', `/api/keys/${p}`);
        if (!data.exists) {
            allKeysSet = false;
            break;
        }
    }
    setBadge('keys', allKeysSet);

    // Step 3: Try it — can't auto-detect, stays unchecked unless keys are set
    setBadge('tryit', false);
}

function setBadge(step, done) {
    const badge = document.getElementById(`badge-${step}`);
    if (done) {
        badge.classList.add('done');
        badge.innerHTML = '&#10003;';
    } else {
        badge.classList.remove('done');
        // Restore the step number
        const nums = { providers: '1', keys: '2', tryit: '3' };
        badge.textContent = nums[step] || '';
    }
}

function showSection(sectionId) {
    document.querySelectorAll('.nav-item').forEach(i => {
        i.classList.toggle('active', i.dataset.section === sectionId);
    });
    document.querySelectorAll('.section').forEach(s => {
        s.classList.toggle('active', s.id === sectionId);
    });
}

// ---- Utilities ----

function escHtml(str) {
    const div = document.createElement('div');
    div.textContent = str;
    return div.innerHTML.replace(/"/g, '&quot;');
}

// ---- Init ----

loadConfig();
