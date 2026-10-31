/* Research copilot — the whole interface, in one file, no build step.

   Two rules worth keeping in mind while reading:
   1. Model output and filenames are escaped before they reach the DOM. The
      only markup we add ourselves is the [n] -> superscript transform.
   2. Passage N in the prompt is source N in the response, which is what lets
      a marker in the prose point at a note in the margin. */

const el = (id) => document.getElementById(id);

const ui = {
  counts:       el('counts'),
  banner:       el('banner'),
  fileField:    document.querySelector('.file-field'),
  fileInput:    el('file-input'),
  fileLabel:    el('file-label'),
  uploadNote:   el('upload-note'),
  docList:      el('doc-list'),
  libraryEmpty: el('library-empty'),
  askForm:      el('ask-form'),
  question:     el('question'),
  askButton:    el('ask-button'),
  answer:       el('answer'),
  notes:        el('notes'),
  marginEmpty:  el('margin-empty'),
};

const state = {
  documents: [],
  sources: [],
  ready: false,
  asking: false,
  uploading: false,
};

const reduceMotion = window.matchMedia('(prefers-reduced-motion: reduce)');

/* --- helpers ----------------------------------------------------------- */

function escapeHtml(value) {
  return String(value).replace(/[&<>"']/g, (c) => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;',
  }[c]));
}

function plural(n, one, many) {
  return `${n} ${n === 1 ? one : many}`;
}

async function api(path, options) {
  const response = await fetch(path, options);
  let body = null;
  try {
    body = await response.json();
  } catch {
    body = null;
  }
  if (!response.ok) {
    const message = body && body.error
      ? body.error
      : 'The server could not be reached.';
    throw new Error(message);
  }
  return body;
}

/* --- header and banner -------------------------------------------------- */

function renderCounts(documents, chunks) {
  ui.counts.textContent = documents === 0
    ? ''
    : `${plural(documents, 'paper', 'papers')}, ${plural(chunks, 'passage', 'passages')}`;
}

function showBanner(problems) {
  if (!problems || problems.length === 0) {
    ui.banner.hidden = true;
    ui.banner.textContent = '';
    return;
  }
  ui.banner.hidden = false;
  ui.banner.textContent = problems.join(' ');
}

function setReady(ready) {
  state.ready = ready;
  ui.question.disabled = !ready;
  ui.fileInput.disabled = !ready;
  updateAskButton();
}

function updateAskButton() {
  ui.askButton.disabled = !state.ready || state.asking;
  ui.askButton.textContent = 'Ask';
}

/* --- library ------------------------------------------------------------ */

function renderLibrary() {
  ui.docList.textContent = '';

  if (state.documents.length === 0) {
    ui.libraryEmpty.hidden = false;
    return;
  }
  ui.libraryEmpty.hidden = true;

  for (const doc of state.documents) {
    const item = document.createElement('li');
    item.className = 'doc';

    const title = document.createElement('p');
    title.className = 'doc-title';
    title.textContent = doc.filename;          // textContent, never innerHTML

    const meta = document.createElement('p');
    meta.className = 'doc-meta';
    meta.textContent = doc.noted
      ? 'Already in the library'
      : `${plural(doc.pages, 'page', 'pages')}, ${plural(doc.chunks, 'passage', 'passages')}`;

    const remove = document.createElement('button');
    remove.type = 'button';
    remove.className = 'doc-remove';
    remove.textContent = 'Remove';
    remove.addEventListener('click', () => removeDocument(doc));

    item.append(title, meta, remove);
    ui.docList.append(item);
  }
}

async function refreshLibrary() {
  const documents = await api('/api/documents');
  state.documents = documents;
  renderLibrary();
}

async function refreshCounts() {
  const health = await api('/api/health');
  renderCounts(health.documents, health.chunks);
  return health;
}

async function removeDocument(doc) {
  const ok = window.confirm(`Remove ${doc.filename} from the library?`);
  if (!ok) return;

  try {
    await api(`/api/documents/${encodeURIComponent(doc.doc_id)}`, { method: 'DELETE' });
    state.documents = state.documents.filter((d) => d.doc_id !== doc.doc_id);
    renderLibrary();
    await refreshCounts();
  } catch (error) {
    setUploadNote(error.message, true);
  }
}

/* --- upload ------------------------------------------------------------- */

function setUploadNote(text, isProblem) {
  if (!text) {
    ui.uploadNote.hidden = true;
    ui.uploadNote.textContent = '';
    return;
  }
  ui.uploadNote.hidden = false;
  ui.uploadNote.textContent = text;
  ui.uploadNote.classList.toggle('is-problem', Boolean(isProblem));
}

function setUploading(busy) {
  state.uploading = busy;
  ui.fileField.classList.toggle('is-busy', busy);
  ui.fileInput.disabled = busy || !state.ready;
  // A large paper takes tens of seconds. The label has to say something.
  ui.fileLabel.textContent = busy ? 'Reading…' : 'Add a PDF';
}

async function uploadFile(file) {
  setUploading(true);
  setUploadNote('');

  const form = new FormData();
  form.append('file', file);

  try {
    const result = await api('/api/documents', { method: 'POST', body: form });

    if (result.already_indexed) {
      // Do not add a second row for a paper that is already here.
      const existing = state.documents.find((d) => d.doc_id === result.doc_id);
      if (existing) {
        existing.noted = true;
      } else {
        state.documents.unshift({ ...result, noted: true });
      }
      renderLibrary();
      setUploadNote(`${result.filename} was already indexed, so nothing was re-read.`);
    } else {
      state.documents.unshift({
        doc_id: result.doc_id,
        filename: result.filename,
        pages: result.pages,
        chunks: result.chunks,
      });
      renderLibrary();
      setUploadNote(`Read ${plural(result.pages, 'page', 'pages')} into ${plural(result.chunks, 'passage', 'passages')}.`);
    }

    await refreshCounts();
  } catch (error) {
    setUploadNote(error.message, true);
  } finally {
    setUploading(false);
    ui.fileInput.value = '';
  }
}

/* --- the answer, and its citations -------------------------------------- */

/* Turn [1] and [2][4] into real superscript numerals. The text is escaped
   first, so this is the only markup that reaches the answer column. */
function withCitations(escapedText, sourceCount) {
  return escapedText.replace(/\[(\d+)\]/g, (whole, digits) => {
    const n = Number(digits);
    if (!Number.isInteger(n) || n < 1 || n > sourceCount) return whole;
    return `<sup class="cite"><a href="#note-${n}" data-cite="${n}">${n}</a></sup>`;
  });
}

function renderAnswer(text, sourceCount) {
  ui.answer.textContent = '';

  const blocks = String(text).split(/\n\s*\n/);

  for (const block of blocks) {
    const lines = block.split('\n').map((l) => l.trim()).filter(Boolean);
    if (lines.length === 0) continue;

    const bulleted = lines.every((l) => /^[-*]\s+/.test(l));
    const numbered = lines.every((l) => /^\d+[.)]\s+/.test(l));

    if ((bulleted || numbered) && lines.length > 1) {
      const list = document.createElement(bulleted ? 'ul' : 'ol');
      for (const line of lines) {
        const li = document.createElement('li');
        const content = line.replace(/^([-*]|\d+[.)])\s+/, '');
        li.innerHTML = withCitations(escapeHtml(content), sourceCount);
        list.append(li);
      }
      ui.answer.append(list);
    } else {
      const p = document.createElement('p');
      p.innerHTML = withCitations(escapeHtml(lines.join(' ')), sourceCount);
      ui.answer.append(p);
    }
  }

  wireMarkers();
}

function renderNotes(sources) {
  ui.notes.textContent = '';
  state.sources = sources;

  if (!sources || sources.length === 0) {
    ui.marginEmpty.hidden = false;
    return;
  }
  ui.marginEmpty.hidden = true;

  for (const source of sources) {
    const note = document.createElement('li');
    note.className = 'note';
    note.id = `note-${source.number}`;
    note.tabIndex = 0;
    note.dataset.note = String(source.number);

    const number = document.createElement('span');
    number.className = 'note-number';
    number.textContent = source.number;

    const body = document.createElement('div');

    const name = document.createElement('p');
    name.className = 'note-source';
    name.textContent = source.filename;        // textContent, never innerHTML

    const meta = document.createElement('p');
    meta.className = 'note-meta';
    meta.textContent = `page ${source.page}, match ${source.score.toFixed(2)}`;

    const quote = document.createElement('p');
    quote.className = 'note-quote';
    const trimmed = source.text.length > 260
      ? `${source.text.slice(0, 260).trimEnd()}…`
      : source.text;
    quote.textContent = `“${trimmed}”`;

    body.append(name, meta, quote);
    note.append(number, body);

    // Hovering or focusing a note highlights every marker pointing at it.
    const on  = () => highlightMarkers(source.number, true);
    const off = () => highlightMarkers(source.number, false);
    note.addEventListener('mouseenter', on);
    note.addEventListener('mouseleave', off);
    note.addEventListener('focus', on);
    note.addEventListener('blur', off);
    note.addEventListener('click', () => activateNote(source.number, false));
    note.addEventListener('keydown', (event) => {
      if (event.key === 'Enter' || event.key === ' ') {
        event.preventDefault();
        activateNote(source.number, false);
      }
    });

    ui.notes.append(note);
  }
}

function markers(n) {
  return ui.answer.querySelectorAll(`a[data-cite="${n}"]`);
}

function highlightMarkers(n, on) {
  markers(n).forEach((a) => a.classList.toggle('is-linked', on));
}

function activateNote(n, scroll) {
  ui.notes.querySelectorAll('.note').forEach((note) => {
    note.classList.toggle('is-active', note.dataset.note === String(n));
  });
  ui.answer.querySelectorAll('a[data-cite]').forEach((a) => {
    a.classList.toggle('is-active', a.dataset.cite === String(n));
  });

  if (scroll) {
    const note = el(`note-${n}`);
    if (note) {
      note.scrollIntoView({
        behavior: reduceMotion.matches ? 'auto' : 'smooth',
        block: 'nearest',
      });
    }
  }
}

function wireMarkers() {
  ui.answer.querySelectorAll('a[data-cite]').forEach((link) => {
    const n = Number(link.dataset.cite);
    link.addEventListener('click', (event) => {
      event.preventDefault();
      activateNote(n, true);
    });
    link.addEventListener('mouseenter', () => highlightMarkers(n, true));
    link.addEventListener('mouseleave', () => highlightMarkers(n, false));
  });
}

function showWorking() {
  ui.answer.textContent = '';
  const p = document.createElement('p');
  p.className = 'working';
  p.textContent = 'Reading your papers…';
  ui.answer.append(p);
}

function showProblem(message) {
  ui.answer.textContent = '';
  const p = document.createElement('p');
  p.className = 'problem';
  p.textContent = message;                     // plain text, not a red alert box
  ui.answer.append(p);
}

/* --- ask ---------------------------------------------------------------- */

async function askQuestion() {
  const question = ui.question.value.trim();
  if (!question || state.asking) return;

  state.asking = true;
  updateAskButton();
  showWorking();
  renderNotes([]);

  try {
    const result = await api('/api/ask', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ question }),
    });
    renderNotes(result.sources);
    renderAnswer(result.answer, result.sources.length);
  } catch (error) {
    showProblem(error.message);
    renderNotes([]);
  } finally {
    state.asking = false;
    updateAskButton();
  }
}

/* --- wiring ------------------------------------------------------------- */

ui.askForm.addEventListener('submit', (event) => {
  event.preventDefault();
  askQuestion();
});

// Enter sends the question; Shift+Enter starts a new line.
ui.question.addEventListener('keydown', (event) => {
  if (event.key === 'Enter' && !event.shiftKey) {
    event.preventDefault();
    askQuestion();
  }
});

ui.fileInput.addEventListener('change', () => {
  const file = ui.fileInput.files && ui.fileInput.files[0];
  if (file) uploadFile(file);
});

/* --- start -------------------------------------------------------------- */

async function start() {
  setReady(false);

  const [health, documents] = await Promise.allSettled([
    api('/api/health'),
    api('/api/documents'),
  ]);

  if (health.status === 'fulfilled') {
    renderCounts(health.value.documents, health.value.chunks);
    showBanner(health.value.problems);
    setReady(health.value.ok);
  } else {
    showBanner([health.reason.message]);
    setReady(false);
  }

  if (documents.status === 'fulfilled') {
    state.documents = documents.value;
  }
  renderLibrary();
  renderNotes([]);
}

start();
