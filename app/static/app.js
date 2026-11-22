const app = document.getElementById('app');
const toastRoot = document.getElementById('toast-root');
const state = { manager: null, save: null, summary: null, clubs: [], leagues: [], tab: 'home', squad: [], fixtures: [], tactics: null, search: '', league: '', clubTotal: 0, clubOffset: 0, calendarMonth: null, selectedCalendarDate: null, tacticSlots: [], tacticBench: [], selectedTacticSlot: null, tacticSettings: {} };

const esc = (value) => String(value ?? '').replace(/[&<>"']/g, (ch) => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[ch]));
const initials = (value) => String(value || 'SM').split(/[\s-]+/).slice(0,2).map((part) => part[0] || '').join('').toUpperCase();
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
    const message = response.status >= 500
      ? (data.detail || 'Сервер временно не смог выполнить действие. Данные сохранены.')
      : (data.detail || `Не удалось выполнить запрос (${response.status}).`);
    throw new Error(message);
  }
  return data;
}
function crest(name, logo) {
  const fallback = esc(initials(name));
  if (logo && String(logo).startsWith('https://')) {
    return `<div class="crest"><span>${fallback}</span><img src="${esc(logo)}" alt="Эмблема ${esc(name)}" loading="lazy" decoding="async" referrerpolicy="no-referrer" onerror="this.remove()"></div>`;
  }
  return `<div class="crest">${fallback}</div>`;
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
    api('/api/catalog/summary'), api('/api/catalog/leagues'), api('/api/catalog/clubs?limit=200')
  ]);
  state.summary = summary; state.leagues = leagues; state.clubs = clubsPage.items;
  state.clubTotal = clubsPage.total; state.clubOffset = clubsPage.items.length;
  renderClubSelection();
}
function renderClubSelection() {
  const clubCards = state.clubs.map((club) => `
    <button class="club-card" data-club="${esc(club.source_id)}">
      ${crest(club.club_name, club.logo_url)}
      <span><b>${esc(club.club_name)}</b><small>${esc(club.country || '—')} · ${esc(club.league_name || 'Лига')}</small><em>${club.has_squad ? `Состав: ${club.squad_count} игроков` : 'Игровой состав будет сформирован'}</em></span>
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
  const query = new URLSearchParams({limit:'200',q:state.search,league:state.league});
  try {
    query.set('offset','0');
    const data = await api(`/api/catalog/clubs?${query.toString()}`); state.clubs = data.items; state.clubTotal = data.total; state.clubOffset = data.items.length;
    const node = document.getElementById('club-grid'); if (!node) return;
    node.innerHTML = state.clubs.map((club) => `<button class="club-card" data-club="${esc(club.source_id)}">${crest(club.club_name,club.logo_url)}<span><b>${esc(club.club_name)}</b><small>${esc(club.country||'—')} · ${esc(club.league_name||'Лига')}</small><em>${club.has_squad?`Состав: ${club.squad_count} игроков`:'Игровой состав будет сформирован'}</em></span></button>`).join('') || '<div class="empty-state">По запросу ничего не найдено.</div>';
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
    const query = new URLSearchParams({limit:'200',offset:String(state.clubOffset),q:state.search,league:state.league});
    const data = await api(`/api/catalog/clubs?${query.toString()}`);
    state.clubs.push(...data.items); state.clubOffset += data.items.length; state.clubTotal = data.total;
    const node = document.getElementById('club-grid');
    node.insertAdjacentHTML('beforeend', data.items.map((club) => `<button class="club-card" data-club="${esc(club.source_id)}">${crest(club.club_name,club.logo_url)}<span><b>${esc(club.club_name)}</b><small>${esc(club.country||'—')} · ${esc(club.league_name||'Лига')}</small><em>${club.has_squad?`Состав: ${club.squad_count} игроков`:'Игровой состав будет сформирован'}</em></span></button>`).join(''));
    data.items.forEach(club => node.querySelector(`[data-club="${CSS.escape(club.source_id)}"]`)?.addEventListener('click', () => selectClub(club.source_id)));
    const parent = button.parentElement; if (state.clubOffset >= state.clubTotal) parent.remove(); else { button.disabled=false; button.textContent=`Показать ещё клубы (${state.clubTotal-state.clubOffset})`; }
  } catch(err) { button.disabled=false; button.textContent='Повторить'; toast(err.message,true); }
}
async function selectClub(sourceId) {
  const button = document.querySelector(`[data-club="${CSS.escape(sourceId)}"]`); if (button) button.disabled = true;
  try { await api('/api/saves', {method:'POST',body:JSON.stringify({club_source_id:sourceId,save_name:'Моя карьера'})}); toast('Карьера создана!'); await start(); }
  catch (err) { toast(err.message, true); if (button) button.disabled = false; }
}
function navItems() {
  return [
    ['home','⌂','Обзор'],['squad','♟','Состав'],['tactics','⌖','Тактика'],['fixtures','▦','Календарь'],['table','≡','Таблица']
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
      <div class="nav-label">АККАУНТ</div><nav class="nav-list"><button class="nav-item" id="logout"><span class="nav-ico">↪</span>Выйти</button></nav>
      <div class="sidebar-bottom"><div class="club-mini">${crest(club,state.save?.logo_url)}<span><b>${esc(club)}</b><small>${esc(state.save?.league || 'Сезон 2026/27')}</small></span></div></div>
    </aside>
    <main class="main-area">
      <header class="topbar"><div class="breadcrumb">Карьера <span style="color:#456253"> / </span> <b>${esc(title)}</b></div><div class="top-actions"><div class="season-pill">СЕЗОН 2026 / 27</div><div class="manager-chip"><div class="avatar">${esc(initials(name))}</div><span><b>${esc(name)}</b><small>Главный тренер</small></span></div></div></header>
      ${content}
    </main>
  </div>`;
  document.querySelectorAll('[data-nav]').forEach((button) => button.addEventListener('click', () => { state.tab = button.dataset.nav; renderCurrent(); }));
  document.getElementById('logout').addEventListener('click', logout);
}
function renderHome(data) {
  const save = data.save;
  const match = data.next_match;
  const matchCard = match ? `<section class="panel hero-match">
    <div class="match-top"><span class="live-tag">СЛЕДУЮЩИЙ МАТЧ · ТУР ${esc(match.matchday||'—')}</span><span class="match-date">${dateLabel(match.match_date)}</span></div>
    <div class="match-teams"><div class="match-team"><div class="match-crest">${esc(initials(match.home_name))}</div><b>${esc(match.home_name)}</b><small>${match.is_home?'Хозяева':'Гости'}</small></div><div class="vs">VS</div><div class="match-team"><div class="match-crest">${esc(initials(match.away_name))}</div><b>${esc(match.away_name)}</b><small>${match.is_home?'Гости':'Хозяева'}</small></div></div>
    <div class="match-bottom"><small>Время продолжить сезон</small><button class="btn-primary" id="advance-game">Сыграть тур →</button></div>
  </section>` : `<section class="panel hero-match"><div class="match-top"><span class="live-tag">СЕЗОН</span><span class="match-date">2026 / 27</span></div><div class="empty-state"><strong>Матчи сезона завершены</strong>Новая глава начнётся со следующего сезона.</div></section>`;
  const standingRows = data.standings.slice(0,6).map((row,index) => `<tr class="${row.name===save.club_name?'me-row':''}"><td>${index+1}</td><td><div class="team-cell"><span class="team-dot">${esc(initials(row.name))}</span>${esc(row.name)}</div></td><td>${row.played}</td><td>${row.goal_difference || 0}</td><td><b>${row.points}</b></td></tr>`).join('');
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
    const source = player.profile_source || 'SM27 estimate';
    const valueLabel = player.market_value
      ? money(player.market_value)
      : 'Нет оценки';
    return `<tr class="player-row" data-player-details="${esc(player.id)}">
      <td><span class="rating">${player.overall}</span></td>
      <td><span class="player-name">${esc(player.nationality_flag || '🏳️')} ${esc(player.name)}</span>
        ${player.original_data?.generated ? '<div class="player-source-generated">Игровой игрок SM27</div>' : ''}</td>
      <td><span class="position-tag">${esc(player.position)}</span></td>
      <td>${(player.secondary_positions || []).map(pos => `<span class="secondary-position">${esc(pos)}</span>`).join(' ') || '—'}</td>
      <td>${player.age}</td>
      <td><span class="potential-rating">${player.potential}</span></td>
      <td class="value" title="${esc(source)}">${valueLabel}${player.market_value ? `<div class="data-source">${esc(source)}</div>` : '<div class="data-source">Игровая оценка отсутствует</div>'}</td>
      <td>${player.contract_end ? new Date(player.contract_end).toLocaleDateString('ru-RU',{month:'short',year:'numeric'}) : '—'}</td>
      <td>${money(player.weekly_wage)}<div class="data-source">/ нед.</div></td>
      <td><span class="mini-meter">${player.form ?? 50}</span></td>
      <td><span class="mini-meter">${player.morale ?? 70}</span></td>
    </tr>`;
  }).join('');
  return `${pageHead('ПЕРВАЯ КОМАНДА','Состав',`${players.length} игроков · нажми на игрока, чтобы открыть полный профиль`)}
    <section class="panel">
      <div class="panel-head"><h3>Игроки первой команды</h3><span>OVR / POTENTIAL / VALUE</span></div>
      <div class="table-wrap squad-table-wrap"><table class="squad-table">
        <thead><tr><th>OVR</th><th>ИГРОК</th><th>ПОЗ.</th><th>ДОП. ПОЗ.</th><th>ВОЗР.</th><th>POT</th><th>РЫНОЧНАЯ СТОИМОСТЬ</th><th>КОНТРАКТ</th><th>ЗАРПЛАТА</th><th>ФОРМА</th><th>НАСТРОЙ</th></tr></thead>
        <tbody>${rows || '<tr><td colspan="11">Состав не загружен</td></tr>'}</tbody>
      </table></div>
      <div class="catalog-note" style="margin-top:18px"><span>ⓘ</span><span>Оценки OVR/POT, зарплата, контракт, форма и настрой — игровые параметры SM27. Стоимость Transfermarkt показывается только там, где найдена подтверждённая оценка; остальные суммы будут обозначаться как игровые оценки.</span></div>
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
  const modal = document.createElement('div');
  modal.id = 'player-detail-modal';
  modal.className = 'player-modal-backdrop';
  modal.innerHTML = `
    <section class="player-modal panel">
      <button class="modal-close" id="close-player-modal" aria-label="Закрыть">×</button>
      <div class="player-modal-head">
        <div class="player-modal-flag">${esc(player.nationality_flag || '🏳️')}</div>
        <div><div class="eyebrow">ПРОФИЛЬ ФУТБОЛИСТА</div><h2>${esc(player.name)}</h2><p>${esc(player.nationality || 'Национальность не указана')} · ${player.age} лет · ${esc(player.position)}</p></div>
        <div class="player-modal-ratings"><b>${player.overall}</b><span>OVR</span><b>${player.potential}</b><span>POT</span></div>
      </div>
      <div class="player-modal-grid">
        <div class="player-metric"><small>Дополнительные позиции</small><b>${(player.secondary_positions || []).map(esc).join(' · ') || 'Нет данных'}</b></div>
        <div class="player-metric"><small>Рыночная стоимость</small><b>${money(player.market_value)}</b><em>${esc(player.profile_source || 'SM27 estimate')}</em></div>
        <div class="player-metric"><small>Контракт до</small><b>${player.contract_end ? dateLabel(player.contract_end) : 'Не указано'}</b><em>Игровая оценка, не официальный срок</em></div>
        <div class="player-metric"><small>Зарплата в неделю</small><b>${money(player.weekly_wage)}</b><em>Игровая оценка SM27</em></div>
      </div>
      <div class="player-state-grid">
        <div><small>Тонус</small><b>${player.sharpness ?? 85}%</b><i><span style="width:${player.sharpness ?? 85}%"></span></i></div>
        <div><small>Форма</small><b>${player.form ?? 50}/100</b><i><span style="width:${player.form ?? 50}%"></span></i></div>
        <div><small>Настрой</small><b>${player.morale ?? 70}/100</b><i><span style="width:${player.morale ?? 70}%"></span></i></div>
      </div>
      <div class="panel-head"><h3>Характеристики ${keeper ? 'вратаря' : 'полевого игрока'}</h3><span>ШКАЛА 1–99</span></div>
      <div class="attribute-grid">${bars}</div>
      <div class="catalog-note"><span>ⓘ</span><span>Если у источника нет конкретных характеристик, они сгенерированы игровым движком на основе OVR и позиции. Это не официальные атрибуты EA или Transfermarkt.</span></div>
    </section>`;
  document.body.appendChild(modal);
  document.getElementById('close-player-modal').addEventListener('click', () => modal.remove());
  modal.addEventListener('click', event => { if (event.target === modal) modal.remove(); });
}

function renderTactics(players, tactics) {
  const formations = ['4-3-3','4-2-3-1','4-4-2','3-5-2','3-4-3','5-3-2'];
  const selected = new Set(tactics.starting_xi || []);
  const rows = players.map((player) => `<label class="fixture-row" style="grid-template-columns:25px 1fr 50px;cursor:pointer"><input type="checkbox" class="xi-check" value="${esc(player.id)}" ${selected.has(String(player.id))?'checked':''} style="accent-color:var(--green)" ${selected.size>=11&&!selected.has(String(player.id))?'disabled':''}><span class="fixture-teams">${esc(player.name)}<br><small style="color:var(--muted)">${esc(player.position)} · ${player.age} лет</small></span><span class="rating">${player.overall}</span></label>`).join('');
  const lineup = players.filter(p => selected.has(String(p.id)));
  const pitch = lineup.slice(0,11).map((player,index) => {
    const coords = [[50,91],[18,75],[40,78],[60,78],[82,75],[34,55],[66,55],[18,35],[50,37],[82,35],[50,13]];
    const [left,top] = coords[index]; return `<div class="pitch-player" style="left:${left}%;top:${top}%"><span>${esc(player.position)}</span><small>${esc(player.name.split(' ').slice(-1)[0])}</small></div>`;
  }).join('');
  return `${pageHead('ПЛАН НА МАТЧ','Тактика','Выбери схему и стартовые 11. Состав сохраняется в твоей карьере.')}
    <div class="tactic-layout"><section class="panel"><div class="panel-head"><h3>Тактическая доска</h3><span>${lineup.length}/11 игроков</span></div><div class="pitch"><div class="pitch-line"></div>${pitch}</div><div class="catalog-note"><span>ⓘ</span><span>Игроки отображаются схематично; позиции на поле в этой версии — визуальная расстановка стартового состава.</span></div></section>
    <section class="panel tactic-controls"><div class="panel-head"><h3>Настройки команды</h3></div>
      <div class="form-field"><label>РАССТАНОВКА</label><select id="formation" class="select-input">${formations.map(f=>`<option ${tactics.formation===f?'selected':''}>${f}</option>`).join('')}</select></div>
      <div class="form-field"><label>МЕНТАЛИТЕТ</label><select id="mentality" class="select-input">${[['defensive','Оборонительный'],['balanced','Сбалансированный'],['positive','Позитивный'],['attacking','Атакующий']].map(([v,l])=>`<option value="${v}" ${tactics.mentality===v?'selected':''}>${l}</option>`).join('')}</select></div>
      <div class="panel-head" style="margin:10px 0 0"><h3>Стартовый состав</h3><span>до 11 игроков</span></div>
      <div style="max-height:295px;overflow:auto" id="xi-list">${rows || '<div class="empty-state">Игроков пока нет</div>'}</div>
      <button id="save-tactics" class="btn-primary block">Сохранить тактику</button>
    </section></div>`;
}
function renderFixtures(rows) {
  return `${pageHead('РАСПИСАНИЕ','Календарь','Матчи твоей лиги. Продолжай сезон по игровым турам.')}
    <section class="panel"><div class="panel-head"><h3>Все матчи сезона</h3><span>2026 / 27</span></div>
      ${rows.map(f=>`<div class="fixture-row"><span class="fixture-date">${dateLabel(f.match_date)}<br><span class="badge-soft">Тур ${f.matchday||'—'}</span></span><div class="fixture-teams">${esc(f.home_name)}<br>${esc(f.away_name)}</div><div class="fixture-score">${f.status==='completed'?`${f.home_score} : ${f.away_score}`:'— : —'}</div></div>`).join('') || '<div class="empty-state">Матчей пока нет</div>'}
    </section>`;
}
function renderTable(rows) {
  return `${pageHead('ЧЕМПИОНАТ','Турнирная таблица','Каждый сыгранный тур обновляет положение команд.')}
    <section class="panel"><div class="panel-head"><h3>${esc(state.save?.league || 'Лига')}</h3><span>СЕЗОН 2026 / 27</span></div><div class="table-wrap"><table><thead><tr><th>#</th><th>Клуб</th><th>И</th><th>В</th><th>Н</th><th>П</th><th>ЗМ</th><th>ПМ</th><th>РМ</th><th>ОЧКИ</th></tr></thead><tbody>${rows.map((r,i)=>`<tr class="${r.name===state.save?.club_name?'me-row':''}"><td>${i+1}</td><td><div class="team-cell"><span class="team-dot">${esc(initials(r.name))}</span>${esc(r.name)}</div></td><td>${r.played}</td><td>${r.won}</td><td>${r.drawn}</td><td>${r.lost}</td><td>${r.goals_for}</td><td>${r.goals_against}</td><td>${r.goal_difference||0}</td><td><b>${r.points}</b></td></tr>`).join('') || '<tr><td colspan="10">Таблица пока пустая</td></tr>'}</tbody></table></div></section>`;
}
async function renderCurrent() {
  try {
    if (state.tab === 'home') {
      const data = await api('/api/dashboard'); state.save = data.save; shell(renderHome(data), 'Обзор');
      document.getElementById('advance-game')?.addEventListener('click', advanceGame);
      document.querySelectorAll('[data-nav="table"]').forEach((button) => button.addEventListener('click',()=>{state.tab='table';renderCurrent();}));
    } else if (state.tab === 'squad') {
      const players = await api('/api/squad'); state.squad = players; shell(renderSquad(players), 'Состав');
    } else if (state.tab === 'tactics') {
      const [players,tactics] = await Promise.all([api('/api/squad'),api('/api/tactics')]); state.squad=players;state.tactics=tactics; shell(renderTactics(players,tactics),'Тактика');
      const checks = () => { const checked = [...document.querySelectorAll('.xi-check:checked')]; document.querySelectorAll('.xi-check:not(:checked)').forEach(el=>el.disabled=checked.length>=11); };
      document.querySelectorAll('.xi-check').forEach(el=>el.addEventListener('change',checks));
      document.getElementById('save-tactics').addEventListener('click',saveTactics);
    } else if (state.tab === 'fixtures') {
      const rows = await api('/api/fixtures?limit=80'); state.fixtures=rows; shell(renderFixtures(rows),'Календарь');
    } else if (state.tab === 'table') {
      const rows = await api('/api/standings'); shell(renderTable(rows),'Таблица');
    }
  } catch (err) {
    if (err.message.includes('Сохранение не найдено')) { state.save=null; await loadClubPage(); }
    else toast(err.message,true);
  }
}
async function saveTactics() {
  const starting_xi = [...document.querySelectorAll('.xi-check:checked')].map(el=>el.value);
  try {
    await api('/api/tactics',{method:'PUT',body:JSON.stringify({formation:document.getElementById('formation').value,mentality:document.getElementById('mentality').value,starting_xi,bench:[]})});
    toast('Тактика сохранена'); await renderCurrent();
  } catch(err){toast(err.message,true);}
}
async function advanceGame() {
  const button = document.getElementById('advance-game'); if(button){button.disabled=true;button.textContent='Симулируем матчи…';}
  try {
    const result = await api('/api/game/advance',{method:'POST',body:'{}'});
    const summary = result.results.slice(0,3).map(r=>`${r.home} ${r.home_score}:${r.away_score} ${r.away}`).join(' · ');
    toast(`Тур сыгран. ${summary}`); state.tab='home'; await renderCurrent();
  } catch(err){toast(err.message,true);if(button){button.disabled=false;button.textContent='Сыграть тур →';}}
}
async function logout() {
  try { await api('/api/auth/logout',{method:'POST',body:'{}'}); } catch (_) { /* clear local screen anyway */ }
  state.manager=null;state.save=null;renderAuth('login');
}
async function start() {
  try {
    const me = await api('/api/me'); state.manager=me.manager; state.save=me.save;
    if (!state.save) { await loadClubPage(); return; }
    state.tab='home'; await renderCurrent();
  } catch (_) { renderAuth('login'); }
}
start();
