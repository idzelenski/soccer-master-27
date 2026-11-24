const app = document.getElementById('app');
const toastRoot = document.getElementById('toast-root');
const state = { manager: null, save: null, summary: null, clubs: [], leagues: [], tab: 'home', squad: [], fixtures: [], tactics: null, search: '', league: '', clubTotal: 0, clubOffset: 0, calendarMonth: null, selectedCalendarDate: null, selectedTournamentId: null, tacticSlots: [], tacticBench: [], selectedTacticSlot: null, selectedTacticPlayer: null, tacticReserve: [], tacticSettings: {}, tacticFormation: '4-3-3', tabCache: {}, tabLoads: {}, cacheEpoch: 0, preloadStarted: false, creatingSave: false };

const esc = (value) => String(value ?? '').replace(/[&<>"']/g, (ch) => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[ch]));
const initials = (value) => String(value || 'SM').split(/[\s-]+/).slice(0,2).map((part) => part[0] || '').join('').toUpperCase();
function flagAssetUrl(code) {
  const value = String(code || '').toLowerCase();
  const safe = /^[a-z]{2}$|^gb-(?:eng|sct|wls|nir)$/.test(value) ? value : '';
  return safe ? 'https://flagcdn.com/w80/' + safe + '.png' : '';
}
function flagImage(code) {
  const src = flagAssetUrl(code);
  return src
    ? '<img class="national-flag" src="' + src + '" alt="Флаг ' + esc(String(code).toUpperCase()) + '" loading="lazy" decoding="async" referrerpolicy="no-referrer" onerror="this.hidden=true">'
    : '';
}
const TRAINING_POSITIONS = {
  GK:[], RB:['LB','RWB'], LB:['RB','LWB'], CB:['CDM'], RWB:['RB','RM'], LWB:['LB','LM'],
  CDM:['CM','CB'], CM:['CDM','CAM'], CAM:['CM','CF'], RM:['RW','CM'], LM:['LW','CM'],
  RW:['RM','ST'], LW:['LM','ST'], ST:['CF','LW'], CF:['ST','CAM']
};
const money = (value) => {
  const n = Number(value || 0);
  if (!n) return '—';
  if (n >= 1_000_000_000) return `€${(n / 1_000_000_000).toFixed(1)} млрд`;
  if (n >= 1_000_000) return `€${(n / 1_000_000).toFixed(1)} млн`;
  if (n >= 1000) return `€${Math.round(n / 1000)} тыс.`;
  return `€${n}`;
};
const dateLabel = (value) => value ? new Date(value).toLocaleDateString('ru-RU',{day:'numeric',month:'short',year:'numeric'}) : '—';
const toast = (message, error = false) => {
  const node = document.createElement('div'); node.className = `toast${error ? ' error' : ''}`; node.textContent = message;
  toastRoot.appendChild(node); setTimeout(() => node.remove(), 3600);
};
async function api(url, options = {}) {
  let response;
  try {
    response = await fetch(url, { credentials: 'same-origin', headers: {'Content-Type':'application/json', ...(options.headers || {})}, ...options });
  } catch (_) {
    throw new Error('Не удалось связаться с сервером. Проверь подключение и повтори попытку.');
  }
  let data = {};
  try { data = await response.json(); } catch (_) { /* empty response */ }
  if (!response.ok) {
    const safeDetail = typeof data.detail === 'string' && !/^internal server error$/i.test(data.detail)
      ? data.detail
      : '';
    const message = response.status >= 500
      ? (safeDetail || `Ошибка сервера (${response.status}). Результат действия не подтверждён. Обнови экран перед повтором.`)
      : (data.detail || `Не удалось выполнить запрос (${response.status}).`);
    throw new Error(message);
  }
  if ((options.method || 'GET').toUpperCase() !== 'GET') {
    state.cacheEpoch += 1;
    state.tabCache = {};
    state.tabLoads = {};
    state.preloadStarted = false;
  }
  return data;
}
function loadTabData(key, loader) {
  if (Object.prototype.hasOwnProperty.call(state.tabCache, key)) {
    return Promise.resolve(state.tabCache[key]);
  }
  if (state.tabLoads[key]) return state.tabLoads[key];
  const epoch = state.cacheEpoch;
  const pending = Promise.resolve().then(loader).then(data => {
    if (epoch === state.cacheEpoch) state.tabCache[key] = data;
    return data;
  }).finally(() => {
    if (state.tabLoads[key] === pending) delete state.tabLoads[key];
  });
  state.tabLoads[key] = pending;
  return pending;
}
async function preloadCareerTabs() {
  if (state.preloadStarted || !state.save) return;
  state.preloadStarted = true;
  const tasks = [
    loadTabData('squad', () => api('/api/squad')).then(players => { state.squad = players; }),
    loadTabData('tactics', async () => {
      const [players, tactics] = await Promise.all([
        loadTabData('squad', () => api('/api/squad')),
        api('/api/tactics')
      ]);
      return {players, tactics};
    }).then(data => { state.tactics = data.tactics; }),
    loadTabData('fixtures', () => api('/api/fixtures?limit=400')).then(rows => { state.fixtures = rows; }),
    loadTabData('tournaments', () => api('/api/tournaments'))
  ];
  const results = await Promise.allSettled(tasks);
  if (results.some(result => result.status === 'rejected')) state.preloadStarted = false;
}
function flagIcon(code, label = 'Флаг страны') {
  const src = flagAssetUrl(code);
  return src
    ? '<img class="player-flag" src="' + src + '" alt="' + esc(label) + '" loading="lazy" decoding="async" referrerpolicy="no-referrer" onerror="this.hidden=true">'
    : '';
}
function renderToneCrystals(value) {
  const score = Math.max(0, Math.min(100, Number(value ?? 85)));
  const level = Math.max(0, Math.min(4, Math.ceil(score / 20) - 1));
  const colors = ['#ff6c79','#ffad55','#efd15c','#83d477','#58c9d8'];
  const color = colors[level];
  return '<span class="tone-crystals" role="img" aria-label="Тонус ' + score + ' из 100">' +
    '<svg viewBox="0 0 16 19" aria-hidden="true">' +
    '<path d="M8 1 14 5 12 14 8 18 4 14 2 5Z" fill="' + color + '" stroke="' + color + '" stroke-width="1"/>' +
    '<path d="M8 1 8 18M2 5 14 5M4 14 12 14" fill="none" stroke="#102117" stroke-width=".8" opacity=".65"/>' +
    '</svg></span>';
}
function renderMoodFaces(value) {
  const score = Math.max(0, Math.min(100, Number(value ?? 70)));
  const level = Math.max(0, Math.min(4, Math.ceil(score / 20) - 1));
  const colors = ['#f06b72','#f29a52','#e8c95a','#8dce72','#55c8a1'];
  const mouths = [
    'M5.5 10.8 Q8 8.4 10.5 10.8',
    'M5.5 10.5 Q8 9.6 10.5 10.5',
    'M5.5 10.5 L10.5 10.5',
    'M5.5 9.8 Q8 12.3 10.5 9.8',
    'M5 9.2 Q8 13.5 11 9.2'
  ];
  const color = colors[level];
  return '<span class="mood-faces" role="img" aria-label="Настрой ' + score + ' из 100">' +
    '<svg viewBox="0 0 16 16" aria-hidden="true">' +
    '<circle cx="8" cy="8" r="7" fill="' + color + '" stroke="' + color + '" stroke-width=".8"/>' +
    '<path d="M5.4 6.2v.2M10.6 6.2v.2' + mouths[level] + '" fill="none" stroke="#17231d" stroke-width="1.25" stroke-linecap="round"/>' +
    '</svg></span>';
}
const POSITION_TRAINING_OPTIONS = {
  GK: [], RB: ['LB','RWB'], LB: ['RB','LWB'], CB: ['CDM'],
  RWB: ['RB','RM'], LWB: ['LB','LM'], CDM: ['CM','CB'], CM: ['CDM','CAM'],
  CAM: ['CM','CF'], RM: ['RW','CM'], LM: ['LW','CM'], RW: ['RM','ST'],
  LW: ['LM','ST'], ST: ['CF','LW'], CF: ['ST','CAM']
};
function marketValueSourceLabel(player) {
  if (player.market_value_source === 'SofaScore') return 'SofaScore';
  if (player.market_value_source === 'Transfermarkt') return 'Transfermarkt';
  if (player.market_value_source === 'SM27 estimate') return 'Оценка SM27';
  return 'Источник не указан';
}
function crest(name, logo, size = 'normal') {
  const fallback = esc(initials(name));
  const safeLogo = typeof logo === 'string' && /^https:\/\//i.test(logo) ? logo : '';
  return `<span class="crest ${size === 'large' ? 'crest-large' : ''}" role="img" aria-label="Эмблема ${esc(name)}"><span class="crest-fallback">${fallback}</span>${safeLogo ? `<img src="${esc(safeLogo)}" alt="" loading="lazy" decoding="async" referrerpolicy="no-referrer" onerror="this.hidden=true;this.previousElementSibling.hidden=false">` : ''}</span>`;
}
function pageHead(kicker, title, description, action = '') {
  return `<div class="page-head"><div><div class="eyebrow">${esc(kicker)}</div><h1>${esc(title)}</h1><p>${esc(description || '')}</p></div>${action}</div>`;
}
function renderAuth(mode = 'login', error = '') {
  const register = mode === 'register';
  app.innerHTML = `
    <div class="auth-wrap">
      <section class="auth-hero">
        <div class="auth-brand"><div class="brand-icon">SM</div><div><strong>SOCCER MASTER 27</strong><span>BUILD YOUR LEGACY</span></div></div>
        <div class="auth-copy"><div class="eyebrow">Сезон 2026 / 27</div><h1>Твоя команда.<br><em>Твои правила.</em></h1><p>Строй клуб, управляй составом, меняй тактику и веди команду к вершине. Каждое решение меняет твою историю.</p></div>
        <div class="auth-facts"><div><b>до 750</b>клубов в мире SM27</div><div><b>2026/27</b>игровой сезон</div><div><b>∞</b>новые карьеры</div></div>
      </section>
      <section class="auth-card-wrap"><div class="auth-card">
        <div class="eyebrow">Добро пожаловать в SM27</div><h2>${register ? 'Создать аккаунт' : 'С возвращением'}</h2>
        <p class="subtext">${register ? 'Создай менеджера и выбери клуб, который приведёшь к славе.' : 'Войди в аккаунт, чтобы продолжить свою карьеру.'}</p>
        <div class="auth-tabs"><button data-auth-mode="login" class="${!register?'active':''}">Войти</button><button data-auth-mode="register" class="${register?'active':''}">Регистрация</button></div>
        <form id="auth-form">
          ${register ? `<div class="form-field"><label for="auth-name">ИМЯ МЕНЕДЖЕРА</label><input id="auth-name" name="name" placeholder="Например, Иван" minlength="2" maxlength="48" required></div>` : ''}
          <div class="form-field"><label for="auth-email">EMAIL</label><input id="auth-email" name="email" type="email" placeholder="name@example.com" autocomplete="email" required></div>
          <div class="form-field"><label for="auth-password">ПАРОЛЬ</label><input id="auth-password" name="password" type="password" placeholder="Минимум 8 символов" minlength="8" autocomplete="${register?'new-password':'current-password'}" required></div>
          <div class="form-error" id="auth-error">${esc(error)}</div>
          <button class="btn-primary block" type="submit">${register ? 'Создать аккаунт →' : 'Войти в игру →'}</button>
        </form>
        <div class="form-foot">Продолжая, ты создаёшь игровое сохранение в Soccer Master 27.<br>Не используй пароль от других сервисов.</div>
      </div></section>
    </div>`;
  document.querySelectorAll('[data-auth-mode]').forEach((button) => button.addEventListener('click', () => renderAuth(button.dataset.authMode)));
  document.getElementById('auth-form').addEventListener('submit', async (event) => {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    const body = Object.fromEntries(form.entries());
    const target = register ? '/api/auth/register' : '/api/auth/login';
    const submit = event.currentTarget.querySelector('button[type="submit"]'); submit.disabled = true; submit.textContent = 'Подключаемся…';
    try {
      await api(target, {method:'POST', body: JSON.stringify(body)});
      await start();
    } catch (err) {
      const errorNode = document.getElementById('auth-error'); if (errorNode) errorNode.textContent = err.message;
      submit.disabled = false; submit.textContent = register ? 'Создать аккаунт →' : 'Войти в игру →';
    }
  });
}
async function loadClubPage() {
  const [summary, leagues, clubsPage] = await Promise.all([
    api('/api/catalog/summary'), api('/api/catalog/leagues'), api('/api/catalog/clubs?limit=200&sort=alphabetical')
  ]);
  state.summary = summary; state.leagues = leagues; state.clubs = clubsPage.items;
  state.clubTotal = clubsPage.total; state.clubOffset = clubsPage.items.length;
  renderClubSelection();
}
function renderClubSelection() {
  const clubCards = state.clubs.map((club) => `
    <button class="club-card" data-club="${esc(club.source_id)}">
      ${crest(club.club_name, club.logo_url)}
      <span><b>${esc(club.club_name)} <i class="club-star-rating">${club.fifa_stars ? Number(club.fifa_stars).toFixed(1) + ' ★' : ''}</i></b><small>${esc(club.country || '—')} · ${esc(club.league_name || 'Лига')}</small><em>${club.has_squad ? `Состав: ${club.squad_count} игроков` : 'Игровой состав будет сформирован'}</em></span>
    </button>`).join('');
  const leagueOptions = ['<option value="">Все лиги</option>', ...state.leagues.map((league) => `<option value="${esc(league.code)}" ${state.league===league.code?'selected':''}>${esc(league.name)} · ${league.clubs}</option>`)].join('');
  app.innerHTML = `<main class="onboard">
    <div class="auth-brand"><div class="brand-icon">SM</div><div><strong>SOCCER MASTER 27</strong><span>BUILD YOUR LEGACY</span></div><div style="margin-left:auto"><button id="logout" class="btn-quiet">Выйти</button></div></div>
    <div class="onboard-head"><div class="eyebrow">Твоя история начинается здесь</div><h1>Выбери свой <span style="color:var(--green)">клуб</span></h1><p>Управляй командой, строй тактику и создавай собственную футбольную династию.</p></div>
    <div class="filters"><input class="search-input" id="club-search" placeholder="Поиск клуба, страны или лиги…" value="${esc(state.search)}"><select class="select-input" id="league-filter">${leagueOptions}</select></div>
    <div class="club-grid" id="club-grid">${clubCards || '<div class="empty-state"><strong>Каталог ещё не загружен</strong>Запусти команду импорта, указанную в README.md</div>'}</div>
    ${state.clubTotal > state.clubs.length ? `<div style="display:flex;justify-content:center;margin:18px 0"><button class="btn-secondary" id="load-more-clubs">Показать ещё клубы (${state.clubTotal-state.clubs.length})</button></div>` : ''}
    <div class="catalog-note"><span>ⓘ</span><span>Данные текущего сезона взяты из OpenFootballBase (релиз 21.11.2026). У части клубов составы подтверждены источником, у остальных используется явно помеченный игровой состав.</span></div>
  </main>`;
  document.getElementById('logout').addEventListener('click', logout);
  document.querySelectorAll('[data-club]').forEach((button) => button.addEventListener('click', () => selectClub(button.dataset.club)));
  document.getElementById('load-more-clubs')?.addEventListener('click', loadMoreClubs);
  document.getElementById('club-search').addEventListener('input', debounce(async (event) => { state.search = event.target.value; await refreshClubList(); }, 230));
  document.getElementById('league-filter').addEventListener('change', async (event) => { state.league = event.target.value; await refreshClubList(); });
}
let searchTimer;
function debounce(fn, delay) { return (...args) => { clearTimeout(searchTimer); searchTimer = setTimeout(() => fn(...args), delay); }; }
async function refreshClubList() {
  const query = new URLSearchParams({limit:'200',q:state.search,league:state.league,sort:'alphabetical'});
  try {
    query.set('offset','0');
    const data = await api(`/api/catalog/clubs?${query.toString()}`); state.clubs = data.items; state.clubTotal = data.total; state.clubOffset = data.items.length;
    const node = document.getElementById('club-grid'); if (!node) return;
    node.innerHTML = state.clubs.map((club) => `<button class="club-card" data-club="${esc(club.source_id)}">${crest(club.club_name,club.logo_url)}<span><b>${esc(club.club_name)} <i class="club-star-rating">${club.fifa_stars ? Number(club.fifa_stars).toFixed(1) + ' ★' : ''}</i></b><small>${esc(club.country||'—')} · ${esc(club.league_name||'Лига')}</small><em>${club.has_squad?`Состав: ${club.squad_count} игроков`:'Игровой состав будет сформирован'}</em></span></button>`).join('') || '<div class="empty-state">По запросу ничего не найдено.</div>';
    node.querySelectorAll('[data-club]').forEach((button) => button.addEventListener('click', () => selectClub(button.dataset.club)));
    const oldLoadMore = document.getElementById('load-more-clubs');
    if (oldLoadMore) oldLoadMore.parentElement.remove();
    if (state.clubOffset < state.clubTotal) {
      const container = document.createElement('div'); container.style.cssText='display:flex;justify-content:center;margin:18px 0';
      container.innerHTML = `<button class="btn-secondary" id="load-more-clubs">Показать ещё клубы (${state.clubTotal-state.clubOffset})</button>`;
      document.getElementById('club-grid').after(container);
      container.querySelector('button').addEventListener('click', loadMoreClubs);
    }
  } catch (err) { toast(err.message, true); }
}
async function loadMoreClubs() {
  const button = document.getElementById('load-more-clubs'); if (!button) return;
  button.disabled = true; button.textContent = 'Загружаем…';
  try {
    const query = new URLSearchParams({limit:'200',offset:String(state.clubOffset),q:state.search,league:state.league,sort:'alphabetical'});
    const data = await api(`/api/catalog/clubs?${query.toString()}`);
    state.clubs.push(...data.items); state.clubOffset += data.items.length; state.clubTotal = data.total;
    const node = document.getElementById('club-grid');
    node.insertAdjacentHTML('beforeend', data.items.map((club) => `<button class="club-card" data-club="${esc(club.source_id)}">${crest(club.club_name,club.logo_url)}<span><b>${esc(club.club_name)} <i class="club-star-rating">${club.fifa_stars ? Number(club.fifa_stars).toFixed(1) + ' ★' : ''}</i></b><small>${esc(club.country||'—')} · ${esc(club.league_name||'Лига')}</small><em>${club.has_squad?`Состав: ${club.squad_count} игроков`:'Игровой состав будет сформирован'}</em></span></button>`).join(''));
    data.items.forEach(club => node.querySelector(`[data-club="${CSS.escape(club.source_id)}"]`)?.addEventListener('click', () => selectClub(club.source_id)));
    const parent = button.parentElement; if (state.clubOffset >= state.clubTotal) parent.remove(); else { button.disabled=false; button.textContent=`Показать ещё клубы (${state.clubTotal-state.clubOffset})`; }
  } catch(err) { button.disabled=false; button.textContent='Повторить'; toast(err.message,true); }
}
async function selectClub(sourceId) {
  if (state.creatingSave) return;
  state.creatingSave = true;
  const controls = () => document.querySelectorAll('[data-club], #load-more-clubs, #club-search, #league-filter');
  controls().forEach((control) => { control.disabled = true; });
  const button = document.querySelector(`[data-club="${CSS.escape(sourceId)}"]`);
  if (button) button.setAttribute('aria-busy', 'true');

  // Give immediate feedback before the server starts creating a full career.
  const loading = document.createElement('div');
  loading.className = 'action-loading';
  loading.innerHTML = '<div class="action-loading-card"><span class="loading-spinner"></span><b>Формируем карьеру</b><small>Загружаем составы, тактику и календарь сезона…</small></div>';
  document.body.appendChild(loading);

  try {
    await api('/api/saves', {
      method: 'POST',
      body: JSON.stringify({club_source_id:sourceId,save_name:'Моя карьера'})
    });
    toast('Карьера создана!');
    await start();
  } catch (err) {
    // A request can fail after the database transaction has committed.
    let openedExistingSave = false;
    try {
      const me = await api('/api/me');
      state.manager = me.manager;
      if (me.save) {
        state.save = me.save;
        state.tab = 'home';
        state.cacheEpoch += 1;
        state.tabCache = {};
        state.tabLoads = {};
        state.preloadStarted = false;
        toast('Карьера уже создана — открываем её.');
        await renderCurrent();
        openedExistingSave = true;
      }
    } catch (_) {
      // Keep the original request error if reconciliation also fails.
    }
    if (!openedExistingSave) {
      toast(err.message, true);
      controls().forEach((control) => { control.disabled = false; });
    }
  } finally {
    loading.remove();
    if (button) button.removeAttribute('aria-busy');
    state.creatingSave = false;
  }
}
function navItems() {
  return [
    ['home','⌂','Обзор'],['squad','♟','Состав'],['tactics','⌖','Тактика'],['fixtures','▦','Календарь'],['table','≡','Таблицы']
  ];
}
function shell(content, title = 'Обзор') {
  const name = state.manager?.name || 'Менеджер';
  const club = state.save?.club_name || 'Без клуба';
  app.innerHTML = `<div class="game-shell">
    <aside class="sidebar">
      <div class="sidebar-brand"><div class="brand-icon">SM</div><div><strong>SOCCER MASTER 27</strong><small>FOOTBALL MANAGER</small></div></div>
      <div class="nav-label">МЕНЕДЖМЕНТ</div>
      <nav class="nav-list">${navItems().map(([id,icon,label])=>`<button class="nav-item ${state.tab===id?'active':''}" data-nav="${id}"><span class="nav-ico">${icon}</span>${label}</button>`).join('')}</nav>
      <div class="nav-label">АККАУНТ</div><nav class="nav-list">
        <button class="nav-item" id="restart-career"><span class="nav-ico">↻</span>Новая карьера</button>
        <button class="nav-item" id="logout"><span class="nav-ico">↪</span>Выйти</button>
      </nav>
      <div class="sidebar-bottom"><div class="club-mini">${crest(club,state.save?.logo_url)}<span><b>${esc(club)}</b><small>${esc(state.save?.league || 'Сезон 2026/27')}</small></span></div></div>
    </aside>
    <main class="main-area">
      <header class="topbar"><div class="breadcrumb">Карьера <span style="color:#456253"> / </span> <b>${esc(title)}</b></div><div class="top-actions"><div class="season-pill">СЕЗОН 2026 / 27</div><div class="manager-chip"><div class="avatar">${esc(initials(name))}</div><span><b>${esc(name)}</b><small>Главный тренер</small></span></div></div></header>
      ${content}
    </main>
  </div>`;
  document.querySelectorAll('[data-nav]').forEach((button) => button.addEventListener('click', () => { state.tab = button.dataset.nav; renderCurrent(); }));
  document.getElementById('logout').addEventListener('click', logout);
  document.getElementById('restart-career').addEventListener('click', restartCareer);
}
async function restartCareer() {
  if (!window.confirm('Начать новую карьеру? Все текущие сохранения и связанные игровые данные будут удалены. Новая карьера начнётся с исходных данных SM27.')) return;
  const button=document.getElementById('restart-career'); if(button) button.disabled=true;
  try {
    await api('/api/saves/restart',{method:'POST',body:'{}'});
    state.save=null;state.tab='home';state.tactics=null;state.squad=[];state.fixtures=[];state.selectedTournamentId=null;
    await loadClubPage();
    toast('Карьера завершена. Выбери новый клуб.');
  } catch(err){toast(err.message,true);if(button)button.disabled=false;}
}
function renderHome(data) {
  const save = data.save;
  const match = data.next_match;
  const matchCard = match ? `<section class="panel hero-match">
    <div class="match-top"><span class="live-tag">СЛЕДУЮЩИЙ МАТЧ · ТУР ${esc(match.matchday||'—')}</span><span class="match-date">${dateLabel(match.match_date)}</span></div>
    <div class="match-teams"><div class="match-team">${crest(match.home_name, match.home_logo, 'large')}<b>${esc(match.home_name)}</b><small>${match.is_home?'Хозяева':'Гости'}</small></div><div class="vs">VS</div><div class="match-team">${crest(match.away_name, match.away_logo, 'large')}<b>${esc(match.away_name)}</b><small>${match.is_home?'Гости':'Хозяева'}</small></div></div>
    <div class="match-bottom"><small>Время продолжить сезон</small><button class="btn-primary" id="advance-game">Сыграть тур →</button></div>
  </section>` : `<section class="panel hero-match"><div class="match-top"><span class="live-tag">СЕЗОН</span><span class="match-date">2026 / 27</span></div><div class="empty-state"><strong>Матчи сезона завершены</strong>Новая глава начнётся со следующего сезона.</div></section>`;
  const standingRows = data.standings.slice(0,6).map((row,index) => `<tr class="${row.name===save.club_name?'me-row':''}"><td>${index+1}</td><td><div class="team-cell">${crest(row.name, row.logo_url)}${esc(row.name)}</div></td><td>${row.played}</td><td>${row.goal_difference || 0}</td><td><b>${row.points}</b></td></tr>`).join('');
  return `${pageHead('ЦЕНТР УПРАВЛЕНИЯ', 'Добро пожаловать, '+(state.manager?.name || 'тренер'), `${esc(save.club_name)} · ${esc(save.league)} · ${dateLabel(save.game_date)}`)}
    <div class="grid-main"><div>${matchCard}<div class="stats-strip">
      <div class="stat-card"><span>МЕСТО В ЛИГЕ</span><b>${data.my_position || '—'}<small style="font-size:11px;color:var(--muted)"> / ${data.standings.length}</small></b><small>Текущая позиция</small></div>
      <div class="stat-card"><span>СОСТАВ</span><b>${data.squad.players}</b><small>Игроков в команде</small></div>
      <div class="stat-card"><span>СРЕДНИЙ OVERALL</span><b>${data.squad.avg_overall || '—'}</b><small>Оценка SM27</small></div>
    </div><section class="panel" style="margin-top:17px"><div class="panel-head"><h3>Последние новости клуба</h3><span>SM27 DAILY</span></div><div class="empty-state" style="padding:18px 10px"><strong>Начало новой истории</strong>Настрой тактику, оцени состав и проведи первый тур. Дальше сезон будет развиваться по твоим решениям.</div></section></div>
    <section class="panel"><div class="panel-head"><h3>Турнирная таблица</h3><button class="btn-quiet" data-nav="table">Вся таблица →</button></div><div class="table-wrap"><table><thead><tr><th>#</th><th>Клуб</th><th>И</th><th>РМ</th><th>О</th></tr></thead><tbody>${standingRows || '<tr><td colspan="5">Таблица пока пустая</td></tr>'}</tbody></table></div></section></div>`;
}
function renderSquad(players) {
  const rows = players.map((player) => {
    const source = marketValueSourceLabel(player);
    const hasValue = Number(player.market_value || 0) > 0;
    const valueLabel = hasValue ? money(player.market_value) : '—';
    const status = [
      Number(player.injury_days_remaining || 0) > 0
        ? `<span class="player-status injury-status">Травма · ${player.injury_days_remaining} дн.</span>`
        : '',
      Number(player.suspension_matches || 0) > 0
        ? `<span class="player-status suspension-status">Дисквалификация · ${player.suspension_matches} матч.</span>`
        : ''
    ].filter(Boolean).join('');
    return `<tr class="player-row" data-player-details="${esc(player.id)}">
      <td><span class="rating">${player.overall}</span></td>
      <td><span class="player-name">${flagIcon(player.nationality_flag, player.nationality || 'Флаг страны')} ${esc(player.name)}</span>
        ${status}
        ${player.original_data?.generated ? '<div class="player-source-generated">Вымышленный игрок SM27</div>' : ''}</td>
      <td><span class="position-tag">${esc(player.position)}</span></td>
      <td>${(player.secondary_positions || []).map(pos => `<span class="secondary-position">${esc(pos)}</span>`).join(' ') || '—'}</td>
      <td>${player.age}</td>
      <td><span class="potential-rating">${player.potential}</span></td>
      <td class="value" title="${esc(source)}">${valueLabel}<div class="data-source">${esc(source)}</div></td>
      <td>${player.contract_end ? new Date(player.contract_end).toLocaleDateString('ru-RU',{month:'short',year:'numeric'}) : '—'}</td>
      <td>${money(player.weekly_wage)}<div class="data-source">/ нед.</div></td>
      <td>${renderToneCrystals(player.sharpness)}</td>
      <td>${renderMoodFaces(player.morale)}</td>
    </tr>`;
  }).join('');
  return `${pageHead('ПЕРВАЯ КОМАНДА','Состав',`${players.length} игроков · нажми на игрока, чтобы открыть полный профиль`)}
    <section class="panel">
      <div class="panel-head"><h3>Игроки первой команды</h3><span>OVR / POTENTIAL / VALUE</span></div>
      <div class="table-wrap squad-table-wrap"><table class="squad-table">
        <thead><tr><th>OVR</th><th>ИГРОК</th><th>ПОЗ.</th><th>ДОП. ПОЗ.</th><th>ВОЗР.</th><th>POT</th><th>РЫНОЧНАЯ СТОИМОСТЬ</th><th>КОНТРАКТ</th><th>ЗАРПЛАТА</th><th>ТОНУС</th><th>НАСТРОЙ</th></tr></thead>
        <tbody>${rows || '<tr><td colspan="11">Состав не загружен</td></tr>'}</tbody>
      </table></div>
      <div class="catalog-note" style="margin-top:18px"><span>ⓘ</span><span>Оценка стоимости учитывает источник данных, лигу, возраст, OVR, потенциал и игровые атрибуты. У каждой цены указан источник: SofaScore, Transfermarkt или расчёт SM27.</span></div>
    </section>`;
}
function showPlayerDetails(playerId) {
  const player = state.squad.find(item => String(item.id) === String(playerId));
  if (!player) return;
  document.getElementById('player-detail-modal')?.remove();
  const stats = player.attributes || {};
  const keeper = player.position === 'GK';
  const labels = keeper
    ? [['DIV','Отражение'],['HAN','Игра руками'],['KIC','Удар'],['REF','Реакция'],['SPE','Скорость'],['POS','Позиционирование']]
    : [['PAC','Скорость'],['SHO','Удар'],['PAS','Пас'],['DRI','Дриблинг'],['DEF','Защита'],['PHY','Физика']];
  const bars = labels.map(([code,label]) => `<div class="attribute-item"><div><b>${code}</b><span>${label}</span><strong>${stats[code] ?? player.overall}</strong></div><i><span style="width:${stats[code] ?? player.overall}%"></span></i></div>`).join('');
  const trainOptions = (POSITION_TRAINING_OPTIONS[player.position] || [])
    .filter(position => !(player.secondary_positions || []).includes(position));
  const isTraining = Boolean(player.position_training_target);
  const trainingBlock = isTraining
    ? `<div class="position-training-progress"><b>Осваивает ${esc(player.position_training_target)}</b><span>${player.position_training_progress ?? 0}%</span><i><span style="width:${player.position_training_progress ?? 0}%"></span></i></div>`
    : trainOptions.length
      ? `<div class="position-training-controls"><label>Осваивать позицию<select id="position-training-target" class="select-input">${trainOptions.map(position => `<option value="${position}">${position}</option>`).join('')}</select></label><button id="start-position-training" class="btn-secondary">Начать тренировку</button></div><small class="training-help">Одна новая позиция за раз. До освоения игрок получает позиционный штраф.</small>`
      : '<small class="training-help">Для этой позиции нет доступных соседних ролей.</small>';
  const marketSource = marketValueSourceLabel(player);
  const fc27SourceUrl = /^https:\/\/www\.ea\.com\//i.test(player.fc27_source_url || '') ? player.fc27_source_url : '';
  const fotmobSourceUrl = !player.fc27_player_id && /^https:\/\/www\.fotmob\.com\/players\//i.test(player.source_url || '') ? player.source_url : '';
  const sofascoreSourceUrl = /^https:\/\/www\.sofascore\.com\/football\/player\//i.test(player.original_data?.research?.sofascore_url || '') ? player.original_data.research.sofascore_url : '';
  const hasVerifiedValue = Number(player.market_value || 0) > 0
    && player.market_value_source === 'SofaScore';
  const modal = document.createElement('div');
  modal.id = 'player-detail-modal';
  modal.className = 'player-modal-backdrop';
  modal.innerHTML = `
    <section class="player-modal panel">
      <button class="modal-close" id="close-player-modal" aria-label="Закрыть">×</button>
      <div class="player-modal-head">
        <div class="player-modal-flag">${flagIcon(player.nationality_flag, player.nationality || 'Флаг страны')}</div>
        <div><div class="eyebrow">ПРОФИЛЬ ФУТБОЛИСТА</div><h2>${esc(player.name)}</h2><p>${esc(player.nationality || 'Национальность не указана')} · ${player.age} лет · ${esc(player.position)}</p></div>
        <div class="player-modal-ratings"><b>${player.overall}</b><span>OVR</span><b>${player.potential}</b><span>POT</span></div>
      </div>
      <div class="player-modal-grid">
        <div class="player-metric"><small>Дополнительные позиции</small><b>${(player.secondary_positions || []).map(esc).join(' · ') || 'Не освоены'}</b></div>
        <div class="player-metric"><small>Рыночная стоимость</small><b>${hasVerifiedValue ? money(player.market_value) : 'Нет подтверждённой оценки'}</b><em>${esc(marketSource)}</em></div>
        <div class="player-metric"><small>Контракт до</small><b>${player.contract_end ? dateLabel(player.contract_end) : 'Не указано'}</b><em>Источник: ${esc(player.profile_source || 'SM27 estimate')}</em></div>
        <div class="player-metric"><small>Зарплата в неделю</small><b>${money(player.weekly_wage)}</b><em>Оценка SM27 по FC 27 Career Mode</em></div>
      </div>
      <div class="player-state-grid">
        <div class="condition-metric"><small>Тонус</small><b>${player.sharpness ?? 85}/100</b>${renderToneCrystals(player.sharpness)}</div>
        <div class="condition-metric"><small>Настрой</small><b>${player.morale ?? 70}/100</b>${renderMoodFaces(player.morale)}</div>
      </div>
      <div class="position-training-panel">
        <div class="panel-head"><h3>Развитие позиции</h3><span>${isTraining ? 'ИДЁТ ТРЕНИРОВКА' : 'ВЫБЕРИ НОВУЮ РОЛЬ'}</span></div>
        ${trainingBlock}
      </div>
      <div class="panel-head"><h3>Характеристики ${keeper ? 'вратаря' : 'полевого игрока'}</h3><span>ШКАЛА 1–99</span></div>
      <div class="attribute-grid">${bars}</div>
      <div class="catalog-note"><span>ⓘ</span><span>${player.fc27_player_id ? 'OVR и шесть основных характеристик взяты из базы EA SPORTS FC 27. Потенциал и зарплата — отдельные оценки SM27.' : 'Игрок не найден в базе EA SPORTS FC 27. OVR, потенциал и характеристики — исследовательская оценка SM27, не официальный рейтинг EA.'} ${fc27SourceUrl ? '<a href="' + esc(fc27SourceUrl) + '" target="_blank" rel="noopener noreferrer">Официальная карточка EA</a>' : ''} ${fotmobSourceUrl ? '<a href="' + esc(fotmobSourceUrl) + '" target="_blank" rel="noopener noreferrer">Статистика FotMob 2026/27</a>' : ''} ${sofascoreSourceUrl ? '<a href="' + esc(sofascoreSourceUrl) + '" target="_blank" rel="noopener noreferrer">Стоимость SofaScore</a>' : ''}</span></div>
    </section>`;
  document.body.appendChild(modal);
  document.getElementById('close-player-modal').addEventListener('click', () => modal.remove());
  modal.addEventListener('click', event => { if (event.target === modal) modal.remove(); });
  document.getElementById('start-position-training')?.addEventListener('click', async () => {
    const position = document.getElementById('position-training-target')?.value;
    if (!position) return;
    try {
      await api(`/api/players/${encodeURIComponent(player.id)}/position-training`, {
        method: 'POST',
        body: JSON.stringify({position})
      });
      state.squad = await api('/api/squad');
      showPlayerDetails(player.id);
      toast('Тренировка новой позиции начата');
    } catch (error) {
      toast(error.message, true);
    }
  });
}


const FORMATIONS = [
  "3-1-4-2","3-4-1-2","3-4-2-1","3-4-3","3-4-3 Flat","3-5-2",
  "4-1-2-1-2","4-1-2-1-2 (2)","4-1-2-1-2 Narrow","4-1-2-1-2 Wide","4-1-3-2","4-1-4-1",
  "4-2-1-3","4-2-2-2","4-2-3-1","4-2-3-1 (2)","4-2-3-1 Narrow","4-2-3-1 Wide",
  "4-2-4","4-3-1-2","4-3-2-1","4-3-3","4-3-3 (2)","4-3-3 (3)","4-3-3 (4)","4-3-3 Attack","4-3-3 Defend",
  "4-3-3 Flat","4-3-3 Holding","4-4-1-1 Midfield","4-4-2","4-4-2 (2)","4-4-2 Flat","4-4-2 Holding",
  "4-5-1","4-5-1 (2)","4-5-1 Attack","4-5-1 Flat","5-2-1-2","5-2-3","5-3-2",
  "5-3-2 Holding","5-4-1","5-4-1 Flat"
];
const FORMATION_SHAPES = {
  "3-1-4-2":[["GK"],["CB","CB","CB"],["CDM"],["LM","CM","CM","RM"],["ST","ST"]],
  "3-4-1-2":[["GK"],["CB","CB","CB"],["LM","CM","CM","RM"],["CAM"],["ST","ST"]],
  "3-4-2-1":[["GK"],["CB","CB","CB"],["LM","CM","CM","RM"],["CAM","CAM"],["ST"]],
  "3-4-3":[["GK"],["CB","CB","CB"],["LM","CM","CM","RM"],["LW","ST","RW"]],
  "3-5-2":[["GK"],["CB","CB","CB"],["LM","CDM","CM","CDM","RM"],["ST","ST"]],
  "4-1-2-1-2":[["GK"],["LB","CB","CB","RB"],["CDM"],["CM","CM"],["CAM"],["ST","ST"]],
  "4-1-3-2":[["GK"],["LB","CB","CB","RB"],["CDM"],["LM","CM","RM"],["ST","ST"]],
  "4-1-4-1":[["GK"],["LB","CB","CB","RB"],["CDM"],["LM","CM","CM","RM"],["ST"]],
  "4-2-1-3":[["GK"],["LB","CB","CB","RB"],["CDM","CM"],["CAM"],["LW","ST","RW"]],
  "4-2-2-2":[["GK"],["LB","CB","CB","RB"],["CDM","CM"],["CAM","CAM"],["ST","ST"]],
  "4-2-3-1":[["GK"],["LB","CB","CB","RB"],["CDM","CDM"],["LM","CAM","RM"],["ST"]],
  "4-2-4":[["GK"],["LB","CB","CB","RB"],["CDM","CM"],["LW","ST","ST","RW"]],
  "4-3-1-2":[["GK"],["LB","CB","CB","RB"],["CDM","CM","CM"],["CAM"],["ST","ST"]],
  "4-3-2-1":[["GK"],["LB","CB","CB","RB"],["CM","CDM","CM"],["CAM","CAM"],["ST"]],
  "4-3-3":[["GK"],["LB","CB","CB","RB"],["CDM","CM","CAM"],["LW","ST","RW"]],
  "4-3-3 Attack":[["GK"],["LB","CB","CB","RB"],["CDM"],["CM","CAM"],["LW","ST","RW"]],
  "4-3-3 Defend":[["GK"],["LB","CB","CB","RB"],["CDM","CM","CM"],["LW","ST","RW"]],
  "4-3-3 Flat":[["GK"],["LB","CB","CB","RB"],["CM","CM","CM"],["LW","ST","RW"]],
  "4-3-3 Holding":[["GK"],["LB","CB","CB","RB"],["CDM","CDM","CM"],["LW","ST","RW"]],
  "4-4-1-1 Midfield":[["GK"],["LB","CB","CB","RB"],["LM","CM","CM","RM"],["CAM"],["ST"]],
  "4-1-2-1-2 (2)":[["GK"],["LB","CB","CB","RB"],["CDM"],["CM","CM"],["CAM"],["ST","ST"]],
  "4-2-3-1 (2)":[["GK"],["LB","CB","CB","RB"],["CDM","CDM"],["LM","CAM","RM"],["ST"]],
  "4-3-3 (2)":[["GK"],["LB","CB","CB","RB"],["CM","CDM","CM"],["LW","ST","RW"]],
  "4-3-3 (3)":[["GK"],["LB","CB","CB","RB"],["CDM","CM","CDM"],["LW","ST","RW"]],
  "4-3-3 (4)":[["GK"],["LB","CB","CB","RB"],["CM","CAM","CM"],["LW","ST","RW"]],
  "4-4-2":[["GK"],["LB","CB","CB","RB"],["LM","CM","CM","RM"],["ST","ST"]],
  "4-4-2 (2)":[["GK"],["LB","CB","CB","RB"],["CDM","CDM","LM","RM"],["ST","ST"]],
  "4-4-2 Flat":[["GK"],["LB","CB","CB","RB"],["LM","CM","CM","RM"],["ST","ST"]],
  "4-5-1":[["GK"],["LB","CB","CB","RB"],["LM","CM","CDM","CM","RM"],["ST"]],
  "4-5-1 (2)":[["GK"],["LB","CB","CB","RB"],["LM","CM","CM","CM","RM"],["ST"]],
  "5-2-1-2":[["GK"],["LWB","CB","CB","CB","RWB"],["CM","CM"],["CAM"],["ST","ST"]],
  "5-2-3":[["GK"],["LWB","CB","CB","CB","RWB"],["CM","CM"],["LW","ST","RW"]],
  "5-3-2":[["GK"],["LWB","CB","CB","CB","RWB"],["CM","CDM","CM"],["ST","ST"]],
  "5-4-1":[["GK"],["LWB","CB","CB","CB","RWB"],["LM","CM","CM","RM"],["ST"]]
};
function shapeForFormation(formation) {
  const base = formation.replace(/ (Flat|Attack|Defend|Holding|Narrow|Wide|Midfield)$/i, "");
  return FORMATION_SHAPES[formation] || FORMATION_SHAPES[base] || FORMATION_SHAPES["4-3-3"];
}
function formationSlots(formation) {
  const lines = shapeForFormation(formation);
  const y = [91, 75, 56, 35, 15];
  const roles = [];
  lines.forEach((line,row) => {
    const n = line.length;
    line.forEach((role,index) => roles.push({
      role,
      left: n === 1 ? 50 : 10 + index * (80 / (n-1)),
      top: y[Math.min(row,y.length-1)]
    }));
  });
  return roles.slice(0,11);
}
function positionPenalty(player, target) {
  const primary = player.position || "CM";
  const secondary = player.secondary_positions || [];
  if (primary === target || secondary.includes(target)) return 0;
  if (primary === "GK" || target === "GK") return -40;
  const distances = {
    RB:{LB:-2,RWB:-2,LWB:-5,CB:-3,RM:-5,CDM:-7},
    LB:{RB:-2,LWB:-2,RWB:-5,CB:-3,LM:-5,CDM:-7},
    CB:{LB:-3,RB:-3,CDM:-3,RWB:-5,LWB:-5,CM:-7},
    CDM:{CM:-2,CB:-3,CAM:-5,RM:-7,LM:-7},
    CM:{CDM:-2,CAM:-2,RM:-3,LM:-3,CB:-7,ST:-10},
    CAM:{CM:-2,CF:-3,ST:-5,RM:-5,LM:-5},
    RM:{RW:-2,CM:-3,RB:-5,ST:-7,LM:-7},
    LM:{LW:-2,CM:-3,LB:-5,ST:-7,RM:-7},
    RW:{RM:-2,ST:-3,CF:-5,LW:-7,RB:-7},
    LW:{LM:-2,ST:-3,CF:-5,RW:-7,LB:-7},
    ST:{CF:-2,CAM:-5,RW:-7,LW:-7,CM:-10},
    CF:{ST:-2,CAM:-3,RW:-5,LW:-5,CM:-7},
    RWB:{RB:-2,RM:-3,LB:-5,CB:-5},
    LWB:{LB:-2,LM:-3,RB:-5,CB:-5}
  };
  return (distances[primary] || {})[target] ?? -7;
}
function optimiseLineup(players, formation) {
  const roles = formationSlots(formation).map(slot => slot.role);
  const fullMask = (1 << roles.length) - 1;
  const blank = Array(roles.length).fill(null);
  let dp = new Map([[0, {score: 0, path: blank}]]);
  const ordered = [...players].sort((a,b) => String(a.id).localeCompare(String(b.id)));

  for (const player of ordered) {
    const next = new Map(dp);
    for (const [mask, entry] of dp.entries()) {
      for (let index = 0; index < roles.length; index++) {
        const bit = 1 << index;
        if (mask & bit) continue;
        const candidateMask = mask | bit;
        const candidatePath = [...entry.path];
        candidatePath[index] = player;
        const candidateScore = entry.score
          + Number(player.dynamic_overall ?? player.overall ?? 0)
          + positionPenalty(player, roles[index]);
        const previous = next.get(candidateMask);
        const candidateKey = candidatePath.map(item => String(item?.id ?? '')).join('|');
        const previousKey = previous ? previous.path.map(item => String(item?.id ?? '')).join('|') : '';
        if (!previous || candidateScore > previous.score
          || (candidateScore === previous.score && candidateKey < previousKey)) {
          next.set(candidateMask, {score: candidateScore, path: candidatePath});
        }
      }
    }
    dp = next;
  }
  const best = dp.get(fullMask);
  const starters = best ? best.path.filter(Boolean) : [];
  if (starters.length !== roles.length) {
    const fallback = [...players].sort((a,b) => Number(b.dynamic_overall ?? b.overall) - Number(a.dynamic_overall ?? a.overall));
    return {starters: fallback.slice(0, roles.length), remaining: fallback.slice(roles.length)};
  }
  const selected = new Set(starters.map(player => String(player.id)));
  const remaining = players.filter(player => !selected.has(String(player.id)));
  return {starters, remaining};
}
function ensureTacticState(players, tactics) {
  const formation = tactics.formation || "4-3-3";
  const existing = new Map(players.map(player => [String(player.id),player]));
  let starters = (tactics.starting_xi || []).map(id => existing.get(String(id))).filter(Boolean);
  let rest = players.filter(p => !starters.some(s => String(s.id)===String(p.id)));
  if (starters.length !== 11) {
    const optimized = optimiseLineup(players,formation);
    starters = optimized.starters;
    rest = optimized.remaining;
  }
  state.tacticFormation = formation;
  state.tacticSlots = starters.slice(0,11).map(p => String(p.id));
  const savedBench = (tactics.bench || []).map(id => String(id)).filter(id => existing.has(id) && !state.tacticSlots.includes(id));
  state.tacticBench = savedBench.slice(0,9);
  const fillBench = rest.filter(p => !state.tacticBench.includes(String(p.id))).sort((a,b)=>(b.dynamic_overall??b.overall)-(a.dynamic_overall??a.overall));
  while(state.tacticBench.length<7 && fillBench.length) state.tacticBench.push(String(fillBench.shift().id));
  state.tacticSettings = {
    build_up: "balanced", chance_creation: "balanced", pressing: "on_mistake",
    defensive_approach: "balanced", width: 50, depth: 55, tempo: "balanced",
    focus: "balanced", player_roles: {}, ...(tactics.style || {})
  };
  state.tacticSettings.player_roles ||= {};
  const savedReserve = Array.isArray(state.tacticSettings.reserve_order) ? state.tacticSettings.reserve_order.map(String) : [];
  const assigned = new Set([...state.tacticSlots, ...state.tacticBench]);
  state.tacticReserve = savedReserve.filter(id => existing.has(id) && !assigned.has(id));
  currentReserveIds();
  if (state.selectedTacticSlot === undefined) state.selectedTacticSlot = null;
  if (state.selectedTacticPlayer === undefined) state.selectedTacticPlayer = null;
  if (!Array.isArray(state.tacticReserve)) state.tacticReserve = [];
}
function redrawTactics() {
  const tactics = {formation: state.tacticFormation, mentality: 'balanced', style: state.tacticSettings, starting_xi: state.tacticSlots, bench: state.tacticBench};
  shell(renderTactics(state.squad, tactics), 'Тактика');
  setupTacticsInteractions();
}
function playerTag(player, slotIndex = null) {
  if (!player) return "";
  return `<div class="pitch-player-card" draggable="true" data-player-id="${esc(player.id)}" ${slotIndex !== null ? `data-pitch-slot="${slotIndex}"` : ""}>
    <b>${player.overall}</b><small>${esc(player.name.split(" ").slice(-1)[0])}</small>
  </div>`;
}
function currentReserveIds() {
  const used = new Set([...state.tacticSlots, ...state.tacticBench].filter(Boolean));
  const reserve = state.squad.filter(player => !used.has(String(player.id))).map(player => String(player.id));
  const valid = new Set(reserve);
  const ordered = (state.tacticReserve || []).filter(id => valid.has(id));
  reserve.forEach(id => { if (!ordered.includes(id)) ordered.push(id); });
  state.tacticReserve = ordered;
  return ordered;
}
function renderTactics(players, tactics) {
  const formation = tactics.formation || "4-3-3";
  const slots = formationSlots(formation);
  const byId = new Map(players.map(player => [String(player.id),player]));
  const pitchPlayers = slots.map((slot,index) => {
    const player = byId.get(state.tacticSlots[index]);
    const selected = state.selectedTacticSlot === index;
    const rating = player ? (player.dynamic_overall ?? player.overall) + positionPenalty(player,slot.role) : null;
    return `<button class="pitch-player ${selected ? "selected" : ""} ${player ? "" : "empty"}" style="left:${slot.left}%;top:${slot.top}%" data-pitch-slot="${index}" data-drop-slot="${index}" draggable="${Boolean(player)}" ${player ? `data-player-id="${esc(player.id)}"` : ""}>
      <strong>${player ? rating : "+"}</strong><small>${esc(slot.role)}</small><em>${player ? esc(player.name.split(" ").slice(-1)[0]) : "Выбрать"}</em>
    </button>`;
  }).join("");
  const benchIds = new Set(state.tacticBench);
  const reserveIds = currentReserveIds();
  const bench = state.tacticBench.map(id => {
    const p=byId.get(id);
    return p ? '<div class="tactic-roster-item"><button class="tactic-player-row bench-player ' +
      (state.selectedTacticPlayer===String(id) ? 'selected' : '') +
      '" draggable="true" data-player-id="' + esc(id) + '"><b>' +
      (p.dynamic_overall ?? p.overall) + '</b><span>' + esc(p.name) +
      '<small>' + esc(p.position) + ' · запас</small></span></button></div>' : '';
  }).join("");
  const reserves = reserveIds.map(id=>{
    const p=byId.get(id);
    return p ? '<div class="tactic-roster-item"><button class="tactic-player-row reserve-player ' +
      (state.selectedTacticPlayer===String(id) ? 'selected' : '') +
      '" draggable="true" data-player-id="' + esc(id) + '"><b>' +
      (p.dynamic_overall ?? p.overall) + '</b><span>' + esc(p.name) +
      '<small>' + esc(p.position) + ' · резерв</small></span></button></div>' : '';
  }).join("");
  const settings = state.tacticSettings;
  const select = (id,label,value,options) => `<label class="tactic-setting"><span>${label}</span><select id="${id}" class="select-input">${options.map(([v,l])=>`<option value="${v}" ${value===v?"selected":""}>${l}</option>`).join("")}</select></label>`;
  const options = {
    balanced:"Сбалансированно", short:"Короткий пас", direct:"Вертикальный пас", fast:"Быстрый выход",
    possession:"Контроль мяча", counter:"Контратака", high:"Высокий прессинг", mid:"Средний блок",
    low:"Низкий блок", aggressive:"Агрессивно", conservative:"Осторожно", wide:"Через фланги",
    centre:"Через центр", on_mistake:"Прессинг после потери", heavy:"Постоянный прессинг"
  };
  return `${pageHead("ПЛАН НА МАТЧ","Тактика","Выбери схему, расставь футболистов и настрой поведение команды.")}
    <div class="tactic-toolbar panel">
      <label>СХЕМА<select id="formation" class="select-input">${FORMATIONS.map(f=>`<option value="${esc(f)}" ${formation===f?"selected":""}>${esc(f)}</option>`).join("")}</select></label>
      <span class="lineup-counter">${state.tacticSlots.filter(Boolean).length}/11 В ОСНОВЕ</span>
      <span class="lineup-counter">${state.tacticBench.length}/9 В ЗАПАСЕ</span>
      <button id="auto-lineup" class="btn-secondary">Лучший состав</button>
      <button id="save-tactics" class="btn-primary">Сохранить</button>
    </div>
    <div class="tactic-layout tactic-layout-full">
      <section class="panel tactic-board-panel">
        <div class="panel-head"><h3>Тактическое поле</h3><span>Нажми на двух игроков в любой группе, чтобы поменять их местами</span></div>
        <div class="pitch pitch-football" id="tactic-pitch"><div class="pitch-line"></div><div class="pitch-box pitch-box-top"></div><div class="pitch-box pitch-box-bottom"></div><div class="pitch-circle"></div>${pitchPlayers}</div>
        <div class="catalog-note"><span>ⓘ</span><span>ОВР на поле учитывает позиционный штраф. Родная и дополнительная позиция не снижают рейтинг. Позиция вратаря и полевого игрока — штраф 40.</span></div>
        <div class="squad-bench-block"><div class="panel-head"><h3>Запас</h3><span>5–9 игроков · нажми на двух игроков для обмена</span></div><div class="tactic-roster-grid" id="tactic-bench">${bench || '<p class="empty-state">Скамейка пуста</p>'}</div></div>
        <div class="squad-bench-block"><div class="panel-head"><h3>Резерв</h3><span>Нажми на двух игроков для обмена с основой или запасом</span></div><div class="tactic-roster-grid reserves-list" id="tactic-reserves">${reserves || '<p class="empty-state">В резерве пока нет игроков</p>'}</div></div>
      </section>
      <aside class="panel tactic-controls tactic-settings-panel">
        <div class="panel-head"><h3>Тактика команды</h3><span>Установки на матч</span></div>
        ${select("build-up","Построение атаки",settings.build_up,[["balanced","Сбалансированно"],["short","Короткий пас"],["direct","Вертикальные передачи"],["fast","Быстрый выход"],["possession","Контроль мяча"]])}
        ${select("chance-creation","Создание моментов",settings.chance_creation,[["balanced","Сбалансированно"],["wide","Через фланги"],["centre","Через центр"],["direct","Забросы за спину"],["patient","Терпеливое владение"]])}
        ${select("pressing","Прессинг",settings.pressing,[["on_mistake","После потери"],["heavy","Постоянный прессинг"],["mid","Средний блок"],["low","Низкий блок"]])}
        ${select("defensive-approach","Оборонительная линия",settings.defensive_approach,[["balanced","Сбалансированно"],["aggressive","Высокая линия"],["conservative","Низкий блок"],["offside","Искусственный офсайд"]])}
        ${select("tempo","Темп",settings.tempo,[["balanced","Обычный"],["slow","Медленный"],["fast","Высокий"]])}
        ${select("focus","Акцент команды",settings.focus,[["balanced","Баланс"],["attack","Атака"],["defence","Оборона"],["left","Левый фланг"],["right","Правый фланг"],["centre","Центр поля"]])}
        <label class="tactic-setting"><span>Ширина атаки <b id="width-value">${settings.width}</b></span><input type="range" id="tactic-width" min="1" max="100" value="${settings.width}"></label>
        <label class="tactic-setting"><span>Высота линии <b id="depth-value">${settings.depth}</b></span><input type="range" id="tactic-depth" min="1" max="100" value="${settings.depth}"></label>
        <div class="panel-head"><h3>Роли игроков</h3><span>Указания футболистам</span></div>
        <div class="player-role-list">${state.tacticSlots.map((id,index)=>{const p=byId.get(id);return p?`<label class="tactic-setting"><span>${esc(p.name)}</span><select data-player-role="${esc(id)}" class="select-input">${[["balanced","Сбалансированно"],["attack","Подключаться в атаку"],["stay","Оставаться сзади"],["free","Свободная роль"],["press","Активный прессинг"]].map(([v,l])=>`<option value="${v}" ${(settings.player_roles[id]||"balanced")===v?"selected":""}>${l}</option>`).join("")}</select></label>`: ""}).join("")}</div>
      </aside>
    </div>`;
}
function locateTacticPlayer(playerId) {
  const id = String(playerId);
  const xiIndex = state.tacticSlots.indexOf(id);
  if (xiIndex >= 0) return {kind: 'xi', index: xiIndex};
  const benchIndex = state.tacticBench.indexOf(id);
  if (benchIndex >= 0) return {kind: 'bench', index: benchIndex};
  const reserveIndex = currentReserveIds().indexOf(id);
  if (reserveIndex >= 0) return {kind: 'reserve', index: reserveIndex};
  return null;
}
function swapRosterPlayers(firstId, secondId) {
  const a = String(firstId), b = String(secondId);
  if (!a || !b || a === b) return;
  const first = locateTacticPlayer(a);
  const second = locateTacticPlayer(b);
  if (!first || !second) return;
  const collections = {xi: state.tacticSlots, bench: state.tacticBench, reserve: state.tacticReserve};
  const firstList = collections[first.kind];
  const secondList = collections[second.kind];
  [firstList[first.index], secondList[second.index]] = [secondList[second.index], firstList[first.index]];
  state.selectedTacticPlayer = null;
  state.selectedTacticSlot = null;
  redrawTactics();
}
function swapTacticPlayers(slotIndex, playerId) {
  const targetId = String(playerId);
  const currentId = state.tacticSlots[slotIndex];
  if (currentId && currentId === targetId) {
    state.selectedTacticPlayer = null;
    state.selectedTacticSlot = null;
    redrawTactics();
    return;
  }
  if (currentId) {
    swapRosterPlayers(currentId, targetId);
    return;
  }
  const target = locateTacticPlayer(targetId);
  if (!target) return;
  if (target.kind === 'xi') state.tacticSlots[target.index] = null;
  else {
    const list = target.kind === 'bench' ? state.tacticBench : state.tacticReserve;
    list.splice(target.index, 1);
  }
  state.tacticSlots[slotIndex] = targetId;
  state.selectedTacticPlayer = null;
  state.selectedTacticSlot = null;
  redrawTactics();
}
function setupTacticsInteractions() {
  document.getElementById("formation")?.addEventListener("change",event=>{
    const result=optimiseLineup(state.squad,event.target.value);
    state.tacticSlots=result.starters.map(player=>String(player.id));
    state.tacticBench=result.remaining.slice(0,7).map(player=>String(player.id));
    state.tacticReserve=[];
    state.selectedTacticPlayer=null;
    state.selectedTacticSlot=null;
    state.tacticFormation=event.target.value;
    redrawTactics();
  });
  document.getElementById("auto-lineup")?.addEventListener("click",()=>{
    const formation=document.getElementById("formation").value;
    const result=optimiseLineup(state.squad,formation);
    state.tacticSlots=result.starters.map(player=>String(player.id));
    state.tacticBench=result.remaining.slice(0,7).map(player=>String(player.id));
    state.tacticReserve=[];
    state.selectedTacticPlayer=null;
    state.selectedTacticSlot=null;
    state.tacticFormation=formation;
    redrawTactics();
  });
  document.querySelectorAll("[data-pitch-slot]").forEach(button=>button.addEventListener("click",()=>{
    const slot=Number(button.dataset.pitchSlot);
    if(state.selectedTacticPlayer){
      swapTacticPlayers(slot,state.selectedTacticPlayer);
      return;
    }
    if(state.selectedTacticSlot!==null && state.selectedTacticSlot!==slot){
      const first=state.tacticSlots[state.selectedTacticSlot];
      const second=state.tacticSlots[slot];
      state.tacticSlots[slot]=first;
      state.tacticSlots[state.selectedTacticSlot]=second;
      state.selectedTacticSlot=null;
      state.selectedTacticPlayer=null;
      redrawTactics();
      return;
    }
    state.selectedTacticSlot=state.selectedTacticSlot===slot ? null : slot;
    state.selectedTacticPlayer=state.selectedTacticSlot===null ? null : (state.tacticSlots[slot] || null);
    redrawTactics();
  }));
  document.querySelectorAll(".tactic-player-row").forEach(button=>button.addEventListener("click",()=>{
    const id=String(button.dataset.playerId);
    if(state.selectedTacticSlot!==null){
      swapTacticPlayers(state.selectedTacticSlot,id);
      return;
    }
    if(state.selectedTacticPlayer && state.selectedTacticPlayer!==id){
      swapRosterPlayers(state.selectedTacticPlayer,id);
      return;
    }
    state.selectedTacticPlayer=state.selectedTacticPlayer===id ? null : id;
    redrawTactics();
  }));
  const pitch=document.getElementById("tactic-pitch");
  pitch?.querySelectorAll("[data-pitch-slot]").forEach(slot=>{
    slot.addEventListener("dragstart",event=>{
      event.dataTransfer.setData("text/player-id",state.tacticSlots[Number(slot.dataset.pitchSlot)]||"");
    });
  });
  document.querySelectorAll("[data-player-id]").forEach(node=>{
    node.addEventListener("dragstart",event=>event.dataTransfer.setData("text/player-id",node.dataset.playerId));
  });
  document.querySelectorAll(".tactic-player-row").forEach(target=>{
    target.addEventListener("dragover",event=>event.preventDefault());
    target.addEventListener("drop",event=>{
      event.preventDefault();
      event.stopPropagation();
      const from=event.dataTransfer.getData("text/player-id");
      const to=String(target.dataset.playerId || "");
      if(from && to && from!==to) swapRosterPlayers(from,to);
    });
  });
  pitch?.querySelectorAll("[data-drop-slot]").forEach(slot=>{
    slot.addEventListener("dragover",event=>event.preventDefault());
    slot.addEventListener("drop",event=>{
      event.preventDefault();
      const id=event.dataTransfer.getData("text/player-id");
      if(id) swapTacticPlayers(Number(slot.dataset.dropSlot),id);
    });
  });
  ["build-up","chance-creation","pressing","defensive-approach","tempo","focus"].forEach(id=>{
    document.getElementById(id)?.addEventListener("change",event=>{
      const key=id.replace(/-([a-z])/g,(_,character)=>character.toUpperCase()).replace(/^buildUp$/,"build_up").replace(/^chanceCreation$/,"chance_creation").replace(/^defensiveApproach$/,"defensive_approach");
      state.tacticSettings[key]=event.target.value;
    });
  });
  document.getElementById("tactic-width")?.addEventListener("input",event=>{
    state.tacticSettings.width=Number(event.target.value);
    document.getElementById("width-value").textContent=event.target.value;
  });
  document.getElementById("tactic-depth")?.addEventListener("input",event=>{
    state.tacticSettings.depth=Number(event.target.value);
    document.getElementById("depth-value").textContent=event.target.value;
  });
  document.querySelectorAll("[data-player-role]").forEach(node=>node.addEventListener("change",event=>{
    state.tacticSettings.player_roles[event.target.dataset.playerRole]=event.target.value;
  }));
  document.getElementById("save-tactics")?.addEventListener("click",saveTactics);
}
function renderFixtures(rows) {
  if (!rows.length) {
    return pageHead("РАСПИСАНИЕ","Календарь","Календарь сезона 2026/27.") +
      '<section class="panel"><div class="empty-state">Матчей пока нет</div></section>';
  }
  if (!state.calendarMonth) {
    const initialDate = new Date(state.save?.game_date || "2026-07-01T12:00:00");
    state.calendarMonth = new Date(initialDate.getFullYear(), initialDate.getMonth(), 1);
  }
  const month = new Date(state.calendarMonth.getFullYear(), state.calendarMonth.getMonth(), 1);
  const monthLabel = month.toLocaleDateString("ru-RU", {month:"long", year:"numeric"});
  const keyDate = value => {
    const date = new Date(value);
    return date.getFullYear() + "-" + String(date.getMonth()+1).padStart(2,"0") + "-" + String(date.getDate()).padStart(2,"0");
  };
  const byDate = new Map();
  rows.forEach(row => {
    const key = keyDate(row.match_date);
    if (!byDate.has(key)) byDate.set(key, []);
    byDate.get(key).push(row);
  });
  const offset = (month.getDay()+6)%7;
  const days = new Date(month.getFullYear(), month.getMonth()+1, 0).getDate();
  const cells = [];
  for (let i=0; i<offset; i++) cells.push('<div class="calendar-empty"></div>');
  for (let day=1; day<=days; day++) {
    const key = month.getFullYear() + "-" + String(month.getMonth()+1).padStart(2,"0") + "-" + String(day).padStart(2,"0");
    const match = (byDate.get(key) || [])[0];
    const result = match?.result || "scheduled";
    let cell = '<button class="calendar-day ' +
      (state.selectedCalendarDate===key ? "selected " : "") +
      (match ? "has-event" : "") + '" data-calendar-date="' + key + '" title="' +
      (match ? esc(match.opponent_name) : "") + '"><b>' + day + '</b>';
    if (match) {
      const score = match.status === "completed"
        ? String(match.home_score) + " : " + String(match.away_score)
        : "— : —";
      cell += '<span class="calendar-day-event">' +
        crest(match.opponent_name, match.opponent_logo) +
        '<span class="calendar-day-opponent"><b>' + esc(match.opponent_name) +
        '</b><small class="calendar-day-meta">' + esc(match.tournament_name || "Турнир") +
        ' · ' + esc(match.stage_label || "МАТЧ") +
        '</small><small class="calendar-day-homeaway">' + (match.is_home ? "ДОМА" : "В ГОСТЯХ") +
        '</small></span><strong class="calendar-day-score ' + result + '">' + score +
        '</strong></span>';
    }
    cell += '</button>';
    cells.push(cell);
  }
  const selected = state.selectedCalendarDate || keyDate(state.save?.game_date || "2026-07-01T12:00:00");
  const selectedRows = byDate.get(selected) || [];
  const selectedContent = selectedRows.length ? selectedRows.map(f => {
    const score = f.status === "completed"
      ? String(f.home_score) + " : " + String(f.away_score)
      : "— : —";
    const result = f.result || "scheduled";
    return '<button type="button" class="calendar-match-row calendar-selected-match" data-fixture-id="' + esc(f.id) + '">' +
      '<div class="calendar-selected-opponent">' + crest(f.opponent_name, f.opponent_logo) +
      '<span><b>' + esc(f.opponent_name) + '</b><small>' + esc(f.tournament_name || "Турнир") +
      '</small></span></div><div class="calendar-match-details"><span>' +
      esc(f.stage_label || "МАТЧ") + '</span><span>' + (f.is_home ? "ДОМА" : "В ГОСТЯХ") +
      '</span></div><strong class="calendar-match-score ' + result + '">' + score +
      '</strong><small>' + (f.status === "completed" ? "МАТЧ СЫГРАН · ПОДРОБНОСТИ ↗" : "ЗАПЛАНИРОВАН · ПРЕВЬЮ ↗") +
      '</small></button>';
  }).join("") : '<div class="empty-state">На выбранную дату матчей нет</div>';
  const weekdays = ["ПН","ВТ","СР","ЧТ","ПТ","СБ","ВС"].map(day => '<span>' + day + '</span>').join("");
  return pageHead("СЕЗОН 2026/27","Календарь","Месячный календарь матчей твоего клуба.") +
    '<div class="calendar-layout panel"><section class="calendar-main">' +
    '<div class="calendar-month-nav"><button class="btn-quiet" id="calendar-prev">‹</button><h2>' + monthLabel +
    '</h2><button class="btn-quiet" id="calendar-next">›</button></div>' +
    '<div class="calendar-weekdays">' + weekdays + '</div><div class="calendar-grid">' + cells.join("") +
    '</div><div class="calendar-legend"><span class="calendar-score win">Победа</span>' +
    '<span class="calendar-score draw">Ничья</span><span class="calendar-score loss">Поражение</span></div></section>' +
    '<aside class="calendar-selected"><div class="eyebrow">ВЫБРАННЫЙ ДЕНЬ</div><h3>' +
    dateLabel(selected + "T12:00:00") + '</h3>' + selectedContent + '</aside></div>';
}
function setupCalendarInteractions() {
  document.getElementById("calendar-prev")?.addEventListener("click", () => {
    state.calendarMonth = new Date(state.calendarMonth.getFullYear(), state.calendarMonth.getMonth()-1, 1);
    renderCurrent();
  });
  document.getElementById("calendar-next")?.addEventListener("click", () => {
    state.calendarMonth = new Date(state.calendarMonth.getFullYear(), state.calendarMonth.getMonth()+1, 1);
    renderCurrent();
  });
  document.querySelectorAll("[data-calendar-date]").forEach(button => {
    button.addEventListener("click", () => {
      state.selectedCalendarDate = button.dataset.calendarDate;
      renderCurrent();
    });
    button.addEventListener("contextmenu", async event => {
      event.preventDefault();
      const targetDate = button.dataset.calendarDate;
      const currentDate = String(state.save?.game_date || "2026-07-01").slice(0,10);
      if (targetDate < currentDate) {
        toast("Нельзя перемотать карьеру назад. Выбери текущую или будущую дату.",true);
        return;
      }
      const cells = Array.from(document.querySelectorAll("[data-calendar-date]"));
      const targetIndex = cells.findIndex(cell => cell.dataset.calendarDate === targetDate);
      if (targetIndex < 0) return;
      let currentIndex = cells.findIndex(cell => cell.dataset.calendarDate === currentDate);
      if (currentIndex < 0) currentIndex = targetIndex;
      const direction = targetIndex >= currentIndex ? 1 : -1;
      for (let index = currentIndex; index !== targetIndex + direction; index += direction) {
        cells.forEach((cell, cellIndex) => cell.classList.toggle("selected", cellIndex === index));
        state.selectedCalendarDate = cells[index].dataset.calendarDate;
        if (index !== targetIndex) await new Promise(resolve => setTimeout(resolve, 24));
      }
      button.disabled = true;
      try {
        const result = await api('/api/game/advance-to-date?target_date=' + encodeURIComponent(targetDate), {
          method: 'POST', body: '{}'
        });
        if (state.save) state.save.game_date = result.game_date;
        const ownMatch = result.manager_result || (result.results || []).slice(-1)[0];
        if (ownMatch) {
          toast(ownMatch.home + ' ' + ownMatch.home_score + ':' + ownMatch.away_score + ' ' + ownMatch.away);
        } else {
          toast('Дата обновлена: ' + dateLabel(targetDate) + '. Твой клуб в этот день не играл.');
        }
        await renderCurrent();
      } catch (err) {
        toast(err.message,true);
        await renderCurrent();
      }
    });
  });
  document.querySelectorAll("[data-fixture-id]").forEach(button => {
    button.addEventListener("click", () => showMatchDetails(button.dataset.fixtureId));
  });
}


function tournamentMark(name, logo) {
  const safe = typeof logo === 'string' && /^https:\/\//i.test(logo) ? logo : '';
  return `<span class="tournament-mark"><span>${esc(initials(name))}</span>${safe ? `<img src="${esc(safe)}" alt="" loading="lazy" decoding="async" referrerpolicy="no-referrer" onerror="this.hidden=true">` : ''}</span>`;
}
function matchStatRow(label, homeValue, awayValue, suffix = '') {
  const left = Number(homeValue || 0), right = Number(awayValue || 0);
  const leftWidth = left + right > 0 ? Math.max(4, left / (left + right) * 100) : 50;
  const rightWidth = 100 - leftWidth;
  return `<div class="match-stat-row">
    <b class="home-stat">${esc(homeValue ?? '—')}${suffix}</b>
    <span class="stat-track"><i style="width:${leftWidth}%"></i><i style="width:${rightWidth}%"></i></span>
    <span class="stat-name">${esc(label)}</span>
    <b class="away-stat">${esc(awayValue ?? '—')}${suffix}</b>
  </div>`;
}
async function showMatchDetails(fixtureId) {
  try {
    const data = await api('/api/matches/' + encodeURIComponent(fixtureId));
    document.getElementById('match-detail-modal')?.remove();
    const fixture = data.fixture || {};
    const stats = data.stats;
    const home = stats?.home || {};
    const away = stats?.away || {};
    const players = data.players || [];
    const events = data.events || [];
    const hasStats = Boolean(data.stats_available);
    const timelineLabels = {
      goal: 'ГОЛ',
      penalty_goal: 'ГОЛ С ПЕНАЛЬТИ',
      own_goal: 'АВТОГОЛ',
      yellow_card: 'ЖЁЛТАЯ КАРТОЧКА',
      red_card: 'КРАСНАЯ КАРТОЧКА',
      injury: 'ТРАВМА',
      substitution: 'ЗАМЕНА',
      penalty_miss: 'НЕЗАБИТЫЙ ПЕНАЛЬТИ',
      var: 'VAR'
    };
    const timeline = events.map(event => {
      const detail = event.detail || {};
      const eventTitle = detail.name || detail.injury || detail.reason || timelineLabels[event.event_type] || event.event_type;
      const assist = event.assist_name ? ' · пас: ' + esc(event.assist_name) : '';
      const days = detail.days_out ? ' · выбыл на ' + detail.days_out + ' дн.' : '';
      return `<div class="match-timeline-event event-${esc(event.event_type)}">
        <b>${Number(event.minute || 0)}'${event.added_time ? '+' + event.added_time : ''}</b>
        <span><strong>${esc(timelineLabels[event.event_type] || eventTitle)}</strong>
        <small>${esc(event.player_name || event.club_name || '')}${assist}${days}</small></span>
        <em>${esc(event.club_name || '')}</em>
      </div>`;
    }).join('');
    const playerRows = players.map(player => `<tr class="${player.is_mvp ? 'mvp-row' : ''}">
      <td>${player.is_mvp ? '<b class="mvp-mark">MVP</b>' : ''}${esc(player.name)}</td>
      <td>${esc(player.club_name)}</td>
      <td><b class="rating">${Number(player.rating).toFixed(1)}</b></td>
      <td>${player.minutes_played}'</td>
      <td>${player.goals}</td><td>${player.assists}</td><td>${player.shots}</td>
      <td>${player.passes}</td><td>${player.accurate_passes}</td>
      <td>${player.yellow_cards ? '🟨 ' + player.yellow_cards : '—'} ${player.red_cards ? '🟥 ' + player.red_cards : ''}</td>
    </tr>`).join('');
    const modal = document.createElement('div');
    modal.id = 'match-detail-modal';
    modal.className = 'match-modal-backdrop';
    modal.innerHTML = `<section class="match-modal panel">
      <button type="button" class="modal-close" id="close-match-modal" aria-label="Закрыть">×</button>
      <div class="eyebrow">${esc(fixture.tournament_name || 'ТУРНИР')} · ${dateLabel(fixture.match_date)}</div>
      <div class="match-modal-scoreline">
        <div>${crest(fixture.home_name,fixture.home_logo,'large')}<b>${esc(fixture.home_name)}</b></div>
        <strong>${fixture.status === 'completed' ? fixture.home_score + ' : ' + fixture.away_score : '— : —'}</strong>
        <div>${crest(fixture.away_name,fixture.away_logo,'large')}<b>${esc(fixture.away_name)}</b></div>
      </div>
      ${data.historical_estimate ? '<div class="catalog-note estimate-note">Историческая реконструкция статистики. Итог матча сохранён, индивидуальные показатели и рейтинг рассчитаны приблизительно.</div>' : ''}
      ${!hasStats ? '<div class="empty-state"><strong>Матч ещё не сыгран</strong>После симуляции появятся события, рейтинги и полная статистика.</div>' : ''}
      ${hasStats ? `<section class="match-modal-section"><h3>Статистика матча</h3>
        ${matchStatRow('Удары',home.shots,away.shots)}
        ${matchStatRow('В створ',home.shots_on_target,away.shots_on_target)}
        ${matchStatRow('Передачи',home.passes,away.passes)}
        ${matchStatRow('Точность передач',home.pass_accuracy,away.pass_accuracy,'%')}
        ${matchStatRow('Ожидаемые голы xG',home.xg,away.xg)}
        ${matchStatRow('Владение',home.possession,away.possession,'%')}
        ${matchStatRow('Жёлтые карточки',home.yellow_cards,away.yellow_cards)}
        ${matchStatRow('Красные карточки',home.red_cards,away.red_cards)}
        ${matchStatRow('Офсайды',home.offsides,away.offsides)}
        ${matchStatRow('Угловые',home.corners,away.corners)}
        ${matchStatRow('Фолы',home.fouls,away.fouls)}
      </section>
      <section class="match-modal-section"><h3>Игроки и оценки</h3><div class="table-wrap"><table class="match-player-table">
        <thead><tr><th>Игрок</th><th>Клуб</th><th>Оценка</th><th>Мин.</th><th>Г</th><th>А</th><th>У</th><th>П</th><th>Точн.</th><th>Карточки</th></tr></thead>
        <tbody>${playerRows || '<tr><td colspan="10">Статистика игроков недоступна</td></tr>'}</tbody>
      </table></div></section>
      <section class="match-modal-section"><h3>Ход матча</h3><div class="match-timeline">${timeline || '<div class="empty-state">События матча не записаны</div>'}</div></section>` : ''}
    </section>`;
    document.body.appendChild(modal);
    document.getElementById('close-match-modal').addEventListener('click', () => modal.remove());
    modal.addEventListener('click', event => { if (event.target === modal) modal.remove(); });
  } catch (error) {
    toast(error.message, true);
  }
}
function renderTournamentStandings(rows) {
  return `<div class="table-wrap"><table><thead><tr><th>#</th><th>Клуб</th><th>И</th><th>В</th><th>Н</th><th>П</th><th>ЗМ</th><th>ПМ</th><th>РМ</th><th>ОЧКИ</th></tr></thead>
    <tbody>${(rows || []).map((r,i)=>`<tr class="${r.name===state.save?.club_name?'me-row':''}">
      <td>${i+1}</td><td><div class="team-cell">${crest(r.name,r.logo_url)}${esc(r.name)}</div></td>
      <td>${r.played}</td><td>${r.won}</td><td>${r.drawn}</td><td>${r.lost}</td><td>${r.goals_for}</td><td>${r.goals_against}</td><td>${r.goal_difference}</td><td><b>${r.points}</b></td>
    </tr>`).join('') || '<tr><td colspan="10">Таблица пока пустая</td></tr>'}</tbody></table></div>`;
}
function renderTournamentPlayers(players) {
  return `<div class="table-wrap"><table class="tournament-stats-table"><thead><tr>
    <th>Игрок</th><th>Клуб</th><th>Матчи</th><th>Ср. оценка</th><th>Г</th><th>А</th><th>Г+А</th><th>MVP</th><th>ЖК</th><th>КК</th><th>Сухие</th>
  </tr></thead><tbody>${(players || []).map(player=>`<tr>
    <td><b>${esc(player.name)}</b><div class="data-source">${esc(player.position)}</div></td>
    <td>${esc(player.club_name)}</td><td>${player.appearances}</td><td><b class="rating">${Number(player.average_rating || 0).toFixed(2)}</b></td>
    <td>${player.goals}</td><td>${player.assists}</td><td><b>${player.goal_contributions}</b></td><td>${player.mvp}</td><td>${player.yellow_cards}</td><td>${player.red_cards}</td><td>${player.clean_sheets}</td>
  </tr>`).join('') || '<tr><td colspan="11">Статистика появится после первых матчей</td></tr>'}</tbody></table></div>`;
}
function renderTable(tournaments, detail = null) {
  if (!detail) {
    const cards = (tournaments || []).map(t => `<button type="button" class="competition-card" data-tournament="${esc(t.id)}">
      ${tournamentMark(t.name,t.logo_url)}
      <span><b>${esc(t.name)}</b><small>${esc(t.country || t.continent || 'Турнир')} · ${esc(t.season)}</small>
      <em>${t.teams} команд · ${t.played_fixtures}/${t.fixtures} матчей</em></span><i>Открыть →</i>
    </button>`).join('');
    return `${pageHead('СОРЕВНОВАНИЯ','Таблицы','Выбери турнир, чтобы открыть таблицу и подробную статистику.')}
      <section class="panel"><div class="competition-grid">${cards || '<div class="empty-state">В этом сезоне пока нет турниров</div>'}</div></section>`;
  }
  const t = detail.tournament || {};
  const totals = detail.totals || {};
  const teamCount = (tournaments || []).find(item => String(item.id) === String(t.id))?.teams || '';
  const topGoals = [...(detail.teams || [])].sort((a,b)=>b.goals-a.goals).slice(0,5);
  const topTeamsRating = [...(detail.teams || [])].filter(team=>team.average_rating!=null)
    .sort((a,b)=>b.average_rating-a.average_rating).slice(0,5);
  return `${pageHead('СОРЕВНОВАНИЯ',t.name || 'Турнир',t.season || state.save?.season || '',
      '<button type="button" class="btn-secondary" id="tournament-back">← Все турниры</button>')}
    <section class="panel tournament-hero">
      ${tournamentMark(t.name,t.logo_url)}
      <div><h2>${esc(t.name)}</h2><span>${esc(t.country || t.continent || '')} · ${esc(t.season || '')}</span></div>
      <div class="tournament-totals"><b>${totals.played_matches || 0}/${totals.total_matches || 0}</b><small>матчей сыграно</small><b>${totals.goals || 0}</b><small>голов</small></div>
    </section>
    <section class="panel"><div class="panel-head"><h3>Турнирная таблица</h3><span>${teamCount} КОМАНД</span></div>
      ${renderTournamentStandings(detail.standings)}
    </section>
    <section class="panel"><div class="panel-head"><h3>Статистика игроков</h3><span>СРЕДНЯЯ ОЦЕНКА · G+A · MVP</span></div>
      ${renderTournamentPlayers(detail.players)}
    </section>
    <div class="tournament-analytics">
      <section class="panel"><h3>Больше всего голов</h3>${topGoals.map((team,index)=>`<div class="analytics-row"><b>${index+1}</b>${crest(team.name,team.logo_url)}<span>${esc(team.name)}</span><strong>${team.goals}</strong></div>`).join('') || '<div class="empty-state">Пока нет голов</div>'}</section>
      <section class="panel"><h3>Высший средний рейтинг</h3>${topTeamsRating.map((team,index)=>`<div class="analytics-row"><b>${index+1}</b>${crest(team.name,team.logo_url)}<span>${esc(team.name)}</span><strong>${Number(team.average_rating).toFixed(2)}</strong></div>`).join('') || '<div class="empty-state">Рейтинги появятся после матчей</div>'}</section>
    </div>`;
}
async function renderCurrent() {
  const tab = state.tab;
  const titles = {home:'Обзор',squad:'Состав',tactics:'Тактика',fixtures:'Календарь',table:'Таблицы'};
  const title = titles[tab] || 'SM27';
  const cached = Object.prototype.hasOwnProperty.call(state.tabCache, tab);
  if (!cached) {
    shell(pageHead('ЦЕНТР УПРАВЛЕНИЯ', 'Загружаем ' + title.toLowerCase(), 'Получаем данные карьеры…') +
      '<section class="panel"><div class="empty-state"><strong>Загрузка…</strong>Загружаем данные карьеры…</div></section>', title);
  }
  try {
    if (tab === 'home') {
      const data = await loadTabData('home', () => api('/api/dashboard'));
      state.save = data.save;
      shell(renderHome(data), 'Обзор');
      document.getElementById('advance-game')?.addEventListener('click', advanceGame);
      document.querySelectorAll('[data-nav="table"]').forEach(button => button.addEventListener('click',()=>{state.tab='table';renderCurrent();}));
    } else if (tab === 'squad') {
      const players = await loadTabData('squad', () => api('/api/squad'));
      state.squad = players;
      shell(renderSquad(players), 'Состав');
      document.querySelectorAll('[data-player-details]').forEach(row => row.addEventListener('click', () => showPlayerDetails(row.dataset.playerDetails)));
    } else if (tab === 'tactics') {
      const data = await loadTabData('tactics', async () => {
        const [players, tactics] = await Promise.all([
          loadTabData('squad', () => api('/api/squad')),
          api('/api/tactics')
        ]);
        return {players, tactics};
      });
      state.squad = data.players;
      state.tactics = data.tactics;
      ensureTacticState(data.players, data.tactics);
      shell(renderTactics(data.players, data.tactics), 'Тактика');
      setupTacticsInteractions();
    } else if (tab === 'fixtures') {
      const rows = await loadTabData('fixtures', () => api('/api/fixtures?limit=400'));
      state.fixtures = rows;
      shell(renderFixtures(rows), 'Календарь');
      setupCalendarInteractions();
    } else if (tab === 'table') {
      const rows = await loadTabData('tournaments', () => api('/api/tournaments'));
      let detail = null;
      if (state.selectedTournamentId) {
        detail = await loadTabData(
          'tournament:' + state.selectedTournamentId,
          () => api('/api/tournaments/' + encodeURIComponent(state.selectedTournamentId))
        );
      }
      shell(renderTable(rows, detail), 'Таблицы');
      document.querySelectorAll('[data-tournament]').forEach(button => button.addEventListener('click', () => {
        state.selectedTournamentId = button.dataset.tournament;
        renderCurrent();
      }));
      document.getElementById('tournament-back')?.addEventListener('click', () => {
        state.selectedTournamentId = null;
        renderCurrent();
      });
    }
    if (state.save && !state.preloadStarted) void preloadCareerTabs();
  } catch (err) {
    if (err.message.includes('Сохранение не найдено')) { state.save = null; state.cacheEpoch += 1; state.tabCache = {}; await loadClubPage(); }
    else toast(err.message, true);
  }
}
async function saveTactics() {
  const starting_xi = state.tacticSlots.filter(Boolean);
  const bench = state.tacticBench.filter(id => !starting_xi.includes(id)).slice(0,9);
  if (starting_xi.length !== 11) { toast('На поле должно быть 11 игроков',true); return; }
  if (bench.length < 5) { toast('В запасе должно быть минимум 5 игроков',true); return; }
  const button=document.getElementById('save-tactics'); if(button){button.disabled=true;button.textContent='Сохраняем…';}
  try {
    const formation=document.getElementById('formation').value;
    const style={...state.tacticSettings,reserve_order:currentReserveIds(),slot_roles:formationSlots(formation).map((slot,index)=>({player_id:starting_xi[index],role:slot.role}))};
    await api('/api/tactics',{method:'PUT',body:JSON.stringify({formation,mentality:'balanced',style,starting_xi,bench})});
    toast('Тактика сохранена'); await renderCurrent();
  } catch(err){toast(err.message,true);if(button){button.disabled=false;button.textContent='Сохранить';}}
}
async function advanceGame() {
  const button = document.getElementById('advance-game'); if(button){button.disabled=true;button.textContent='Симулируем матчи…';}
  try {
    const result = await api('/api/game/advance',{method:'POST',body:'{}'});
    const ownMatch = result.manager_result || (result.results || [])[0];
    if (ownMatch) toast(ownMatch.home + ' ' + ownMatch.home_score + ':' + ownMatch.away_score + ' ' + ownMatch.away);
    else if (result.new_season) toast('Начался новый сезон ' + result.new_season);
    else toast('Тур сыгран. Твой клуб в этом туре не играл.');
    state.tab='home'; await renderCurrent();
  } catch(err){toast(err.message,true);if(button){button.disabled=false;button.textContent='Сыграть тур →';}}
}
async function logout() {
  try { await api('/api/auth/logout',{method:'POST',body:'{}'}); } catch (_) { /* clear local screen anyway */ }
  state.manager=null;state.save=null;state.selectedTournamentId=null;renderAuth('login');
}
async function start() {
  try {
    const me = await api('/api/me'); state.manager=me.manager; state.save=me.save;
    if (!state.save) { state.selectedTournamentId=null; await loadClubPage(); return; }
    state.tab='home'; await renderCurrent();
  } catch (_) { renderAuth('login'); }
}
start();
