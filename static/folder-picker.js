function installFolderPicker(inputId, viewId) {
  const input = $(inputId), view = $(viewId);
  if (!input || !view) return;
  const label = input.closest('label');
  const labelText = I18N.original(label.firstChild.textContent.trim());
  const picker = el('details', undefined, 'folder-picker');
  const summary = el('summary');
  const selected = el('span');
  selected.dataset.noTranslate = '';
  const chevron = el('span', '⌄', 'folder-chevron');
  summary.append(selected, chevron);
  const panel = el('div', undefined, 'folder-panel');
  panel.setAttribute('role', 'group');
  panel.setAttribute('aria-label', labelText + ' auswählen');
  const crumbs = el('div', undefined, 'folder-crumbs');
  const filter = el('input');
  filter.type = 'search';
  filter.placeholder = 'Unterordner filtern …';
  filter.setAttribute('aria-label', labelText + ': Unterordner filtern');
  const status = el('p', '', 'folder-status');
  status.setAttribute('role', 'status');
  const list = el('div', undefined, 'folder-list');
  const footer = el('div', undefined, 'folder-footer');
  const cancel = el('button', 'Abbrechen', 'secondary');
  const choose = el('button', 'Diesen Ordner wählen', 'primary');
  cancel.type = choose.type = 'button';
  footer.append(cancel, choose);
  panel.append(crumbs, filter, status, list, footer);
  picker.append(summary, panel);
  input.type = 'hidden';
  input.after(picker);
  let current = '/', names = [], sequence = 0;

  function positionPanel() {
    if (!picker.open) return;
    const rect = summary.getBoundingClientRect();
    const width = Math.min(Math.max(rect.width, 320), window.innerWidth - 24);
    panel.style.position = 'fixed';
    panel.style.width = width + 'px';
    panel.style.minWidth = '0';
    panel.style.right = 'auto';
    panel.style.left = Math.max(12, Math.min(rect.left, window.innerWidth - width - 12)) + 'px';
    panel.style.maxHeight = 'calc(100dvh - 24px)';
    panel.style.overflowY = 'auto';
    const height = panel.getBoundingClientRect().height;
    panel.style.top = Math.max(12, Math.min(rect.bottom + 7, window.innerHeight - height - 12)) + 'px';
  }

  function updateSummary() {
    selected.textContent = input.value || 'Ordner auswählen …';
    summary.setAttribute('aria-label', labelText + ': ' + (input.value || 'Ordner auswählen'));
  }
  function close() {
    picker.open = false;
    sequence++;
    summary.focus();
  }
  function renderList() {
    list.replaceChildren();
    const query = filter.value.toLocaleLowerCase(I18N.locale);
    const visible = names.filter(name => name.toLocaleLowerCase(I18N.locale).includes(query));
    for (const name of visible.slice(0, 500)) {
      const button = el('button', undefined, 'folder-option');
      button.type = 'button';
      button.append(el('span', '▸', 'folder-symbol'), rawEl('span', name), el('span', '›', 'folder-next'));
      button.setAttribute('aria-label', 'Ordner öffnen: ' + name);
      button.onclick = () => load(current.replace(/\/$/, '') + '/' + name);
      list.append(button);
    }
    if (!visible.length) list.append(el('p', names.length ? 'Keine passenden Unterordner.' : 'Keine Unterordner vorhanden.', 'folder-empty'));
    if (visible.length > 500) list.append(el('p', 'Die ersten 500 Ordner werden angezeigt. Mit dem Filter weiter eingrenzen.', 'folder-empty'));
    positionPanel();
  }
  function renderCrumbs() {
    crumbs.replaceChildren();
    const root = el('button', '/', 'folder-crumb');
    root.type = 'button';
    root.setAttribute('aria-label', 'Wurzelverzeichnis öffnen');
    root.onclick = () => load('/');
    crumbs.append(root);
    let path = '';
    for (const part of current.split('/').filter(Boolean)) {
      path += '/' + part;
      const destination = path;
      const button = rawEl('button', part, 'folder-crumb');
      button.type = 'button';
      button.onclick = () => load(destination);
      crumbs.append(el('span', '›'), button);
    }
  }
  async function load(path) {
    const request = ++sequence;
    choose.disabled = true;
    names = [];
    filter.value = '';
    status.textContent = 'Ordner werden geladen …';
    list.replaceChildren();
    try {
      const data = await api('folders?view=' + encodeURIComponent(view.value) + '&path=' + encodeURIComponent(path));
      if (request !== sequence || !picker.open) return;
      current = data.path;
      names = data.folders;
      filter.value = '';
      renderCrumbs();
      renderList();
      status.textContent = data.errors || data.truncated
        ? 'Die Liste ist möglicherweise unvollständig. ' + data.errors + ' Lesefehler.'
        : (view.value === 'system' ? 'Systemplatte · verdeckte Daten' : 'Host · sichtbare Dateien');
      choose.disabled = false;
      positionPanel();
    } catch (error) {
      if (request !== sequence || !picker.open) return;
      status.textContent = error.message;
      current = path;
      renderCrumbs();
      positionPanel();
    }
  }
  picker.addEventListener('toggle', () => {
    if (picker.open) {
      document.querySelectorAll('.folder-picker[open]').forEach(other => {
        if (other !== picker) other.open = false;
      });
      load(input.value || '/');
      positionPanel();
    }
  });
  filter.oninput = renderList;
  filter.onkeydown = event => {
    if (event.key === 'Enter') event.preventDefault();
  };
  cancel.onclick = close;
  choose.onclick = () => {
    input.value = current;
    input.dispatchEvent(new Event('input', { bubbles: true }));
    updateSummary();
    close();
  };
  input.addEventListener('input', updateSummary);
  view.addEventListener('change', () => {
    input.value = '/';
    updateSummary();
    if (picker.open) load('/');
  });
  picker.addEventListener('keydown', event => {
    if (event.key === 'Escape') {
      event.preventDefault();
      close();
    }
  });
  document.addEventListener('click', event => {
    if (picker.open && !event.composedPath().includes(picker)) {
      picker.open = false;
      sequence++;
    }
  });
  window.addEventListener('resize', positionPanel);
  window.addEventListener('scroll', positionPanel);
  document.addEventListener('languagechange', () => {
    updateSummary();
    if (picker.open) load(current);
  });
  input.form.addEventListener('submit', event => {
    if (!input.value) {
      event.preventDefault();
      event.stopImmediatePropagation();
      picker.open = true;
      summary.focus();
    }
  }, true);
  updateSummary();
}

installFolderPicker('path', 'view');
installFolderPicker('source', 'source-view');
installFolderPicker('target', 'target-view');
for (const tool of tools.filter(tool => tool.folder)) installFolderPicker(tool.id + '-path', tool.id + '-view');

const oldHiddenClick = $('hidden').onclick;
$('hidden').onclick = () => {
  oldHiddenClick();
  $('path').dispatchEvent(new Event('input'));
};

const folderResultBox = resultBox;
resultBox = function(data, type) {
  if (type === 'browse') {
    if (data.path) $('browse-path').value = data.path;
    $('browse-path').dispatchEvent(new Event('input'));
  }
  return folderResultBox(data, type);
};
