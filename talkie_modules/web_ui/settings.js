// Talkie Settings — Client-side logic

let config = {};
let models = { stt: {}, llm: {} };
let defaultSystemPrompt = '';  // Fetched from backend during loadConfig()
let hotkeyPollTimer = null;

// ---- Poll Timer Management ----

function clearAllPollTimers() {
    if (hotkeyPollTimer) { clearInterval(hotkeyPollTimer); hotkeyPollTimer = null; }
    if (updatePollTimer) { clearInterval(updatePollTimer); updatePollTimer = null; }
}

// ---- Navigation ----

document.querySelectorAll('.nav-item').forEach(item => {
    item.addEventListener('click', () => {
        clearAllPollTimers();
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
    try {
        const res = await fetch(path, opts);
        if (!res.ok) {
            const text = await res.text();
            throw new Error(`${res.status}: ${text}`);
        }
        return res.json();
    } catch (err) {
        console.error(`API ${method} ${path} failed:`, err);
        return { status: 'error', message: err.message };
    }
}

// ---- Load Config ----

async function loadConfig() {
    config = await api('GET', '/api/config');
    if (config.status === 'error') {
        const content = document.querySelector('.content');
        const section = document.createElement('section');
        section.className = 'section active';
        const h2 = document.createElement('h2');
        h2.textContent = 'Error';
        const p = document.createElement('p');
        p.textContent = 'Failed to load configuration: ' + (config.message || 'unknown error');
        section.appendChild(h2);
        section.appendChild(p);
        content.replaceChildren(section);
        return;
    }
    // Config response bundles models, providers, key statuses, and version
    // to avoid multiple sequential round trips on the single-threaded server.
    models = config._models || { stt: {}, llm: {} };
    _keyStatusCache = config._key_statuses || {};
    populateUI();
}

function populateUI() {
    // Store default system prompt from backend
    defaultSystemPrompt = config._default_system_prompt || '';

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

    // Build dynamic key groups from bundled provider data, then apply cached statuses
    buildKeyGroups();
    applyKeyStatuses();

    // Snippets
    populateSnippets();

    // Vocabulary
    const vocab = config.custom_vocabulary || [];
    document.getElementById('vocab-text').value = vocab.join(', ');

    // System Prompt
    document.getElementById('system-prompt-text').value = config.system_prompt || defaultSystemPrompt;
    const temp = config.temperature !== undefined ? config.temperature : 0;
    document.getElementById('temperature').value = temp;
    document.getElementById('temperature-value').textContent = parseFloat(temp).toFixed(1);

    // Profiles
    loadProfiles();

    // Quick Start badges
    updateQuickStartBadges();

    // About (version bundled in config response)
    document.getElementById('about-version').textContent = config._version || '-';

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

// Cache key status data to avoid double-fetching (loadKeyStatuses + updateQuickStartBadges)
let _keyStatusCache = {};

function applyKeyStatuses() {
    for (const [provider, data] of Object.entries(_keyStatusCache)) {
        const statusEl = document.getElementById(`${provider}-key-status`);
        if (!statusEl) continue;
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
        _keyStatusCache[provider] = { exists: true, masked: result.masked };
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

// ---- Dynamic Key Groups ----

function buildKeyGroups() {
    const container = document.getElementById('key-groups');
    if (!container) return;

    const providers = config._providers || [];
    if (!providers.length) return;

    for (const prov of providers) {
        const group = document.createElement('div');
        group.className = 'key-group';
        group.id = `key-${prov.id}`;

        const formRow = document.createElement('div');
        formRow.className = 'form-row';

        const label = document.createElement('label');
        label.textContent = prov.label + ': ';
        const link = document.createElement('a');
        link.href = prov.url;
        link.target = '_blank';
        link.className = 'key-link';
        link.textContent = 'Get key \u2192';
        label.appendChild(link);

        const input = document.createElement('input');
        input.type = 'password';
        input.id = `${prov.id}-key`;
        input.placeholder = prov.placeholder;
        input.autocomplete = 'off';

        const status = document.createElement('span');
        status.className = 'key-status';
        status.id = `${prov.id}-key-status`;

        formRow.appendChild(label);
        formRow.appendChild(input);
        formRow.appendChild(status);

        const actions = document.createElement('div');
        actions.className = 'key-actions';

        const testBtn = document.createElement('button');
        testBtn.className = 'btn btn-sm';
        testBtn.textContent = 'Test';
        testBtn.addEventListener('click', () => testKey(prov.id));

        const saveBtn = document.createElement('button');
        saveBtn.className = 'btn btn-sm btn-primary';
        saveBtn.textContent = 'Save';
        saveBtn.addEventListener('click', () => saveKey(prov.id));

        actions.appendChild(testBtn);
        actions.appendChild(saveBtn);

        group.appendChild(formRow);
        group.appendChild(actions);
        container.appendChild(group);
    }
}

// ---- Hotkey ----

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
    const result = await api('POST', '/api/config', {
        hotkey: document.getElementById('hotkey-display').value,
        min_hold_seconds: parseFloat(document.getElementById('min-hold').value),
        silence_rms_threshold: parseFloat(document.getElementById('silence-threshold').value),
    });
    const statusEl = document.getElementById('hotkey-status');
    if (statusEl) {
        statusEl.textContent = result.status === 'error' ? result.message : 'Saved';
        statusEl.className = 'save-status ' + (result.status === 'error' ? 'error' : 'ok');
        setTimeout(() => { statusEl.textContent = ''; }, 2000);
    }
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

function createSnippetRow(containerId, trigger = '', expansion = '') {
    const container = document.getElementById(containerId);
    const row = document.createElement('div');
    row.className = 'snippet-row';

    const triggerInput = document.createElement('input');
    triggerInput.type = 'text';
    triggerInput.className = 'trigger';
    triggerInput.placeholder = 'trigger';
    triggerInput.value = trigger;

    const expansionInput = document.createElement('input');
    expansionInput.type = 'text';
    expansionInput.className = 'expansion';
    expansionInput.placeholder = 'expansion text';
    expansionInput.value = expansion;

    const deleteBtn = document.createElement('button');
    deleteBtn.className = 'btn btn-sm btn-danger';
    deleteBtn.textContent = 'X';
    deleteBtn.addEventListener('click', () => row.remove());

    row.appendChild(triggerInput);
    row.appendChild(expansionInput);
    row.appendChild(deleteBtn);
    container.appendChild(row);
}

function addSnippetRow(trigger = '', expansion = '') {
    createSnippetRow('snippets-list', trigger, expansion);
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
    const result = await api('POST', '/api/config', { custom_vocabulary: words });
    const statusEl = document.getElementById('vocab-status');
    if (statusEl) {
        statusEl.textContent = result.status === 'error' ? result.message : 'Saved';
        statusEl.className = 'save-status ' + (result.status === 'error' ? 'error' : 'ok');
        setTimeout(() => { statusEl.textContent = ''; }, 2000);
    }
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
    document.getElementById('system-prompt-text').value = defaultSystemPrompt;
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

    // Step 2: Keys — use cache if available, otherwise fetch
    const sttProv = document.getElementById('stt-provider').value || config.stt_provider || 'openai';
    const llmProv = document.getElementById('llm-provider').value || config.api_provider || 'openai';

    const providers = new Set([sttProv, llmProv]);
    let allKeysSet = true;

    for (const p of providers) {
        let data = _keyStatusCache[p];
        if (!data) {
            data = await api('GET', `/api/keys/${p}`);
            _keyStatusCache[p] = data;
        }
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
    if (!badge) return;
    // Store the original number on first call
    if (!badge.dataset.num) {
        badge.dataset.num = badge.textContent.trim();
    }
    if (done) {
        badge.classList.add('done');
        badge.textContent = '\u2713';
    } else {
        badge.classList.remove('done');
        badge.textContent = badge.dataset.num;
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

// ---- Profiles ----

let profilesList = [];

async function loadProfiles(fromServer = false) {
    if (fromServer) {
        const data = await api('GET', '/api/profiles');
        profilesList = data.profiles || [];
    } else {
        profilesList = config.profiles || [];
    }
    renderProfilesList();
}

function renderProfilesList() {
    const container = document.getElementById('profiles-list');
    container.innerHTML = '';

    const emptyState = document.getElementById('profiles-empty-state');
    const hasProfiles = document.getElementById('profiles-has-profiles');

    if (profilesList.length === 0) {
        emptyState.style.display = 'block';
        hasProfiles.style.display = 'none';
        return;
    }

    emptyState.style.display = 'none';
    hasProfiles.style.display = 'block';

    profilesList.forEach((profile, idx) => {
        const card = document.createElement('div');
        card.className = 'profile-card';

        // Reorder buttons
        const reorder = document.createElement('div');
        reorder.className = 'profile-reorder-btns';
        const upBtn = document.createElement('button');
        upBtn.className = 'btn btn-sm';
        upBtn.textContent = '\u25B2';
        upBtn.disabled = idx === 0;
        upBtn.addEventListener('click', () => moveProfile(idx, -1));
        const downBtn = document.createElement('button');
        downBtn.className = 'btn btn-sm';
        downBtn.textContent = '\u25BC';
        downBtn.disabled = idx === profilesList.length - 1;
        downBtn.addEventListener('click', () => moveProfile(idx, 1));
        reorder.appendChild(upBtn);
        reorder.appendChild(downBtn);

        // Info
        const info = document.createElement('div');
        info.className = 'profile-card-info';
        const name = document.createElement('div');
        name.className = 'profile-card-name';
        name.textContent = profile.name;
        const match = document.createElement('div');
        match.className = 'profile-card-match';
        const parts = [];
        if (profile.match_process) parts.push('process: ' + profile.match_process);
        if (profile.match_title) parts.push('title: "' + profile.match_title + '"');
        match.textContent = parts.join(' + ') || 'no match rules';
        info.appendChild(name);
        info.appendChild(match);

        // Actions
        const actions = document.createElement('div');
        actions.className = 'profile-card-actions';
        const editBtn = document.createElement('button');
        editBtn.className = 'btn btn-sm';
        editBtn.textContent = 'Edit';
        editBtn.addEventListener('click', () => editProfile(profile));
        const deleteBtn = document.createElement('button');
        deleteBtn.className = 'btn btn-sm btn-danger';
        deleteBtn.textContent = 'Delete';
        deleteBtn.addEventListener('click', () => deleteProfile(profile.id));
        actions.appendChild(editBtn);
        actions.appendChild(deleteBtn);

        card.appendChild(reorder);
        card.appendChild(info);
        card.appendChild(actions);
        container.appendChild(card);
    });
}

async function moveProfile(idx, direction) {
    const newIdx = idx + direction;
    if (newIdx < 0 || newIdx >= profilesList.length) return;

    // Swap in local list
    [profilesList[idx], profilesList[newIdx]] = [profilesList[newIdx], profilesList[idx]];

    // Send new order to backend
    const order = profilesList.map(p => p.id);
    await api('POST', '/api/profiles/reorder', { order });
    renderProfilesList();
}

async function deleteProfile(id) {
    await api('DELETE', `/api/profiles/${id}`);
    profilesList = profilesList.filter(p => p.id !== id);
    renderProfilesList();
}

function editProfile(profile) {
    // Hide template view if open
    document.getElementById('profiles-template-view').style.display = 'none';
    document.getElementById('profiles-list-view').style.display = 'none';
    document.getElementById('profiles-edit-view').style.display = 'block';
    document.getElementById('profile-edit-title').textContent = profile ? 'Edit Profile' : 'New Profile';
    document.getElementById('profile-edit-id').value = profile ? profile.id : '';

    document.getElementById('profile-name').value = profile ? profile.name : '';
    document.getElementById('profile-match-process').value = profile ? (profile.match_process || '') : '';
    document.getElementById('profile-match-title').value = profile ? (profile.match_title || '') : '';

    // System prompt override
    const hasPrompt = profile && profile.system_prompt != null;
    document.getElementById('profile-override-prompt').checked = hasPrompt;
    const promptTextarea = document.getElementById('profile-system-prompt');
    promptTextarea.disabled = !hasPrompt;
    promptTextarea.value = hasPrompt ? profile.system_prompt : '';
    if (!hasPrompt) promptTextarea.placeholder = 'Inherited from global';

    // Snippets override
    const hasSnippets = profile && profile.snippets != null;
    document.getElementById('profile-override-snippets').checked = hasSnippets;
    const snippetsList = document.getElementById('profile-snippets-list');
    const addSnippetBtn = document.getElementById('profile-add-snippet');
    snippetsList.classList.toggle('override-disabled', !hasSnippets);
    addSnippetBtn.disabled = !hasSnippets;
    renderProfileSnippets(hasSnippets ? profile.snippets : {});

    // Vocabulary override
    const hasVocab = profile && profile.custom_vocabulary != null;
    document.getElementById('profile-override-vocab').checked = hasVocab;
    const vocabTextarea = document.getElementById('profile-vocabulary');
    vocabTextarea.disabled = !hasVocab;
    vocabTextarea.value = hasVocab ? (profile.custom_vocabulary || []).join(', ') : '';
    if (!hasVocab) vocabTextarea.placeholder = 'Inherited from global';

    // Temperature override
    const hasTemp = profile && profile.temperature != null;
    document.getElementById('profile-override-temp').checked = hasTemp;
    const tempSlider = document.getElementById('profile-temperature');
    tempSlider.disabled = !hasTemp;
    const tempVal = hasTemp ? profile.temperature : (config.temperature || 0);
    tempSlider.value = tempVal;
    document.getElementById('profile-temperature-value').textContent = parseFloat(tempVal).toFixed(1);

    document.getElementById('profile-status').textContent = '';

    // Show/hide reset button based on template_snapshot
    const resetBtn = document.getElementById('profile-reset-template');
    resetBtn.style.display = (profile && profile.template_snapshot) ? 'inline-block' : 'none';
    if (profile) resetBtn.dataset.profileId = profile.id;
}

function renderProfileSnippets(snippets) {
    const container = document.getElementById('profile-snippets-list');
    container.innerHTML = '';
    for (const [trigger, expansion] of Object.entries(snippets || {})) {
        addProfileSnippetRow(trigger, expansion);
    }
}

function addProfileSnippetRow(trigger = '', expansion = '') {
    createSnippetRow('profile-snippets-list', trigger, expansion);
}

// Override toggle handlers
document.getElementById('profile-override-prompt').addEventListener('change', e => {
    const textarea = document.getElementById('profile-system-prompt');
    textarea.disabled = !e.target.checked;
    if (e.target.checked && !textarea.value) {
        // Pre-populate with global system prompt
        textarea.value = config.system_prompt || defaultSystemPrompt;
    }
    if (!e.target.checked) {
        textarea.placeholder = 'Inherited from global';
    }
});

document.getElementById('profile-override-snippets').addEventListener('change', e => {
    const list = document.getElementById('profile-snippets-list');
    const btn = document.getElementById('profile-add-snippet');
    list.classList.toggle('override-disabled', !e.target.checked);
    btn.disabled = !e.target.checked;
    if (e.target.checked && list.children.length === 0) {
        addProfileSnippetRow();
    }
});

document.getElementById('profile-override-vocab').addEventListener('change', e => {
    const textarea = document.getElementById('profile-vocabulary');
    textarea.disabled = !e.target.checked;
    if (!e.target.checked) {
        textarea.placeholder = 'Inherited from global';
    }
});

document.getElementById('profile-override-temp').addEventListener('change', e => {
    document.getElementById('profile-temperature').disabled = !e.target.checked;
});

document.getElementById('profile-temperature').addEventListener('input', e => {
    document.getElementById('profile-temperature-value').textContent = parseFloat(e.target.value).toFixed(1);
});

document.getElementById('profile-add-snippet').addEventListener('click', () => addProfileSnippetRow());

document.getElementById('add-profile').addEventListener('click', () => editProfile(null));

document.getElementById('profile-cancel').addEventListener('click', () => {
    document.getElementById('profiles-edit-view').style.display = 'none';
    document.getElementById('profiles-list-view').style.display = 'block';
});

document.getElementById('profile-save').addEventListener('click', async () => {
    const statusEl = document.getElementById('profile-status');
    const id = document.getElementById('profile-edit-id').value;
    const name = document.getElementById('profile-name').value.trim();
    const matchProcess = document.getElementById('profile-match-process').value.trim();
    const matchTitle = document.getElementById('profile-match-title').value.trim();

    if (!name) {
        statusEl.textContent = 'Name is required';
        statusEl.className = 'save-status error';
        return;
    }
    if (!matchProcess && !matchTitle) {
        statusEl.textContent = 'At least one match field is required';
        statusEl.className = 'save-status error';
        return;
    }

    const payload = {
        name,
        match_process: matchProcess,
        match_title: matchTitle,
        system_prompt: document.getElementById('profile-override-prompt').checked
            ? document.getElementById('profile-system-prompt').value
            : null,
        snippets: null,
        custom_vocabulary: document.getElementById('profile-override-vocab').checked
            ? document.getElementById('profile-vocabulary').value.split(',').map(w => w.trim()).filter(w => w)
            : null,
        temperature: document.getElementById('profile-override-temp').checked
            ? parseFloat(document.getElementById('profile-temperature').value)
            : null,
    };

    // Collect snippets if override is enabled
    if (document.getElementById('profile-override-snippets').checked) {
        const rows = document.querySelectorAll('#profile-snippets-list .snippet-row');
        const snippets = {};
        for (const row of rows) {
            const t = row.querySelector('.trigger').value.trim();
            const e = row.querySelector('.expansion').value.trim();
            if (t) snippets[t] = e;
        }
        payload.snippets = snippets;
    }

    let result;
    if (id) {
        result = await api('PUT', `/api/profiles/${id}`, payload);
    } else {
        result = await api('POST', '/api/profiles', payload);
    }

    if (result.status === 'ok') {
        await loadProfiles(true);
        document.getElementById('profiles-edit-view').style.display = 'none';
        document.getElementById('profiles-list-view').style.display = 'block';
    } else {
        statusEl.textContent = result.message || 'Save failed';
        statusEl.className = 'save-status error';
    }
});

document.getElementById('profile-reset-template').addEventListener('click', async () => {
    if (!confirm('Reset this profile to its original template settings? Your customizations will be lost.')) return;
    const profileId = document.getElementById('profile-reset-template').dataset.profileId;
    const result = await api('POST', `/api/profiles/${profileId}/reset-template`);
    if (result.status === 'ok') {
        await loadProfiles(true);
        editProfile(result.profile);
        const statusEl = document.getElementById('profile-status');
        statusEl.textContent = 'Reset to template defaults';
        statusEl.className = 'save-status ok';
        setTimeout(() => { statusEl.textContent = ''; }, 3000);
    }
});

// ---- Profile Templates ----

let templatesList = [];

const templateIconMap = {
    envelope: '\u2709',
    chat: '\uD83D\uDCAC',
    code: '\uD83D\uDCBB',
    document: '\uD83D\uDCC4',
    notes: '\uD83D\uDCDD',
    browser: '\uD83C\uDF10',
};

async function loadTemplates() {
    const data = await api('GET', '/api/profile-templates');
    templatesList = data.templates || [];
}

async function showTemplateView() {
    if (templatesList.length === 0) await loadTemplates();
    document.getElementById('profiles-list-view').style.display = 'none';
    document.getElementById('profiles-edit-view').style.display = 'none';
    document.getElementById('profiles-template-view').style.display = 'block';
    document.getElementById('template-app-picker').style.display = 'none';
    document.getElementById('template-cards').style.display = 'block';
    document.getElementById('template-cards-actions').style.display = 'block';
    renderTemplateCards();
}

function hideTemplateView() {
    document.getElementById('profiles-template-view').style.display = 'none';
    document.getElementById('profiles-list-view').style.display = 'block';
}

function renderTemplateCards() {
    const container = document.getElementById('template-cards');
    container.innerHTML = '';

    for (const t of templatesList) {
        const card = document.createElement('div');
        card.className = 'template-card';

        const icon = document.createElement('div');
        icon.className = 'template-card-icon';
        icon.textContent = templateIconMap[t.icon] || '\u2699';

        const info = document.createElement('div');
        info.className = 'template-card-info';
        const name = document.createElement('div');
        name.className = 'template-card-name';
        name.textContent = t.name;
        const desc = document.createElement('div');
        desc.className = 'template-card-desc';
        desc.textContent = t.description;
        info.appendChild(name);
        info.appendChild(desc);

        const count = document.createElement('div');
        count.className = 'template-card-count';
        count.textContent = t.apps.length + ' apps';

        card.appendChild(icon);
        card.appendChild(info);
        card.appendChild(count);

        card.addEventListener('click', () => showTemplatePicker(t));
        container.appendChild(card);
    }
}

function showTemplatePicker(template) {
    document.getElementById('template-cards').style.display = 'none';
    document.getElementById('template-cards-actions').style.display = 'none';
    document.getElementById('template-app-picker').style.display = 'block';
    document.getElementById('template-picker-title').textContent = template.name;
    document.getElementById('template-picker-desc').textContent = template.description;
    document.getElementById('template-status').textContent = '';

    const container = document.getElementById('template-app-list');
    container.innerHTML = '';
    container.dataset.templateId = template.id;

    // Build existing keys for duplicate detection
    const existingKeys = new Set();
    for (const p of profilesList) {
        const mp = (p.match_process || '').trim().toLowerCase();
        const mt = (p.match_title || '').trim().toLowerCase();
        existingKeys.add(mp + '|' + mt);
    }

    for (const app of template.apps) {
        const item = document.createElement('div');
        item.className = 'template-app-item';

        const label = document.createElement('label');
        const checkbox = document.createElement('input');
        checkbox.type = 'checkbox';
        checkbox.value = app.id;
        checkbox.dataset.appId = app.id;

        // Duplicate detection using match_process + match_title
        const appMp = (app.match_process || '').trim().toLowerCase();
        const appMt = (app.match_title || '').trim().toLowerCase();
        const alreadyExists = existingKeys.has(appMp + '|' + appMt);

        if (alreadyExists) {
            checkbox.disabled = true;
            const configured = document.createElement('span');
            configured.className = 'configured';
            configured.textContent = '(already configured)';
            label.appendChild(checkbox);
            label.appendChild(document.createTextNode(' ' + app.name + ' '));
            label.appendChild(configured);
        } else {
            label.appendChild(checkbox);
            label.appendChild(document.createTextNode(' ' + app.name));
        }

        item.appendChild(label);
        container.appendChild(item);
    }
}

document.getElementById('template-apply').addEventListener('click', async () => {
    const container = document.getElementById('template-app-list');
    const templateId = container.dataset.templateId;
    const statusEl = document.getElementById('template-status');

    const checkboxes = container.querySelectorAll('input[type="checkbox"]:checked');
    const appIds = Array.from(checkboxes).map(cb => cb.dataset.appId);

    if (appIds.length === 0) {
        statusEl.textContent = 'Select at least one app';
        statusEl.className = 'save-status error';
        return;
    }

    const result = await api('POST', `/api/profile-templates/${templateId}/apply`, { app_ids: appIds });

    if (result.status === 'ok') {
        const created = result.created ? result.created.length : 0;
        const skipped = result.skipped ? result.skipped.length : 0;
        let msg = `${created} profile${created !== 1 ? 's' : ''} added`;
        if (skipped > 0) {
            msg += `, ${skipped} skipped (already exist)`;
        }
        statusEl.textContent = msg;
        statusEl.className = 'save-status ok';

        await loadProfiles(true);
        setTimeout(() => {
            hideTemplateView();
        }, 1500);
    } else {
        statusEl.textContent = result.message || 'Failed to apply template';
        statusEl.className = 'save-status error';
    }
});

document.getElementById('template-back-to-cards').addEventListener('click', () => {
    document.getElementById('template-app-picker').style.display = 'none';
    document.getElementById('template-cards').style.display = 'block';
    document.getElementById('template-cards-actions').style.display = 'block';
});

document.getElementById('template-cancel').addEventListener('click', hideTemplateView);

document.getElementById('empty-state-templates').addEventListener('click', () => showTemplateView());
document.getElementById('empty-state-manual').addEventListener('click', (e) => {
    e.preventDefault();
    editProfile(null);
});
document.getElementById('add-from-template').addEventListener('click', () => showTemplateView());

// ---- Updates ----

let _updateInfo = null;  // Cached check result
let updatePollTimer = null;

document.getElementById('check-update-btn').addEventListener('click', async () => {
    const btn = document.getElementById('check-update-btn');
    const statusDiv = document.getElementById('update-status');
    const msgEl = document.getElementById('update-message');
    const notesEl = document.getElementById('update-notes');
    const downloadBtn = document.getElementById('download-update-btn');
    const progressDiv = document.getElementById('update-progress');

    btn.disabled = true;
    btn.textContent = 'Checking...';
    statusDiv.style.display = 'block';
    msgEl.textContent = '';
    notesEl.style.display = 'none';
    downloadBtn.style.display = 'none';
    progressDiv.style.display = 'none';

    const result = await api('GET', '/api/update/check');

    btn.disabled = false;
    btn.textContent = 'Check for Updates';

    if (result.error) {
        msgEl.textContent = result.error;
        msgEl.style.color = 'var(--error)';
        return;
    }

    if (!result.available) {
        msgEl.textContent = `You're on the latest version (v${result.current_version || result.latest_version || ''}).`;
        msgEl.style.color = 'var(--success)';
        return;
    }

    _updateInfo = result;
    msgEl.textContent = `Update available: v${result.latest_version}`;
    msgEl.style.color = 'var(--accent)';

    if (result.release_notes) {
        notesEl.textContent = result.release_notes;
        notesEl.style.display = 'block';
    }

    downloadBtn.textContent = `Download v${result.latest_version}`;
    downloadBtn.style.display = 'inline-block';
});

document.getElementById('download-update-btn').addEventListener('click', async () => {
    const btn = document.getElementById('download-update-btn');
    const progressDiv = document.getElementById('update-progress');
    const fillEl = document.getElementById('update-progress-fill');
    const textEl = document.getElementById('update-progress-text');

    if (btn.dataset.action === 'apply') {
        btn.disabled = true;
        btn.textContent = 'Restarting...';
        await api('POST', '/api/update/apply');
        return;
    }

    if (!_updateInfo) return;

    btn.disabled = true;
    btn.textContent = 'Downloading...';
    progressDiv.style.display = 'block';
    fillEl.style.width = '0%';
    textEl.textContent = '0%';

    await api('POST', '/api/update/download', {
        url: _updateInfo.download_url,
        expected_size: _updateInfo.download_size || 0,
    });

    // Poll for progress
    updatePollTimer = setInterval(async () => {
        const state = await api('GET', '/api/update/download');

        if (state.error) {
            clearInterval(updatePollTimer);
            updatePollTimer = null;
            btn.disabled = false;
            btn.textContent = `Download v${_updateInfo.latest_version}`;
            fillEl.style.width = '0%';
            textEl.textContent = state.error;
            textEl.style.color = 'var(--error)';
            return;
        }

        const pct = Math.round(state.progress || 0);
        fillEl.style.width = pct + '%';
        textEl.textContent = pct + '%';
        textEl.style.color = '';

        if (state.ready) {
            clearInterval(updatePollTimer);
            updatePollTimer = null;
            fillEl.style.width = '100%';
            textEl.textContent = '100%';
            btn.disabled = false;
            btn.textContent = 'Install & Restart';
            btn.dataset.action = 'apply';
        }
    }, 500);
});

// ---- Cleanup ----

window.addEventListener('beforeunload', clearAllPollTimers);

// ---- Init ----

loadConfig();
