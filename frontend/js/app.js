/**
 * Shorts Clipper — Frontend SPA
 * Управляет навигацией, загрузкой, созданием клипов и публикацией.
 */
(function () {
    'use strict';

    const API = '/api';
    const CANVAS_W = 1080;
    const CANVAS_H = 1920;

    let state = {
        projects: [],
        activeProjectId: null,
        activeVideoSource: null,
        clips: [],
        bannerPosition: 'bottom',
        selectedClips: new Set(),
        selectedSegments: new Set(),
        activeTaskId: null,
        pollTimer: null,
        previewClipId: null,
        transcriptionSegments: [],
        overlaySettings: {
            subtitles_enabled: true,
            subtitle_font: 'Arial',
            subtitle_font_size: 52,
            subtitle_color: '#ffffff',
            subtitle_stroke_color: '#000000',
            subtitle_stroke_width: 3,
            subtitle_x: null,
            subtitle_y: null,
            banner_position: 'bottom',
            banner_x: null,
            banner_y: null,
            banner_scale: 0.9,
            banner_opacity: 0.85,
        },
    };

    let saveOverlayTimer = null;

    // ── ДОМ-элементы ──
    const $ = (sel) => document.querySelector(sel);
    const $$ = (sel) => document.querySelectorAll(sel);

    // ── ИНИЦИАЛИЗАЦИЯ ──
    async function init() {
        bindNavigation();
        bindDashboard();
        bindWorkspace();
        bindPreview();
        bindPublishing();
        bindSettings();
        bindModal();
        await loadProjects();
    }

    // ════════════════════════════════════════
    // НАВИГАЦИЯ
    // ════════════════════════════════════════

    function bindNavigation() {
        $$('.nav-btn').forEach(btn => {
            btn.addEventListener('click', () => switchTab(btn.dataset.tab));
        });
    }

    function switchTab(tabName) {
        $$('.nav-btn').forEach(b => b.classList.remove('active', 'bg-brand-600', 'text-white'));
        const btn = $(`.nav-btn[data-tab="${tabName}"]`);
        if (btn) btn.classList.add('active', 'bg-brand-600', 'text-white');

        $$('.tab-content').forEach(t => t.classList.add('hidden'));
        const tab = $(`#tab-${tabName}`);
        if (tab) tab.classList.remove('hidden');

        if (tabName === 'workspace') loadClips();
        if (tabName === 'publishing') loadPublishQueue();
    }

    // ════════════════════════════════════════
    // DASHBOARD: Проекты + Загрузка
    // ════════════════════════════════════════

    async function loadProjects() {
        const list = $('#projects-list');
        try {
            const resp = await fetch(`${API}/projects/`);
            state.projects = await resp.json();
            if (state.projects.length === 0) {
                list.innerHTML = '<p class="text-gray-500 text-sm">Нет проектов. Создайте новый.</p>';
            } else {
                list.innerHTML = state.projects.map(p => renderProjectCard(p)).join('');
                list.querySelectorAll('.project-card').forEach(card => {
                    card.addEventListener('click', () => selectProject(card.dataset.id));
                });
            }
        } catch (e) {
            list.innerHTML = `<p class="text-red-400 text-sm">Ошибка загрузки: ${e.message}</p>`;
        }
    }

    function renderProjectCard(p) {
        const vs = p.video_source;
        const hasVideo = vs && vs.filename;
        return `
        <div class="project-card bg-gray-900 border border-gray-800 rounded-xl p-4 cursor-pointer hover:border-brand-500 transition ${p.id === state.activeProjectId ? 'border-brand-500 ring-1 ring-brand-500/30' : ''}"
             data-id="${p.id}">
            <div class="flex items-center justify-between">
                <div>
                    <h3 class="font-medium">${escHtml(p.title)}</h3>
                    <p class="text-xs text-gray-500 mt-1">
                        ${hasVideo ? `🎬 ${vs.filename}` : '📭 Видео не загружено'}
                        ${vs && vs.has_transcription ? ' · ✅ Распознано' : ''}
                    </p>
                </div>
                <div class="text-right">
                    <span class="text-xs text-gray-500">${p.clips_count} клипов</span>
                    <button class="del-proj-btn ml-2 text-red-400 hover:text-red-300 text-xs opacity-0 group-hover:opacity-100" data-id="${p.id}" title="Удалить">✕</button>
                </div>
            </div>
        </div>`;
    }

    async function selectProject(id) {
        state.activeProjectId = id;
        state.selectedClips.clear();
        state.selectedSegments.clear();

        // Подсветка карточки
        $$('.project-card').forEach(c => {
            c.classList.toggle('border-brand-500', c.dataset.id === id);
            c.classList.toggle('ring-1', c.dataset.id === id);
            c.classList.toggle('ring-brand-500/30', c.dataset.id === id);
        });

        // Загружаем детали
        try {
            const resp = await fetch(`${API}/projects/${id}`);
            const proj = await resp.json();
            state.activeVideoSource = proj.video_source || null;
            if (state.activeVideoSource) {
                loadOverlaySettingsFromVideoSource(state.activeVideoSource);
            }
            showUploadPanel(proj);
        } catch (e) {
            console.error(e);
        }

        await loadProjects(); // обновляем клипы-каунт
    }

    function showUploadPanel(proj) {
        const panel = $('#upload-panel');
        panel.classList.remove('hidden');

        const vs = proj.video_source;
        if (vs && vs.filename) {
            $('#video-info').classList.remove('hidden');
            $('#video-info').innerHTML = `✅ <b>${escHtml(vs.filename)}</b> · ${fmtDuration(vs.duration)} · ${vs.width}×${vs.height}`;
            $('#banner-dropzone').classList.remove('hidden');
            $('#banner-pos-panel').classList.remove('hidden');
            $('#clip-mode-panel').classList.remove('hidden');
            $('#btn-analyze').classList.remove('hidden');
            applyClipSettingsToUI(vs);

            if (vs.banner_path) {
                $('#banner-info').classList.remove('hidden');
                $('#banner-info').innerHTML = `🖼️ Баннер загружен`;
            }
        } else {
            $('#video-info').classList.add('hidden');
            $('#banner-dropzone').classList.add('hidden');
            $('#banner-pos-panel').classList.add('hidden');
            $('#clip-mode-panel').classList.add('hidden');
            $('#btn-analyze').classList.add('hidden');
        }
    }

    function getSelectedClipMode() {
        const checked = document.querySelector('input[name="clip-mode"]:checked');
        return checked ? checked.value : 'heuristic';
    }

    function applyClipSettingsToUI(vs) {
        const mode = vs?.clip_selection_mode || 'heuristic';
        const buffer = vs?.clip_buffer_seconds ?? 2;

        $$('input[name="clip-mode"]').forEach(r => {
            r.checked = r.value === mode;
        });

        const bufferInput = $('#clip-buffer');
        const bufferVal = $('#clip-buffer-val');
        if (bufferInput) bufferInput.value = buffer;
        if (bufferVal) bufferVal.textContent = buffer;

        updateClipModeUI();
        updateAnalyzeButtonLabel();
    }

    function updateClipModeUI() {
        const mode = getSelectedClipMode();
        const bufferPanel = $('#ai-buffer-panel');
        if (bufferPanel) {
            bufferPanel.classList.toggle('hidden', mode !== 'ai');
        }
        updateAnalyzeButtonLabel();
    }

    function updateAnalyzeButtonLabel() {
        const btn = $('#btn-analyze');
        if (!btn || btn.disabled) return;
        const labels = {
            manual: '🔍 Распознать речь (без нарезки)',
            heuristic: '🔍 Анализ + авто-нарезка',
            ai: '🤖 Анализ + ИИ-нарезка',
        };
        btn.textContent = labels[getSelectedClipMode()] || labels.heuristic;
    }

    let saveClipSettingsTimer = null;

    async function saveClipSettings() {
        if (!state.activeProjectId) return;
        const mode = getSelectedClipMode();
        const buffer = parseFloat($('#clip-buffer')?.value || '2');
        try {
            const resp = await fetch(`${API}/projects/${state.activeProjectId}/clip-settings`, {
                method: 'PATCH',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    clip_selection_mode: mode,
                    clip_buffer_seconds: buffer,
                }),
            });
            if (resp.ok) {
                state.activeVideoSource = await resp.json();
            }
        } catch (e) {
            console.error('Ошибка сохранения настроек нарезки:', e);
        }
    }

    function debouncedSaveClipSettings() {
        if (saveClipSettingsTimer) clearTimeout(saveClipSettingsTimer);
        saveClipSettingsTimer = setTimeout(saveClipSettings, 300);
    }

    function bindDashboard() {
        $('#btn-new-project').addEventListener('click', async () => {
            const title = prompt('Название проекта:', 'Новый проект');
            if (!title) return;
            try {
                await fetch(`${API}/projects/`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ title }),
                });
                await loadProjects();
            } catch (e) {
                alert('Ошибка: ' + e.message);
            }
        });

        // Drag & Drop / Click для видео
        const videoDrop = $('#video-dropzone');
        const videoInput = $('#video-input');

        videoDrop.addEventListener('click', () => videoInput.click());
        videoDrop.addEventListener('dragover', e => { e.preventDefault(); videoDrop.classList.add('border-brand-500'); });
        videoDrop.addEventListener('dragleave', () => videoDrop.classList.remove('border-brand-500'));
        videoDrop.addEventListener('drop', e => {
            e.preventDefault();
            videoDrop.classList.remove('border-brand-500');
            const file = e.dataTransfer.files[0];
            if (file) uploadVideo(file);
        });
        videoInput.addEventListener('change', () => {
            if (videoInput.files[0]) uploadVideo(videoInput.files[0]);
        });

        // Баннер
        const bannerDrop = $('#banner-dropzone');
        const bannerInput = $('#banner-input');
        bannerDrop.addEventListener('click', () => bannerInput.click());
        bannerDrop.addEventListener('dragover', e => { e.preventDefault(); });
        bannerDrop.addEventListener('drop', e => {
            e.preventDefault();
            const file = e.dataTransfer.files[0];
            if (file) uploadBanner(file);
        });
        bannerInput.addEventListener('change', () => {
            if (bannerInput.files[0]) uploadBanner(bannerInput.files[0]);
        });

        // Позиция баннера
        $$('.pos-btn').forEach(btn => {
            btn.addEventListener('click', async () => {
                const pos = btn.dataset.pos;
                state.bannerPosition = pos;
                $$('.pos-btn').forEach(b => {
                    b.classList.remove('bg-brand-600/20', 'border-brand-600', 'text-brand-300');
                    b.classList.add('border-gray-700', 'text-gray-400');
                });
                btn.classList.add('bg-brand-600/20', 'border-brand-600', 'text-brand-300');
                btn.classList.remove('border-gray-700', 'text-gray-400');

                if (state.activeProjectId) {
                    await saveOverlaySettings({ banner: { position: pos } });
                }
            });
        });

        // Режим нарезки клипов
        $$('input[name="clip-mode"]').forEach(radio => {
            radio.addEventListener('change', () => {
                updateClipModeUI();
                debouncedSaveClipSettings();
            });
        });

        const clipBuffer = $('#clip-buffer');
        if (clipBuffer) {
            clipBuffer.addEventListener('input', () => {
                const val = $('#clip-buffer-val');
                if (val) val.textContent = clipBuffer.value;
                debouncedSaveClipSettings();
            });
        }

        // Кнопка анализа
        $('#btn-analyze').addEventListener('click', async () => {
            if (!state.activeProjectId) return;
            await saveClipSettings();

            const mode = getSelectedClipMode();
            if (mode === 'ai') {
                const ollamaResp = await fetch(`${API}/ollama-status`);
                const ollama = await ollamaResp.json();
                if (!ollama.running) {
                    alert('Для ИИ-нарезки нужен Ollama.\n\nУстановите: https://ollama.com/download\nЗапустите: ollama serve\nЗатем: ollama pull qwen2.5:7b');
                    return;
                }
            }

            const btn = $('#btn-analyze');
            btn.disabled = true;
            btn.textContent = '⏳ Запускаю...';
            try {
                const resp = await fetch(`${API}/projects/${state.activeProjectId}/transcribe`, { method: 'POST' });
                if (!resp.ok) {
                    const err = await resp.json();
                    throw new Error(err.detail || 'Ошибка');
                }
                const data = await resp.json();
                showProgress('transcribe', mode);
                startTaskPolling(data.task_id, (result) => {
                    if (result?.ai_error) {
                        console.warn('ИИ-нарезка:', result.ai_error);
                    }
                    loadProjects();
                    switchTab('workspace');
                    loadClips();
                });
            } catch (e) {
                alert('Ошибка анализа: ' + e.message);
                btn.disabled = false;
                updateAnalyzeButtonLabel();
            }
        });
    }

    async function uploadVideo(file) {
        if (!state.activeProjectId) { alert('Сначала выберите проект'); return; }
        const progress = $('#video-progress');
        progress.classList.remove('hidden');
        progress.value = 0;

        const formData = new FormData();
        formData.append('file', file);

        try {
            const resp = await fetch(`${API}/projects/${state.activeProjectId}/upload-video`, {
                method: 'POST',
                body: formData,
            });
            if (!resp.ok) {
                const err = await resp.json();
                throw new Error(err.detail || 'Ошибка загрузки');
            }
            const vs = await resp.json();
            state.activeVideoSource = vs;
            if (vs) loadOverlaySettingsFromVideoSource(vs);
            await loadProjects();
            selectProject(state.activeProjectId);
        } catch (e) {
            alert('Ошибка: ' + e.message);
        } finally {
            progress.classList.add('hidden');
        }
    }

    async function uploadBanner(file) {
        if (!state.activeProjectId) return;
        const formData = new FormData();
        formData.append('file', file);
        try {
            const resp = await fetch(`${API}/projects/${state.activeProjectId}/upload-banner`, {
                method: 'POST',
                body: formData,
            });
            if (!resp.ok) throw new Error((await resp.json()).detail || 'Ошибка');
            const vs = await resp.json();
            state.activeVideoSource = vs;
            loadOverlaySettingsFromVideoSource(vs);
            $('#banner-info').classList.remove('hidden');
            $('#banner-info').innerHTML = '🖼️ Баннер загружен';
        } catch (e) {
            alert('Ошибка загрузки баннера: ' + e.message);
        }
    }

    // ════════════════════════════════════════
    // WORKSPACE: Редактор
    // ════════════════════════════════════════

    async function loadClips() {
        if (!state.activeProjectId) return;
        try {
            const projResp = await fetch(`${API}/projects/${state.activeProjectId}`);
            const proj = await projResp.json();
            state.activeVideoSource = proj.video_source || null;
            if (state.activeVideoSource) {
                loadOverlaySettingsFromVideoSource(state.activeVideoSource);
            }

            const resp = await fetch(`${API}/projects/${state.activeProjectId}/clips`);
            state.clips = await resp.json();
            renderWorkspace();
        } catch (e) {
            console.error(e);
        }
    }

    function renderWorkspace() {
        const empty = $('#workspace-empty');
        const content = $('#workspace-content');

        const vs = state.activeVideoSource;
        const hasTranscription = vs && vs.has_transcription;

        if (!hasTranscription && state.clips.length === 0) {
            empty.classList.remove('hidden');
            content.classList.add('hidden');
            return;
        }

        empty.classList.add('hidden');
        content.classList.remove('hidden');

        // Загружаем транскрипцию
        if (hasTranscription) {
            loadTranscription();
        } else {
            $('#transcript-text').innerHTML = '<p class="text-gray-500 text-sm">Транскрипция ещё не выполнена. Запустите анализ речи.</p>';
        }

        // Рендер клипов
        renderClipsList();
        updateProcessBtn();
        updatePreviewStage();
    }

    function getSelectableClips() {
        return state.clips.filter(c => c.status !== 'processing');
    }

    function updateSelectAllCheckbox() {
        const selectable = getSelectableClips();
        const selectAll = $('#select-all-clips');
        const row = $('#select-all-row');
        if (!selectAll || !row) return;

        if (selectable.length === 0) {
            row.classList.add('hidden');
            return;
        }
        row.classList.remove('hidden');

        const selectedCount = selectable.filter(c => state.selectedClips.has(c.id)).length;
        selectAll.checked = selectedCount === selectable.length;
        selectAll.indeterminate = selectedCount > 0 && selectedCount < selectable.length;
    }

    function toggleSelectAll(checked) {
        const selectable = getSelectableClips();
        if (checked) {
            selectable.forEach(c => state.selectedClips.add(c.id));
        } else {
            selectable.forEach(c => state.selectedClips.delete(c.id));
        }
        renderClipsList();
        updateProcessBtn();
        updateSelectAllCheckbox();
    }

    function renderClipsList() {
        const clipsList = $('#clips-list');
        if (state.clips.length === 0) {
            clipsList.innerHTML = '<p class="text-gray-500 text-sm">Нет клипов. Выделите текст в транскрипте и нажмите «Создать клип».</p>';
            updateSelectAllCheckbox();
            return;
        }
        clipsList.innerHTML = state.clips.map(c => renderClipCard(c)).join('');
        clipsList.querySelectorAll('.clip-card').forEach(card => {
            card.addEventListener('click', (e) => {
                if (e.target.closest('.clip-checkbox') || e.target.tagName === 'BUTTON') return;
                toggleClipSelection(card.dataset.id);
                setPreviewClip(card.dataset.id);
            });
        });
        clipsList.querySelectorAll('.clip-checkbox').forEach(cb => {
            cb.addEventListener('change', (e) => {
                e.stopPropagation();
                const id = cb.dataset.id;
                if (cb.checked) state.selectedClips.add(id);
                else state.selectedClips.delete(id);
                updateSelectAllCheckbox();
                updateProcessBtn();
                const card = cb.closest('.clip-card');
                if (card) card.classList.toggle('selected', cb.checked);
            });
        });
        clipsList.querySelectorAll('.clip-delete').forEach(btn => {
            btn.addEventListener('click', async (e) => {
                e.stopPropagation();
                await deleteClip(btn.dataset.id);
            });
        });
        clipsList.querySelectorAll('.gen-meta-btn').forEach(btn => {
            btn.addEventListener('click', async (e) => {
                e.stopPropagation();
                await generateClipMeta(btn.dataset.id);
            });
        });
        updateSelectAllCheckbox();
    }

    async function loadTranscription() {
        if (!state.activeProjectId) return;
        try {
            const resp = await fetch(`${API}/projects/${state.activeProjectId}/transcription`);
            if (!resp.ok) return;
            const data = await resp.json();
            state.transcriptionSegments = data.segments || [];
            const div = $('#transcript-text');
            div.innerHTML = data.segments.map((seg, i) => {
                const cls = [
                    'transcript-segment',
                    seg.suggested_shorts ? 'suggested' : '',
                    state.selectedSegments.has(i) ? 'selected' : '',
                ].filter(Boolean).join(' ');
                return `<div class="${cls}" data-idx="${i}">
                    <span class="transcript-time">[${fmtTime(seg.start)} → ${fmtTime(seg.end)}]</span>
                    ${escHtml(seg.text)}
                </div>`;
            }).join('');

            // Кнопка создания клипа из выделенных сегментов
            const btnHtml = state.selectedSegments.size > 0
                ? `<button id="btn-create-from-selection" class="mt-3 w-full bg-green-600 hover:bg-green-700 py-2 rounded-lg text-sm font-medium transition">
                     ✂️ Создать клип (${state.selectedSegments.size} сегментов)
                   </button>`
                : '';
            div.innerHTML += btnHtml;

            div.querySelectorAll('.transcript-segment').forEach(el => {
                el.addEventListener('click', () => toggleSegment(parseInt(el.dataset.idx)));
            });

            const createBtn = $('#btn-create-from-selection');
            if (createBtn) {
                createBtn.addEventListener('click', createClipFromSelection);
            }
        } catch (e) {
            console.error(e);
        }
    }

    async function createClipFromSelection() {
        if (state.selectedSegments.size === 0) return;
        // Получаем данные транскрипции для выделенных сегментов
        const resp = await fetch(`${API}/projects/${state.activeProjectId}/transcription`);
        const data = await resp.json();
        const indices = [...state.selectedSegments].sort((a, b) => a - b);
        const selSegs = indices.map(i => data.segments[i]);
        const startTime = selSegs[0].start;
        const endTime = selSegs[selSegs.length - 1].end;
        const textSnippet = selSegs.map(s => s.text).join(' ');

        try {
            await fetch(`${API}/projects/${state.activeProjectId}/clips`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    start_time: startTime,
                    end_time: endTime,
                    text_snippet: textSnippet,
                    title: `Shorts (${fmtTime(startTime)})`,
                    include_banner: state.activeVideoSource?.banner_path != null,
                }),
            });
            state.selectedSegments.clear();
            await loadClips();
        } catch (e) {
            alert('Ошибка: ' + e.message);
        }
    }

    function renderClipCard(c) {
        const statusClass = `status-${c.status}`;
        const statusText = { pending: 'Ожидает', processing: 'В работе', done: 'Готов', error: 'Ошибка' }[c.status] || c.status;
        const selected = state.selectedClips.has(c.id) ? 'selected' : '';
        const isPreview = state.previewClipId === c.id ? 'ring-1 ring-purple-500/50' : '';
        const suggestedBadge = c.is_suggested
            ? `<span class="status-badge ai-suggested-badge ml-1">★ авто</span>` : '';
        return `
        <div class="clip-card ${selected} ${isPreview}" data-id="${c.id}">
            <div class="flex items-start gap-2">
                <input type="checkbox" class="clip-checkbox mt-0.5" data-id="${c.id}" ${selected ? 'checked' : ''}>
                <div class="flex-1 min-w-0">
                    <div class="flex items-center justify-between mb-2">
                        <span class="font-medium text-sm">${escHtml(c.title || 'Без названия')}${suggestedBadge}</span>
                        <span class="status-badge ${statusClass}">${statusText}</span>
                    </div>
                    <div class="text-xs text-gray-500">
                        ${fmtTime(c.start_time)} → ${fmtTime(c.end_time)} (${fmtDuration(c.end_time - c.start_time)})
                    </div>
                    ${c.text_snippet ? `<div class="text-xs text-gray-400 mt-1 truncate">${escHtml(c.text_snippet)}</div>` : ''}
                    <div class="flex gap-2 mt-2">
                        ${c.text_snippet ? `<button class="gen-meta-btn text-yellow-400 hover:text-yellow-300 text-xs" data-id="${c.id}">🤖 Название</button>` : ''}
                        <button class="clip-delete text-red-400 hover:text-red-300 text-xs" data-id="${c.id}">Удалить</button>
                    </div>
                </div>
            </div>
        </div>`;
    }

    function toggleClipSelection(id) {
        if (state.selectedClips.has(id)) state.selectedClips.delete(id);
        else state.selectedClips.add(id);
        renderClipsList();
        updateProcessBtn();
    }

    function setPreviewClip(id) {
        state.previewClipId = id;
        renderClipsList();
        updatePreviewVideo();
    }

    function toggleSegment(idx) {
        if (state.selectedSegments.has(idx)) state.selectedSegments.delete(idx);
        else state.selectedSegments.add(idx);
        loadTranscription();
    }

    function updateProcessBtn() {
        const btn = $('#btn-process-selected');
        btn.disabled = state.selectedClips.size === 0;
        btn.textContent = state.selectedClips.size > 0
            ? `⚡ Обработать (${state.selectedClips.size})`
            : '⚡ Обработать выбранные';
    }

    async function deleteClip(clipId) {
        if (!confirm('Удалить клип?')) return;
        try {
            await fetch(`${API}/projects/${state.activeProjectId}/clips/${clipId}`, { method: 'DELETE' });
            state.selectedClips.delete(clipId);
            if (state.previewClipId === clipId) state.previewClipId = null;
            state.clips = state.clips.filter(c => c.id !== clipId);
            renderClipsList();
            updateProcessBtn();
            updatePreviewStage();
        } catch (e) {
            alert('Ошибка: ' + e.message);
        }
    }

    async function generateClipMeta(clipId) {
        const btn = document.querySelector(`.gen-meta-btn[data-id="${clipId}"]`);
        if (btn) { btn.disabled = true; btn.textContent = '⏳...'; }
        try {
            const resp = await fetch(`${API}/projects/${state.activeProjectId}/clips/${clipId}/generate-metadata`, {
                method: 'POST',
            });
            if (!resp.ok) {
                const err = await resp.json();
                throw new Error(err.detail || 'Ошибка генерации');
            }
            const data = await resp.json();
            alert(`Название: ${data.title}\n\nОписание: ${data.description}`);
            await loadClips();
        } catch (e) {
            alert('Ошибка: ' + e.message);
        } finally {
            if (btn) { btn.disabled = false; btn.textContent = '🤖 Название'; }
        }
    }

    // ════════════════════════════════════════
    // PREVIEW: Оверлеи субтитров и баннера
    // ════════════════════════════════════════

    function toHexColor(color) {
        const map = { white: '#ffffff', black: '#000000', red: '#ff0000', yellow: '#ffff00' };
        if (!color) return '#ffffff';
        if (color.startsWith('#')) return color;
        return map[color.toLowerCase()] || color;
    }

    function loadOverlaySettingsFromVideoSource(vs) {
        state.overlaySettings = {
            subtitles_enabled: vs.subtitles_enabled !== false,
            subtitle_font: vs.subtitle_font || 'Arial',
            subtitle_font_size: vs.subtitle_font_size || 52,
            subtitle_color: toHexColor(vs.subtitle_color || 'white'),
            subtitle_stroke_color: toHexColor(vs.subtitle_stroke_color || 'black'),
            subtitle_stroke_width: vs.subtitle_stroke_width ?? 3,
            subtitle_x: vs.subtitle_x,
            subtitle_y: vs.subtitle_y,
            banner_position: vs.banner_position || 'bottom',
            banner_x: vs.banner_x,
            banner_y: vs.banner_y,
            banner_scale: vs.banner_scale ?? 0.9,
            banner_opacity: vs.banner_opacity ?? 0.85,
        };
        state.bannerPosition = state.overlaySettings.banner_position;
        applyOverlaySettingsToUI();
    }

    function applyOverlaySettingsToUI() {
        const s = state.overlaySettings;
        const subEnabled = $('#sub-enabled');
        if (subEnabled) subEnabled.checked = s.subtitles_enabled;
        const subFont = $('#sub-font');
        if (subFont) subFont.value = s.subtitle_font;
        const subSize = $('#sub-size');
        if (subSize) subSize.value = s.subtitle_font_size;
        const subSizeVal = $('#sub-size-val');
        if (subSizeVal) subSizeVal.textContent = s.subtitle_font_size;
        const subColor = $('#sub-color');
        if (subColor) subColor.value = s.subtitle_color;
        const subStrokeColor = $('#sub-stroke-color');
        if (subStrokeColor) subStrokeColor.value = s.subtitle_stroke_color;
        const subStrokeWidth = $('#sub-stroke-width');
        if (subStrokeWidth) subStrokeWidth.value = s.subtitle_stroke_width;
        const subStrokeVal = $('#sub-stroke-val');
        if (subStrokeVal) subStrokeVal.textContent = s.subtitle_stroke_width;

        const bannerScale = $('#banner-scale');
        if (bannerScale) bannerScale.value = Math.round(s.banner_scale * 100);
        const bannerScaleVal = $('#banner-scale-val');
        if (bannerScaleVal) bannerScaleVal.textContent = Math.round(s.banner_scale * 100);
        const bannerOpacity = $('#banner-opacity');
        if (bannerOpacity) bannerOpacity.value = Math.round(s.banner_opacity * 100);
        const bannerOpacityVal = $('#banner-opacity-val');
        if (bannerOpacityVal) bannerOpacityVal.textContent = Math.round(s.banner_opacity * 100);

        $$('.preview-pos-btn').forEach(btn => {
            const active = btn.dataset.pos === s.banner_position;
            btn.classList.toggle('active', active);
            btn.classList.toggle('border-purple-600', active);
            btn.classList.toggle('bg-purple-600/20', active);
            btn.classList.toggle('text-purple-300', active);
            btn.classList.toggle('border-gray-700', !active);
            btn.classList.toggle('text-gray-400', !active);
        });

        $$('.pos-btn').forEach(btn => {
            const active = btn.dataset.pos === s.banner_position;
            btn.classList.toggle('bg-brand-600/20', active);
            btn.classList.toggle('border-brand-600', active);
            btn.classList.toggle('text-brand-300', active);
            btn.classList.toggle('border-gray-700', !active);
            btn.classList.toggle('text-gray-400', !active);
        });

        updatePreviewOverlays();
    }

    function debouncedSaveOverlaySettings(payload) {
        if (saveOverlayTimer) clearTimeout(saveOverlayTimer);
        saveOverlayTimer = setTimeout(() => saveOverlaySettings(payload), 400);
    }

    async function saveOverlaySettings(payload) {
        if (!state.activeProjectId) return;
        try {
            const resp = await fetch(`${API}/projects/${state.activeProjectId}/overlay-settings`, {
                method: 'PATCH',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload),
            });
            if (resp.ok) {
                const vs = await resp.json();
                state.activeVideoSource = vs;
            }
        } catch (e) {
            console.error('Ошибка сохранения настроек:', e);
        }
    }

    function getPreviewScale() {
        const stage = $('#preview-stage');
        if (!stage) return 1;
        return stage.clientWidth / CANVAS_W;
    }

    function canvasToPercent(x, y) {
        return {
            left: (x / CANVAS_W) * 100,
            top: (y / CANVAS_H) * 100,
        };
    }

    function updatePreviewOverlays() {
        const s = state.overlaySettings;
        const scale = getPreviewScale();
        const bannerEl = $('#preview-banner');
        const subtitleEl = $('#preview-subtitle');

        if (bannerEl && state.activeVideoSource?.banner_url) {
            const url = state.activeVideoSource.banner_url;
            if (bannerEl.dataset.src !== url) {
                bannerEl.dataset.src = url;
                bannerEl.src = url;
            }
            bannerEl.classList.remove('hidden');
            bannerEl.style.opacity = s.banner_opacity;
            bannerEl.style.width = (s.banner_scale * 100) + '%';
            bannerEl.style.maxWidth = (s.banner_scale * 100) + '%';

            if (bannerEl.complete) {
                positionBannerOverlay();
            } else {
                bannerEl.onload = () => positionBannerOverlay();
            }
        } else if (bannerEl) {
            bannerEl.classList.add('hidden');
        }

        if (subtitleEl) {
            if (s.subtitles_enabled) {
                subtitleEl.classList.remove('hidden');
                subtitleEl.style.fontFamily = s.subtitle_font + ', sans-serif';
                subtitleEl.style.fontSize = (s.subtitle_font_size * scale) + 'px';
                subtitleEl.style.color = s.subtitle_color;
                subtitleEl.style.webkitTextStroke = `${s.subtitle_stroke_width * scale}px ${s.subtitle_stroke_color}`;
                subtitleEl.style.paintOrder = 'stroke fill';
                positionSubtitleOverlay();
            } else {
                subtitleEl.classList.add('hidden');
            }
        }
    }

    function positionBannerOverlay() {
        const s = state.overlaySettings;
        const bannerEl = $('#preview-banner');
        const stage = $('#preview-stage');
        if (!bannerEl || !stage || bannerEl.classList.contains('hidden')) return;

        const scale = getPreviewScale();
        const bannerW = bannerEl.offsetWidth / scale;
        const bannerH = bannerEl.offsetHeight / scale;

        let x, y;
        if (s.banner_x != null && s.banner_y != null) {
            x = s.banner_x;
            y = s.banner_y;
        } else {
            x = (CANVAS_W - bannerW) / 2;
            y = calcBannerPresetY(s.banner_position, bannerH);
        }

        x = Math.max(0, Math.min(CANVAS_W - bannerW, x));
        y = Math.max(0, Math.min(CANVAS_H - bannerH, y));

        const pos = canvasToPercent(x, y);
        bannerEl.style.left = pos.left + '%';
        bannerEl.style.top = pos.top + '%';
        bannerEl.style.transform = 'none';
    }

    function positionSubtitleOverlay() {
        const s = state.overlaySettings;
        const subtitleEl = $('#preview-subtitle');
        const stage = $('#preview-stage');
        if (!subtitleEl || !stage || subtitleEl.classList.contains('hidden')) return;

        const scale = getPreviewScale();
        const subW = subtitleEl.offsetWidth / scale;
        const subH = subtitleEl.offsetHeight / scale;

        let x, y;
        if (s.subtitle_x != null && s.subtitle_y != null) {
            x = s.subtitle_x;
            y = s.subtitle_y;
        } else {
            x = (CANVAS_W - subW) / 2;
            y = CANVAS_H - subH - 60;
        }

        x = Math.max(0, Math.min(CANVAS_W - subW, x));
        y = Math.max(0, Math.min(CANVAS_H - subH, y));

        const pos = canvasToPercent(x, y);
        subtitleEl.style.left = pos.left + '%';
        subtitleEl.style.top = pos.top + '%';
        subtitleEl.style.width = '88%';
    }

    function calcBannerPresetY(position, bannerH) {
        const margin = 20;
        if (position === 'top') return margin;
        if (position === 'center') return (CANVAS_H - bannerH) / 2;
        return CANVAS_H - bannerH - margin;
    }

    function applyBannerPreset(pos) {
        state.overlaySettings.banner_position = pos;
        state.overlaySettings.banner_x = null;
        state.overlaySettings.banner_y = null;
        state.bannerPosition = pos;
        applyOverlaySettingsToUI();
        debouncedSaveOverlaySettings({ banner: { position: pos, x: null, y: null } });
    }

    function updatePreviewSubtitleText(currentTime) {
        const subtitleEl = $('#preview-subtitle');
        if (!subtitleEl || !state.overlaySettings.subtitles_enabled) return;

        const clip = state.clips.find(c => c.id === state.previewClipId);
        if (!clip) {
            subtitleEl.textContent = 'Пример субтитров';
            return;
        }

        const seg = state.transcriptionSegments.find(s =>
            s.start <= currentTime && s.end >= currentTime &&
            s.end > clip.start_time && s.start < clip.end_time
        );
        subtitleEl.textContent = seg ? seg.text.trim() : '';
        positionSubtitleOverlay();
    }

    function updatePreviewVideo() {
        const video = $('#preview-video');
        const hint = $('#preview-clip-hint');
        const vs = state.activeVideoSource;
        if (!video || !vs?.source_video_url) return;

        let clip = state.clips.find(c => c.id === state.previewClipId);
        if (!clip && state.clips.length > 0) {
            clip = state.clips[0];
            state.previewClipId = clip.id;
        }

        if (!clip) {
            if (hint) hint.textContent = 'Создайте клип для предпросмотра';
            video.removeAttribute('src');
            return;
        }

        if (hint) hint.textContent = `${clip.title || 'Клип'} · ${fmtTime(clip.start_time)} → ${fmtTime(clip.end_time)}`;

        if (video.dataset.clipId !== clip.id) {
            video.dataset.clipId = clip.id;
            video.src = vs.source_video_url;
            video.onloadedmetadata = () => {
                video.currentTime = clip.start_time + 0.1;
            };
        }

        video.onplay = () => {
            if (video.currentTime < clip.start_time || video.currentTime >= clip.end_time) {
                video.currentTime = clip.start_time;
            }
        };

        video.ontimeupdate = () => {
            if (video.currentTime >= clip.end_time) {
                video.currentTime = clip.start_time;
            }
            updatePreviewSubtitleText(video.currentTime);
        };

        updatePreviewOverlays();
        updatePreviewSubtitleText(clip.start_time);
        video.play().catch(() => {});
    }

    function updatePreviewStage() {
        updatePreviewVideo();
        updatePreviewOverlays();
    }

    function makeOverlayDraggable(el, type) {
        if (!el || el.dataset.dragBound) return;
        el.dataset.dragBound = '1';

        el.addEventListener('pointerdown', (e) => {
            e.preventDefault();
            e.stopPropagation();
            el.classList.add('dragging');
            el.setPointerCapture(e.pointerId);

            const stage = $('#preview-stage');
            const rect = stage.getBoundingClientRect();
            const scale = rect.width / CANVAS_W;

            const elRect = el.getBoundingClientRect();
            const offsetX = (e.clientX - elRect.left) / scale;
            const offsetY = (e.clientY - elRect.top) / scale;

            const onMove = (ev) => {
                let x = (ev.clientX - rect.left) / scale - offsetX;
                let y = (ev.clientY - rect.top) / scale - offsetY;

                const elW = el.offsetWidth / scale;
                const elH = el.offsetHeight / scale;
                x = Math.max(0, Math.min(CANVAS_W - elW, x));
                y = Math.max(0, Math.min(CANVAS_H - elH, y));

                const pos = canvasToPercent(x, y);
                el.style.left = pos.left + '%';
                el.style.top = pos.top + '%';

                if (type === 'banner') {
                    state.overlaySettings.banner_x = x;
                    state.overlaySettings.banner_y = y;
                } else {
                    state.overlaySettings.subtitle_x = x;
                    state.overlaySettings.subtitle_y = y;
                }
            };

            const onUp = () => {
                el.classList.remove('dragging');
                el.removeEventListener('pointermove', onMove);
                el.removeEventListener('pointerup', onUp);
                el.removeEventListener('pointercancel', onUp);

                if (type === 'banner') {
                    debouncedSaveOverlaySettings({
                        banner: {
                            x: state.overlaySettings.banner_x,
                            y: state.overlaySettings.banner_y,
                        },
                    });
                } else {
                    debouncedSaveOverlaySettings({
                        subtitles: {
                            x: state.overlaySettings.subtitle_x,
                            y: state.overlaySettings.subtitle_y,
                        },
                    });
                }
            };

            el.addEventListener('pointermove', onMove);
            el.addEventListener('pointerup', onUp);
            el.addEventListener('pointercancel', onUp);
        });
    }

    function bindPreview() {
        const subEnabled = $('#sub-enabled');
        const subFont = $('#sub-font');
        const subSize = $('#sub-size');
        const subColor = $('#sub-color');
        const subStrokeColor = $('#sub-stroke-color');
        const subStrokeWidth = $('#sub-stroke-width');
        const bannerScale = $('#banner-scale');
        const bannerOpacity = $('#banner-opacity');

        if (subEnabled) {
            subEnabled.addEventListener('change', () => {
                state.overlaySettings.subtitles_enabled = subEnabled.checked;
                updatePreviewOverlays();
                debouncedSaveOverlaySettings({ subtitles: { enabled: subEnabled.checked } });
            });
        }

        if (subFont) {
            subFont.addEventListener('change', () => {
                state.overlaySettings.subtitle_font = subFont.value;
                updatePreviewOverlays();
                debouncedSaveOverlaySettings({ subtitles: { font: subFont.value } });
            });
        }

        if (subSize) {
            subSize.addEventListener('input', () => {
                state.overlaySettings.subtitle_font_size = parseInt(subSize.value, 10);
                $('#sub-size-val').textContent = subSize.value;
                updatePreviewOverlays();
                debouncedSaveOverlaySettings({ subtitles: { font_size: parseInt(subSize.value, 10) } });
            });
        }

        if (subColor) {
            subColor.addEventListener('input', () => {
                state.overlaySettings.subtitle_color = subColor.value;
                updatePreviewOverlays();
                debouncedSaveOverlaySettings({ subtitles: { color: subColor.value } });
            });
        }

        if (subStrokeColor) {
            subStrokeColor.addEventListener('input', () => {
                state.overlaySettings.subtitle_stroke_color = subStrokeColor.value;
                updatePreviewOverlays();
                debouncedSaveOverlaySettings({ subtitles: { stroke_color: subStrokeColor.value } });
            });
        }

        if (subStrokeWidth) {
            subStrokeWidth.addEventListener('input', () => {
                state.overlaySettings.subtitle_stroke_width = parseInt(subStrokeWidth.value, 10);
                $('#sub-stroke-val').textContent = subStrokeWidth.value;
                updatePreviewOverlays();
                debouncedSaveOverlaySettings({ subtitles: { stroke_width: parseInt(subStrokeWidth.value, 10) } });
            });
        }

        if (bannerScale) {
            bannerScale.addEventListener('input', () => {
                state.overlaySettings.banner_scale = parseInt(bannerScale.value, 10) / 100;
                state.overlaySettings.banner_x = null;
                state.overlaySettings.banner_y = null;
                $('#banner-scale-val').textContent = bannerScale.value;
                updatePreviewOverlays();
                debouncedSaveOverlaySettings({
                    banner: { scale: state.overlaySettings.banner_scale, x: null, y: null },
                });
            });
        }

        if (bannerOpacity) {
            bannerOpacity.addEventListener('input', () => {
                state.overlaySettings.banner_opacity = parseInt(bannerOpacity.value, 10) / 100;
                $('#banner-opacity-val').textContent = bannerOpacity.value;
                updatePreviewOverlays();
                debouncedSaveOverlaySettings({ banner: { opacity: state.overlaySettings.banner_opacity } });
            });
        }

        $$('.preview-pos-btn').forEach(btn => {
            btn.addEventListener('click', () => applyBannerPreset(btn.dataset.pos));
        });

        makeOverlayDraggable($('#preview-banner'), 'banner');
        makeOverlayDraggable($('#preview-subtitle'), 'subtitle');

        window.addEventListener('resize', () => {
            updatePreviewOverlays();
        });
    }

    function bindWorkspace() {
        $('#select-all-clips').addEventListener('change', (e) => {
            toggleSelectAll(e.target.checked);
        });

        $('#btn-process-selected').addEventListener('click', async () => {
            if (state.selectedClips.size === 0) return;
            const btn = $('#btn-process-selected');
            btn.disabled = true;
            btn.textContent = '⏳ Запускаю...';

            try {
                const resp = await fetch(`${API}/projects/${state.activeProjectId}/process`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ clip_ids: [...state.selectedClips] }),
                });
                const data = await resp.json();
                showProgress('process');
                startTaskPolling(data.task_id, async () => {
                    await loadClips();
                    btn.disabled = false;
                    updateProcessBtn();
                });
            } catch (e) {
                alert('Ошибка: ' + e.message);
                btn.disabled = false;
                updateProcessBtn();
            }
        });
    }

    // ════════════════════════════════════════
    // PROGRESS POLLING
    // ════════════════════════════════════════

    function showProgress(type, clipMode) {
        const panel = $('#progress-panel');
        panel.classList.remove('hidden');
        if (type === 'transcribe') {
            const labels = {
                manual: '🔊 Распознавание речи',
                heuristic: '🔊 Распознавание + авто-нарезка',
                ai: '🤖 Распознавание + ИИ-анализ',
            };
            $('#progress-type').textContent = labels[clipMode] || labels.heuristic;
        } else {
            $('#progress-type').textContent = '🎬 Обработка видео';
        }
        $('#progress-pct').textContent = '0%';
        $('#progress-bar').style.width = '0%';
        $('#progress-msg').textContent = 'Запуск...';
    }

    function hideProgress() {
        $('#progress-panel').classList.add('hidden');
        if (state.pollTimer) { clearInterval(state.pollTimer); state.pollTimer = null; }
        state.activeTaskId = null;
    }

    function startTaskPolling(taskId, onDone) {
        state.activeTaskId = taskId;
        if (state.pollTimer) clearInterval(state.pollTimer);

        state.pollTimer = setInterval(async () => {
            try {
                const resp = await fetch(`${API}/tasks/${taskId}`);
                const task = await resp.json();
                $('#progress-pct').textContent = task.progress + '%';
                $('#progress-bar').style.width = task.progress + '%';
                $('#progress-msg').textContent = task.message || '';

                if (task.status === 'done') {
                    hideProgress();
                    $('#btn-analyze').disabled = false;
                    updateAnalyzeButtonLabel();
                    if (onDone) onDone(task.result);
                } else if (task.status === 'error') {
                    hideProgress();
                    $('#btn-analyze').disabled = false;
                    updateAnalyzeButtonLabel();
                    alert('Ошибка: ' + (task.error || 'Неизвестная ошибка'));
                }
            } catch (e) {
                // Сервер может быть занят — игнорируем
            }
        }, 2000);
    }

    // ════════════════════════════════════════
    // PUBLISHING: Превью + Сохранение
    // ════════════════════════════════════════

    function bindPublishing() {
        $('#btn-publish-selected').addEventListener('click', publishSelected);
        $('#btn-save-selected').addEventListener('click', saveSelected);

        $('#publish-select-all').addEventListener('change', (e) => {
            const done = state.clips.filter(c => c.status === 'done');
            if (e.target.checked) {
                done.forEach(c => state.selectedClips.add(c.id));
            } else {
                done.forEach(c => state.selectedClips.delete(c.id));
            }
            loadPublishQueue();
        });

        $('#publishing-list').addEventListener('click', (e) => {
            const checkbox = e.target.closest('.publish-checkbox');
            if (checkbox) {
                e.stopPropagation();
                const id = checkbox.dataset.id;
                if (checkbox.checked) state.selectedClips.add(id);
                else state.selectedClips.delete(id);
                updatePublishSelectAll();
                return;
            }
            const card = e.target.closest('.clip-card');
            if (!card) return;
            const clip = state.clips.find(c => c.id === card.dataset.id);
            if (clip && clip.output_path) showPreview(clip);
        });
    }

    function updatePublishSelectAll() {
        const done = state.clips.filter(c => c.status === 'done');
        const selectAll = $('#publish-select-all');
        const row = $('#publish-select-all-row');
        if (!selectAll || !row || done.length === 0) {
            if (row) row.classList.add('hidden');
            return;
        }
        row.classList.remove('hidden');
        const selectedCount = done.filter(c => state.selectedClips.has(c.id)).length;
        selectAll.checked = selectedCount === done.length;
        selectAll.indeterminate = selectedCount > 0 && selectedCount < done.length;
    }

    async function loadPublishQueue() {
        if (!state.activeProjectId) return;
        try {
            const resp = await fetch(`${API}/projects/${state.activeProjectId}/clips`);
            const clips = await resp.json();
            state.clips = clips;
            const done = clips.filter(c => c.status === 'done');
            const list = $('#publishing-list');
            const pubBtn = $('#btn-publish-selected');
            const saveBtn = $('#btn-save-selected');

            if (done.length === 0) {
                list.innerHTML = '<p class="text-gray-500 text-sm">Нет готовых клипов. Сначала обработайте видео.</p>';
                pubBtn.classList.add('hidden');
                saveBtn.classList.add('hidden');
            } else {
                list.innerHTML = done.map(c => renderPublishCard(c)).join('');
                pubBtn.classList.remove('hidden');
                saveBtn.classList.remove('hidden');
                updatePublishSelectAll();
            }
        } catch (e) {
            console.error(e);
        }
    }

    function renderPublishCard(c) {
        const sel = state.selectedClips.has(c.id) ? 'selected' : '';
        const ytBadge = c.yt_status ? `<span class="status-badge status-published">YT</span>` : '';
        const vkBadge = c.vk_status ? `<span class="status-badge status-published">VK</span>` : '';
        return `
        <div class="clip-card ${sel}" data-id="${c.id}">
            <div class="flex items-center gap-2">
                <input type="checkbox" class="publish-checkbox clip-checkbox" data-id="${c.id}" ${sel ? 'checked' : ''}>
                <div class="flex-1 flex items-center justify-between min-w-0">
                    <div>
                        <span class="font-medium text-sm">${escHtml(c.title || 'Без названия')}</span>
                        <span class="text-xs text-gray-500 ml-2">${fmtDuration(c.end_time - c.start_time)}</span>
                    </div>
                    <div class="flex gap-2">${ytBadge}${vkBadge}</div>
                </div>
            </div>
        </div>`;
    }

    function showPreview(clip) {
        const container = $('#preview-container');
        const info = $('#preview-info');
        const videoUrl = clip.output_path.replace(/\\/g, '/');
        // Путь относительно output/
        const relPath = videoUrl.split('/output/').pop() || videoUrl;
        container.innerHTML = `<video src="/output/${relPath}" controls autoplay loop class="w-full h-full object-contain rounded-lg"></video>`;
        info.innerHTML = `<b>${escHtml(clip.title || 'Без названия')}</b><br>${fmtDuration(clip.end_time - clip.start_time)}`;
    }

    async function saveSelected() {
        if (state.selectedClips.size === 0) { alert('Выберите клипы'); return; }
        // Открываем диалог выбора папки (через API)
        const folder = prompt('Путь для сохранения (например, C:\\Users\\Wise\\Desktop\\Shorts):', '');
        if (!folder) return;

        for (const clipId of state.selectedClips) {
            const clip = state.clips.find(c => c.id === clipId);
            if (!clip || !clip.output_path) continue;
            try {
                const resp = await fetch(`${API}/projects/${state.activeProjectId}/clips/${clipId}/save`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ target_dir: folder }),
                });
                const data = await resp.json();
                if (data.ok) {
                    console.log(`Сохранено: ${data.saved_path}`);
                }
            } catch (e) {
                console.error(`Ошибка сохранения ${clipId}:`, e);
            }
        }
        alert('Готово! Файлы сохранены в: ' + folder);
    }

    async function publishSelected() {
        if (state.selectedClips.size === 0) return;
        const privacy = confirm('Опубликовать как Public? (OK = public, Отмена = private)') ? 'public' : 'private';
        const platforms = [];
        if (confirm('Публиковать в YouTube?')) platforms.push('youtube');
        if (confirm('Публиковать в VK?')) platforms.push('vk');
        if (platforms.length === 0) return;

        try {
            const resp = await fetch(`${API}/projects/${state.activeProjectId}/publish`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ clip_ids: [...state.selectedClips], platforms, privacy }),
            });
            const results = await resp.json();
            let msg = 'Результаты публикации:\n';
            for (const r of results) {
                msg += `${r.clip_id} → ${r.platform}: ${r.status}${r.url ? ' ' + r.url : ''}${r.error ? ' (' + r.error + ')' : ''}\n`;
            }
            alert(msg);
            await loadPublishQueue();
        } catch (e) {
            alert('Ошибка: ' + e.message);
        }
    }

    // ════════════════════════════════════════
    // SETTINGS: Токены API + Ollama + Updates
    // ════════════════════════════════════════

    function bindSettings() {
        $('#btn-save-tokens').addEventListener('click', saveTokens);
        $('#btn-check-ollama').addEventListener('click', checkOllamaStatus);
        $('#btn-check-update').addEventListener('click', checkForUpdates);
    }

    async function saveTokens() {
        const vkToken = $('#vk-token').value.trim();
        const ytSecret = $('#yt-secret').value.trim();
        const status = $('#tokens-status');
        const body = {};
        if (vkToken) body.vk_access_token = vkToken;
        if (ytSecret) body.youtube_client_secret_json = ytSecret;
        try {
            const resp = await fetch(`${API}/projects/settings/tokens`, {
                method: 'PUT', headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(body),
            });
            if (resp.ok) { status.textContent = '✅ Сохранено'; status.className = 'ml-3 text-sm text-green-400'; }
            else { throw new Error((await resp.json()).detail || 'Ошибка'); }
        } catch (e) {
            status.textContent = '❌ ' + e.message; status.className = 'ml-3 text-sm text-red-400';
        }
    }

    async function checkOllamaStatus() {
        const div = $('#ollama-result');
        div.classList.remove('hidden');
        div.innerHTML = '⏳ Проверяю...';
        try {
            const resp = await fetch(`${API}/ollama-status`);
            const data = await resp.json();
            if (data.running) {
                const missing = data.missing_models.length
                    ? `<br>⚠ Не хватает моделей: ${data.missing_models.join(', ')}<br><code>ollama pull ${data.missing_models[0]}</code>`
                    : '<br>✅ Все модели на месте';
                div.innerHTML = `✅ Ollama запущен${missing}`;
            } else {
                div.innerHTML = `❌ ${data.error}<br><br>Установите: <a href="https://ollama.com/download" class="text-brand-400 underline" target="_blank">ollama.com/download</a>`;
            }
        } catch (e) {
            div.innerHTML = `❌ Ошибка: ${e.message}`;
        }
    }

    async function checkForUpdates() {
        const div = $('#update-result');
        div.classList.remove('hidden');
        div.innerHTML = '⏳ Проверяю обновления...';
        try {
            const resp = await fetch(`${API}/check-update`);
            const data = await resp.json();
            if (data.update_available) {
                div.innerHTML = `🔔 <b>Новая версия ${data.latest}</b> (у вас ${data.current})<br>
                    <a href="${data.url}" class="text-brand-400 underline" target="_blank">Открыть релиз</a>
                    <button onclick="doUpdate()" class="ml-3 bg-green-600 hover:bg-green-700 px-3 py-1 rounded-lg text-xs transition">Обновить сейчас</button>`;
            } else {
                div.innerHTML = `✅ У вас последняя версия (${data.current})`;
            }
        } catch (e) {
            div.innerHTML = `❌ Ошибка: ${e.message}`;
        }
    }

    async function doUpdate() {
        const div = $('#update-result');
        div.innerHTML = '⏳ Обновляю... (git pull)';
        try {
            const resp = await fetch(`${API}/do-update`, { method: 'POST' });
            const data = await resp.json();
            if (data.ok) {
                div.innerHTML = `✅ ${data.message}<br><br><button onclick="location.reload()" class="bg-brand-600 hover:bg-brand-700 px-4 py-2 rounded-lg text-sm transition">Перезапустить</button>`;
            } else {
                div.innerHTML = `❌ ${data.message}`;
            }
        } catch (e) {
            div.innerHTML = `❌ Ошибка: ${e.message}`;
        }
    }
    window.doUpdate = doUpdate;

    // ════════════════════════════════════════
    // МОДАЛЬНОЕ ОКНО: Создание клипа вручную
    // ════════════════════════════════════════

    function bindModal() {
        $('#modal-cancel').addEventListener('click', closeModal);
        $('#modal-overlay').addEventListener('click', e => { if (e.target === $('#modal-overlay')) closeModal(); });
        $('#modal-create').addEventListener('click', async () => {
            const start = parseFloat($('#modal-start').value);
            const end = parseFloat($('#modal-end').value);
            const title = $('#modal-title').value;
            const includeBanner = $('#modal-banner').checked;

            if (isNaN(start) || isNaN(end) || end <= start) {
                alert('Некорректный диапазон времени');
                return;
            }

            try {
                await fetch(`${API}/projects/${state.activeProjectId}/clips`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ start_time: start, end_time: end, title, include_banner: includeBanner }),
                });
                closeModal();
                await loadClips();
            } catch (e) {
                alert('Ошибка: ' + e.message);
            }
        });
    }

    function openModal(start, end) {
        $('#modal-start').value = start || 0;
        $('#modal-end').value = end || 60;
        $('#modal-title').value = '';
        $('#modal-banner').checked = true;
        $('#modal-overlay').classList.remove('hidden');
    }

    function closeModal() {
        $('#modal-overlay').classList.add('hidden');
    }

    // Глобальная функция для вызова из транскрипта
    window.openClipModal = openModal;

    // ════════════════════════════════════════
    // УТИЛИТЫ
    // ════════════════════════════════════════

    function fmtTime(seconds) {
        const m = Math.floor(seconds / 60);
        const s = Math.floor(seconds % 60);
        return `${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`;
    }

    function fmtDuration(seconds) {
        if (!seconds) return '?';
        const m = Math.floor(seconds / 60);
        const s = Math.floor(seconds % 60);
        if (m > 0) return `${m}м ${s}с`;
        return `${s}с`;
    }

    function escHtml(str) {
        const div = document.createElement('div');
        div.textContent = str || '';
        return div.innerHTML;
    }

    // ── СТАРТ ──
    init();
})();
