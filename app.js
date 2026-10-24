'use strict';

const $ = id => document.getElementById(id);
const els = {
  lessonSelect: $('lessonSelect'), openLessonBtn: $('openLessonBtn'), lessonFile: $('lessonFile'),
  ytInput: $('ytInput'), ytLoadBtn: $('ytLoadBtn'), localBtn: $('localBtn'), localFile: $('localFile'),
  lessonTitle: $('lessonTitle'), ytWrap: $('ytWrap'), video: $('localVideo'), placeholder: $('placeholder'),
  subEn: $('subEn'), subZh: $('subZh'),
  prevLineBtn: $('prevLineBtn'), playBtn: $('playBtn'), nextLineBtn: $('nextLineBtn'),
  loopBtn: $('loopBtn'), autoPauseBtn: $('autoPauseBtn'), rateSelect: $('rateSelect'),
  card: $('card'), cardTag: $('cardTag'), cardCounter: $('cardCounter'), cardTitle: $('cardTitle'),
  cardMeaning: $('cardMeaning'), cardExplain: $('cardExplain'), cardExample: $('cardExample'),
  cardExEn: $('cardExEn'), cardExZh: $('cardExZh'), prevNoteBtn: $('prevNoteBtn'), nextNoteBtn: $('nextNoteBtn'),
  lineList: $('lineList'), toast: $('toast'),
};

// 重點類型：type -> [中文標籤, 英文標籤]
const TAGS = {
  chunk: ['詞塊', 'CHUNK'],
  pattern: ['句型', 'PATTERN'],
  grammar: ['文法', 'GRAMMAR'],
  word: ['單字', 'WORD'],
};

const state = {
  lesson: null,
  lines: [],
  notes: [],        // 全課程的重點，攤平成一個陣列
  lineIdx: -1,
  noteIdx: -1,
  player: null,
  loop: false,
  loopLine: -1,
  autoPause: false,
  pausedAt: -1,     // 逐句暫停：已經停過的句子
  seekGuardUntil: 0,
  rate: 1,
};

const isFileProtocol = location.protocol === 'file:';

/* ---------- 小工具 ---------- */

function esc(s) {
  return String(s ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
}
const pad2 = n => String(n).padStart(2, '0');
function fmtTime(t) {
  t = Math.max(0, Math.floor(t || 0));
  return `${Math.floor(t / 60)}:${pad2(t % 60)}`;
}

let toastTimer;
function toast(msg, ms = 4000) {
  els.toast.textContent = msg;
  els.toast.hidden = false;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => { els.toast.hidden = true; }, ms);
}

// 在 text 中把每個重點的 key 字串包成 <mark>
function highlight(text, notes, key) {
  const lower = String(text ?? '').toLowerCase();
  const ranges = [];
  for (const n of notes) {
    const m = n[key];
    if (!m) continue;
    const i = lower.indexOf(m.toLowerCase());
    if (i >= 0) ranges.push({ s: i, e: i + m.length, n });
  }
  ranges.sort((a, b) => a.s - b.s);
  let out = '', pos = 0;
  for (const r of ranges) {
    if (r.s < pos) continue;
    out += esc(text.slice(pos, r.s));
    out += `<mark class="hl hl-${esc(r.n.type)}" data-note="${r.n.gi}">${esc(text.slice(r.s, r.e))}</mark>`;
    pos = r.e;
  }
  return out + esc(String(text ?? '').slice(pos));
}

function parseYouTubeId(input) {
  input = (input || '').trim();
  if (/^[\w-]{11}$/.test(input)) return input;
  const m = input.match(/(?:youtu\.be\/|[?&]v=|\/embed\/|\/shorts\/|\/live\/)([\w-]{11})/);
  return m ? m[1] : null;
}

/* ---------- 播放器（YouTube / 本機 共用同一組介面） ---------- */

function showStage(which) {
  els.placeholder.hidden = which !== 'none';
  els.ytWrap.hidden = which !== 'yt';
  els.video.hidden = which !== 'local';
}

function destroyPlayer() {
  if (state.player) state.player.destroy();
  state.player = null;
}

function makeLocalPlayer(src) {
  const v = els.video;
  v.src = src;
  v.playbackRate = state.rate;
  showStage('local');
  return {
    getTime: () => v.currentTime,
    seek: t => { v.currentTime = t; },
    play: () => v.play().catch(() => {}),
    pause: () => v.pause(),
    isPaused: () => v.paused,
    setRate: r => { v.playbackRate = r; },
    destroy: () => { v.pause(); v.removeAttribute('src'); v.load(); },
  };
}

let ytApiPromise = null;
function loadYTApi() {
  if (window.YT && window.YT.Player) return Promise.resolve();
  if (!ytApiPromise) {
    ytApiPromise = new Promise((resolve, reject) => {
      window.onYouTubeIframeAPIReady = resolve;
      const s = document.createElement('script');
      s.src = 'https://www.youtube.com/iframe_api';
      s.onerror = () => { ytApiPromise = null; reject(new Error('無法載入 YouTube API，請檢查網路')); };
      document.head.appendChild(s);
    });
  }
  return ytApiPromise;
}

const YT_ERRORS = {
  2: '影片 ID 不正確',
  5: '瀏覽器無法播放此影片',
  100: '影片不存在或已設為私人',
  101: '影片擁有者不允許嵌入播放',
  150: '影片擁有者不允許嵌入播放',
  153: 'YouTube 拒絕播放：請用 start.bat 開啟本系統（不要直接雙擊 index.html）',
};

async function makeYouTubePlayer(videoId) {
  await loadYTApi();
  els.ytWrap.innerHTML = '';
  const host = document.createElement('div');
  els.ytWrap.appendChild(host);
  showStage('yt');
  const playerVars = { playsinline: 1, rel: 0, modestbranding: 1, cc_load_policy: 0 };
  if (!isFileProtocol) playerVars.origin = location.origin;
  return new Promise(resolve => {
    const p = new YT.Player(host, {
      videoId,
      width: '100%',
      height: '100%',
      playerVars,
      events: {
        onReady: () => { p.setPlaybackRate(state.rate); resolve(adapter); },
        // 關掉 YouTube 內建 CC，避免和下方字幕重複
        onStateChange: e => { if (e.data === YT.PlayerState.PLAYING) p.unloadModule?.('captions'); },
        onError: e => toast('YouTube 錯誤：' + (YT_ERRORS[e.data] || e.data), 8000),
      },
    });
    const adapter = {
      getTime: () => (p.getCurrentTime ? p.getCurrentTime() : 0),
      seek: t => p.seekTo(t, true),
      play: () => p.playVideo(),
      pause: () => p.pauseVideo(),
      isPaused: () => {
        const s = p.getPlayerState ? p.getPlayerState() : -1;
        return s !== YT.PlayerState.PLAYING && s !== YT.PlayerState.BUFFERING;
      },
      setRate: r => p.setPlaybackRate(r),
      destroy: () => { p.destroy(); els.ytWrap.innerHTML = ''; },
    };
  });
}

async function loadYouTube(videoId) {
  if (isFileProtocol) toast('提醒：直接開啟 index.html 時 YouTube 可能無法播放，建議改用 start.bat', 6000);
  destroyPlayer();
  try {
    state.player = await makeYouTubePlayer(videoId);
  } catch (err) {
    showStage('none');
    toast(err.message, 6000);
  }
}

function loadLocal(src) {
  destroyPlayer();
  state.player = makeLocalPlayer(src);
}

/* ---------- 課程 ---------- */

function setLesson(lesson) {
  if (!lesson || !Array.isArray(lesson.lines)) {
    toast('課程檔格式錯誤：需要 "lines" 陣列');
    return;
  }
  state.lesson = lesson;
  state.lines = lesson.lines.slice().sort((a, b) => a.start - b.start);
  state.notes = [];
  state.lines.forEach((ln, li) => {
    ln._notes = (ln.notes || []).map(n => {
      const note = { ...n, li, gi: state.notes.length };
      state.notes.push(note);
      return note;
    });
  });
  state.lineIdx = -1;
  state.loopLine = -1;
  state.pausedAt = -1;
  state.noteIdx = state.notes.length ? 0 : -1;

  els.lessonTitle.textContent = lesson.title || '未命名課程';
  renderLineList();
  renderSubtitle();
  renderCard(false);

  const src = lesson.source || {};
  if (src.type === 'youtube' && src.id) {
    els.ytInput.value = src.id;
    loadYouTube(parseYouTubeId(src.id) || src.id);
  } else if (src.type === 'local' && src.file) {
    loadLocal(src.file);
    els.video.onerror = () => toast(`找不到影片檔「${src.file}」，請按「本機影片」手動選擇`, 7000);
  }
}

async function loadLessonIndex() {
  if (isFileProtocol) {
    els.lessonSelect.hidden = true;
    return;
  }
  try {
    const res = await fetch('lessons/index.json', { cache: 'no-store' });
    const list = await res.json();
    els.lessonSelect.innerHTML = list.map(it =>
      `<option value="${esc(it.file)}">${esc(it.title || it.file)}</option>`).join('');
    if (list.length) await loadLessonUrl('lessons/' + list[0].file);
  } catch {
    els.lessonSelect.hidden = true;
  }
}

async function loadLessonUrl(url) {
  try {
    const res = await fetch(url, { cache: 'no-store' });
    setLesson(await res.json());
  } catch (err) {
    toast('無法讀取課程：' + err.message);
  }
}

/* ---------- 畫面 ---------- */

function renderSubtitle() {
  const ln = state.lines[state.lineIdx];
  els.subEn.innerHTML = ln ? highlight(ln.en, ln._notes, 'match') : '';
  els.subZh.innerHTML = ln ? highlight(ln.zh, ln._notes, 'zhMatch') : '';
}

function renderLineList() {
  els.lineList.innerHTML = state.lines.map((ln, i) => `
    <li data-line="${i}">
      <span class="time">${fmtTime(ln.start)}</span>
      <span class="en">${highlight(ln.en, ln._notes, 'match')}</span>
      <span class="zh">${esc(ln.zh)}</span>
    </li>`).join('');
}

function markActiveLine() {
  const box = els.lineList;
  box.querySelector('li.active')?.classList.remove('active');
  const li = box.children[state.lineIdx];
  if (!li) return;
  li.classList.add('active');
  if (li.offsetTop < box.scrollTop || li.offsetTop + li.offsetHeight > box.scrollTop + box.clientHeight) {
    box.scrollTop = li.offsetTop - box.clientHeight / 3;
  }
}

function renderCard(flash = true) {
  const n = state.notes[state.noteIdx];
  if (!n) { els.card.hidden = true; return; }
  els.card.hidden = false;
  const [zh, en] = TAGS[n.type] || [n.type || '重點', ''];
  els.card.className = 'card ' + (n.type || '');
  els.cardTag.textContent = `${zh} ${en}`.trim();
  els.cardCounter.textContent = `${pad2(n.gi + 1)} / ${pad2(state.notes.length)}`;
  els.cardTitle.textContent = n.title || n.match || '';
  els.cardMeaning.textContent = n.meaning || '';
  els.cardExplain.textContent = n.explain || '';
  els.cardExplain.hidden = !n.explain;
  const ex = n.example || {};
  els.cardExEn.textContent = ex.en || '';
  els.cardExZh.textContent = ex.zh || '';
  els.cardExample.hidden = !ex.en && !ex.zh;
  if (flash) {
    els.card.classList.remove('flash');
    void els.card.offsetWidth;
    els.card.classList.add('flash');
  }
}

function setLineIdx(i) {
  if (i === state.lineIdx) return;
  state.lineIdx = i;
  renderSubtitle();
  markActiveLine();
  const ln = state.lines[i];
  if (ln && ln._notes.length && state.noteIdx !== ln._notes[0].gi) {
    state.noteIdx = ln._notes[0].gi;
    renderCard();
  }
}

/* ---------- 時間同步 ---------- */

// 目前時間所在的句子；句子之間的短空檔沿用上一句，長空檔回傳 -1
function findLine(t) {
  let best = -1;
  for (let i = 0; i < state.lines.length; i++) {
    if (state.lines[i].start <= t + 0.001) best = i;
    else break;
  }
  if (best >= 0 && t > state.lines[best].end + 1.5) return -1;
  return best;
}

function tick() {
  const p = state.player;
  if (!p) return;
  const t = p.getTime();
  const paused = p.isPaused();
  els.playBtn.textContent = paused ? '▶ 播放' : '⏸ 暫停';
  if (performance.now() < state.seekGuardUntil) return;

  const idx = findLine(t);

  if (state.loop) {
    const ln = state.lines[state.loopLine];
    if (ln) {
      if (idx !== state.loopLine && idx >= 0 && (t < ln.start || t > ln.end + 1)) {
        state.loopLine = idx;   // 使用者自行拖到別句，就循環那一句
      } else if (!paused && t >= ln.end) {
        seekTo(ln.start);
        return;
      }
    }
  } else if (state.autoPause && !paused) {
    const cur = state.lineIdx;
    const ln = state.lines[cur];
    if (ln && state.pausedAt !== cur && t >= ln.end - 0.08 && t < ln.end + 1) {
      p.pause();
      p.seek(Math.max(ln.start, ln.end - 0.1));
      state.pausedAt = cur;
      state.seekGuardUntil = performance.now() + 300;
      return;
    }
  }

  setLineIdx(idx);
}
setInterval(tick, 100);

function seekTo(t) {
  state.player?.seek(t);
  state.seekGuardUntil = performance.now() + 400;
}

function goLine(i, play = true) {
  if (!state.lines.length) return;
  i = Math.max(0, Math.min(state.lines.length - 1, i));
  state.pausedAt = -1;
  if (state.loop) state.loopLine = i;
  setLineIdx(i);
  if (!state.player) { toast('請先載入影片'); return; }
  seekTo(state.lines[i].start + 0.01);
  if (play) state.player.play();
}

function stepLine(dir) {
  const cur = state.lineIdx;
  if (dir < 0 && cur >= 0 && state.player && state.player.getTime() - state.lines[cur].start > 1.5) {
    goLine(cur);   // 先回到本句開頭，再按一次才到上一句
  } else {
    goLine(cur < 0 ? (dir > 0 ? findNextLine() : 0) : cur + dir);
  }
}

function findNextLine() {
  const t = state.player ? state.player.getTime() : 0;
  const i = state.lines.findIndex(ln => ln.start > t);
  return i < 0 ? state.lines.length - 1 : i;
}

function goNote(gi) {
  const n = state.notes[gi];
  if (!n) return;
  state.noteIdx = gi;
  renderCard();
  if (n.li !== state.lineIdx) goLine(n.li, false);
}

function togglePlay() {
  const p = state.player;
  if (!p) { toast('請先載入影片'); return; }
  p.isPaused() ? p.play() : p.pause();
}

function setLoop(on) {
  state.loop = on;
  state.loopLine = state.lineIdx;
  els.loopBtn.classList.toggle('on', on);
}

function setAutoPause(on) {
  state.autoPause = on;
  state.pausedAt = -1;
  els.autoPauseBtn.classList.toggle('on', on);
}

/* ---------- 事件 ---------- */

els.ytLoadBtn.addEventListener('click', () => {
  const id = parseYouTubeId(els.ytInput.value);
  if (!id) { toast('看不懂這個 YouTube 網址，請貼完整網址或 11 碼影片 ID'); return; }
  loadYouTube(id);
});
els.ytInput.addEventListener('keydown', e => { if (e.key === 'Enter') els.ytLoadBtn.click(); });

els.localBtn.addEventListener('click', () => els.localFile.click());
els.localFile.addEventListener('change', () => {
  const f = els.localFile.files[0];
  if (!f) return;
  els.video.onerror = null;
  loadLocal(URL.createObjectURL(f));
  toast('已載入本機影片：' + f.name, 2500);
  els.localFile.value = '';
});

els.openLessonBtn.addEventListener('click', () => els.lessonFile.click());
els.lessonFile.addEventListener('change', async () => {
  const f = els.lessonFile.files[0];
  if (!f) return;
  try {
    setLesson(JSON.parse(await f.text()));
  } catch (err) {
    toast('課程 JSON 解析失敗：' + err.message, 6000);
  }
  els.lessonFile.value = '';
});
els.lessonSelect.addEventListener('change', () => loadLessonUrl('lessons/' + els.lessonSelect.value));

els.playBtn.addEventListener('click', togglePlay);
els.prevLineBtn.addEventListener('click', () => stepLine(-1));
els.nextLineBtn.addEventListener('click', () => stepLine(1));
els.loopBtn.addEventListener('click', () => setLoop(!state.loop));
els.autoPauseBtn.addEventListener('click', () => setAutoPause(!state.autoPause));
els.rateSelect.addEventListener('change', () => {
  state.rate = parseFloat(els.rateSelect.value);
  state.player?.setRate(state.rate);
});

els.prevNoteBtn.addEventListener('click', () => goNote(state.noteIdx - 1));
els.nextNoteBtn.addEventListener('click', () => goNote(state.noteIdx + 1));

// 點字幕或逐字稿中的高亮片語 -> 顯示對應卡片
document.addEventListener('click', e => {
  const mark = e.target.closest('mark.hl');
  if (mark && !mark.closest('#lineList')) {
    state.noteIdx = +mark.dataset.note;
    renderCard();
  }
});
els.lineList.addEventListener('click', e => {
  const li = e.target.closest('li[data-line]');
  if (li) goLine(+li.dataset.line);
});

document.addEventListener('keydown', e => {
  if (e.target.closest('input, select, textarea') || e.ctrlKey || e.altKey || e.metaKey) return;
  switch (e.key) {
    case ' ': e.preventDefault(); togglePlay(); break;
    case 'ArrowLeft': e.preventDefault(); stepLine(-1); break;
    case 'ArrowRight': e.preventDefault(); stepLine(1); break;
    case 'r': case 'R': setLoop(!state.loop); break;
    case 'p': case 'P': setAutoPause(!state.autoPause); break;
  }
});

showStage('none');
loadLessonIndex();
