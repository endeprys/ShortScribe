/**
 * Shorts Clipper — Frontend SPA
 * Управляет навигацией, загрузкой, созданием клипов и публикацией.
 */
(function () {
    'use strict';

    const API = '/api';
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
    };

    // ── ДОМ-элементы ──
    const $ = (sel) => document.querySelector(sel);
    const $$ = (sel) => document.querySelectorAll(sel);

    // ── ИНИЦИАЛИЗАЦИЯ ──
    async function init() {
        bindNavigation();
        bindDashboard();
        bindWorkspace();
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
            $('#btn-analyze').classList.remove('hidden');

            if (vs.banner_path) {
                $('#banner-info').classList.remove('hidden');
                $('#banner-info').innerHTML = `🖼️ Баннер загружен`;
            }
        } else {
            $('#video-info').classList.add('hidden');
            $('#banner-dropzone').classList.add('hidden');
            $('#banner-pos-panel').classList.add('hidden');
            $('#btn-analyze').classList.add('hidden');
        }
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
                    await fetch(`${API}/projects/${state.activeProjectId}/banner-settings`, {
                        method: 'PATCH',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ position: pos }),
                    });
                }
            });
        });

        // Кнопка анализа
        $('#btn-analyze').addEventListener('click', async () => {
            if (!state.activeProjectId) return;
            $('#btn-analyze').disabled = true;
            $('#btn-analyze').textContent = '⏳ Запускаю...';
            try {
                const resp = await fetch(`${API}/projects/${state.activeProjectId}/transcribe`, { method: 'POST' });
                if (!resp.ok) {
                    const err = await resp.json();
                    throw new Error(err.detail || 'Ошибка');
                }
                const data = await resp.json();
                // Начинаем polling прогресса
                showProgress('transcribe');
                startTaskPolling(data.task_id, () => {
                    // По завершении — переключаемся на workspace
                    loadProjects();
                    switchTab('workspace');
                    loadClips();
                });
            } catch (e) {
                alert('Ошибка анализа: ' + e.message);
                $('#btn-analyze').disabled = false;
                $('#btn-analyze').textContent = '🔍 Запустить анализ речи';
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
    }

    function renderClipsList() {
        const clipsList = $('#clips-list');
        if (state.clips.length === 0) {
            clipsList.innerHTML = '<p class="text-gray-500 text-sm">Нет клипов. Выделите текст в транскрипте и нажмите «Создать клип».</p>';
        } else {
            clipsList.innerHTML = state.clips.map(c => renderClipCard(c)).join('');
            clipsList.querySelectorAll('.clip-card').forEach(card => {
                card.addEventListener('click', (e) => {
                    if (e.target.tagName === 'BUTTON' || e.target.tagName === 'INPUT') return;
                    toggleClipSelection(card.dataset.id);
                });
            });
            // Кнопки удаления
            clipsList.querySelectorAll('.clip-delete').forEach(btn => {
                btn.addEventListener('click', async (e) => {
                    e.stopPropagation();
                    await deleteClip(btn.dataset.id);
                });
            });
            // Кнопки генерации названия
            clipsList.querySelectorAll('.gen-meta-btn').forEach(btn => {
                btn.addEventListener('click', async (e) => {
                    e.stopPropagation();
                    await generateClipMeta(btn.dataset.id);
                });
            });
        }
    }

    async function loadTranscription() {
        if (!state.activeProjectId) return;
        try {
            const resp = await fetch(`${API}/projects/${state.activeProjectId}/transcription`);
            if (!resp.ok) return;
            const data = await resp.json();
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
        return `
        <div class="clip-card ${selected}" data-id="${c.id}">
            <div class="flex items-center justify-between mb-2">
                <span class="font-medium text-sm">${escHtml(c.title || 'Без названия')}</span>
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
        </div>`;
    }

    function toggleClipSelection(id) {
        if (state.selectedClips.has(id)) state.selectedClips.delete(id);
        else state.selectedClips.add(id);
        renderWorkspace();
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
            state.clips = state.clips.filter(c => c.id !== clipId);
            renderClipsList();
            updateProcessBtn();
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

    function bindWorkspace() {
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

    function showProgress(type) {
        const panel = $('#progress-panel');
        panel.classList.remove('hidden');
        $('#progress-type').textContent = type === 'transcribe' ? '🔊 Распознавание речи' : '🎬 Обработка видео';
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
                    $('#btn-analyze').textContent = '🔍 Запустить анализ речи';
                    if (onDone) onDone(task.result);
                } else if (task.status === 'error') {
                    hideProgress();
                    $('#btn-analyze').disabled = false;
                    $('#btn-analyze').textContent = '🔍 Запустить анализ речи';
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

        // Клик по клипу в publishing = превью
        $('#publishing-list').addEventListener('click', (e) => {
            const card = e.target.closest('.clip-card');
            if (!card) return;
            const clip = state.clips.find(c => c.id === card.dataset.id);
            if (clip && clip.output_path) showPreview(clip);
        });
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
            <div class="flex items-center justify-between">
                <div>
                    <span class="font-medium text-sm">${escHtml(c.title || 'Без названия')}</span>
                    <span class="text-xs text-gray-500 ml-2">${fmtDuration(c.end_time - c.start_time)}</span>
                </div>
                <div class="flex gap-2">${ytBadge}${vkBadge}</div>
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
