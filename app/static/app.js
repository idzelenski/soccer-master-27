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
  if (!window.confirm('Начать новую карьеру? Текущее сохранение будет архивировано. Все игровые параметры новой карьеры создадутся заново.')) return;
  const button=document.getElementById('restart-career'); if(button) button.disabled=true;
  try {
    await api('/api/saves/restart',{method:'POST',body:'{}'});
    state.save=null;state.tab='home';state.tactics=null;state.squad=[];state.fixtures=[];
    await loadClubPage();
    toast('Карьера завершена. Выбери новый клуб.');
  } catch(err){toast(err.message,true);if(button)button.disabled=false;}
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


const FORMATIONS = [
  "3-1-4-2","3-4-1-2","3-4-2-1","3-4-3","3-4-3 Flat","3-5-2",
  "4-1-2-1-2","4-1-2-1-2 Narrow","4-1-2-1-2 Wide","4-1-3-2","4-1-4-1",
  "4-2-1-3","4-2-2-2","4-2-3-1","4-2-3-1 Narrow","4-2-3-1 Wide",
  "4-2-4","4-3-1-2","4-3-2-1","4-3-3","4-3-3 Attack","4-3-3 Defend",
  "4-3-3 Flat","4-3-3 Holding","4-4-1-1 Midfield","4-4-2","4-4-2 Holding",
  "4-5-1","4-5-1 Attack","4-5-1 Flat","5-2-1-2","5-2-3","5-3-2",
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
  "4-4-1-1 Midfield":[["GK"],["LB","CB","CB","RB"],["LM","CM","CM","RM"],["CAM"],["ST"]],
  "4-4-2":[["GK"],["LB","CB","CB","RB"],["LM","CM","CM","RM"],["ST","ST"]],
  "4-5-1":[["GK"],["LB","CB","CB","RB"],["LM","CM","CDM","CM","RM"],["ST"]],
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
  const remaining = [...players];
  const starters = [];
  for (const slot of formationSlots(formation)) {
    if (!remaining.length) break;
    remaining.sort((a,b) => (b.overall + positionPenalty(b,slot.role)) - (a.overall + positionPenalty(a,slot.role)));
    starters.push(remaining.shift());
  }
  return {starters,remaining};
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
  state.tacticSlots = starters.slice(0,11).map(p => String(p.id));
  const savedBench = (tactics.bench || []).map(id => String(id)).filter(id => existing.has(id) && !state.tacticSlots.includes(id));
  state.tacticBench = savedBench.slice(0,9);
  const fillBench = rest.filter(p => !state.tacticBench.includes(String(p.id))).sort((a,b)=>b.overall-a.overall);
  while(state.tacticBench.length<7 && fillBench.length) state.tacticBench.push(String(fillBench.shift().id));
  state.tacticSettings = {
    build_up: "balanced", chance_creation: "balanced", pressing: "on_mistake",
    defensive_approach: "balanced", width: 50, depth: 55, tempo: "balanced",
    focus: "balanced", player_roles: {}, ...(tactics.style || {})
  };
  state.tacticSettings.player_roles ||= {};
  state.selectedTacticSlot = null;
}
function playerTag(player, slotIndex = null) {
  if (!player) return "";
  return `<div class="pitch-player-card" draggable="true" data-player-id="${esc(player.id)}" ${slotIndex !== null ? `data-pitch-slot="${slotIndex}"` : ""}>
    <b>${player.overall}</b><small>${esc(player.name.split(" ").slice(-1)[0])}</small>
  </div>`;
}
function renderTactics(players, tactics) {
  const formation = tactics.formation || "4-3-3";
  const slots = formationSlots(formation);
  const byId = new Map(players.map(player => [String(player.id),player]));
  const pitchPlayers = slots.map((slot,index) => {
    const player = byId.get(state.tacticSlots[index]);
    const selected = state.selectedTacticSlot === index;
    const rating = player ? player.overall + positionPenalty(player,slot.role) : null;
    return `<button class="pitch-player ${selected ? "selected" : ""} ${player ? "" : "empty"}" style="left:${slot.left}%;top:${slot.top}%" data-pitch-slot="${index}" data-drop-slot="${index}" draggable="${Boolean(player)}" ${player ? `data-player-id="${esc(player.id)}"` : ""}>
      <strong>${player ? rating : "+"}</strong><small>${esc(slot.role)}</small><em>${player ? esc(player.name.split(" ").slice(-1)[0]) : "Выбрать"}</em>
    </button>`;
  }).join("");
  const benchIds = new Set(state.tacticBench);
  const bench = state.tacticBench.map(id => {
    const p=byId.get(id); return p ? `<button class="tactic-player-row bench-player" data-player-id="${esc(id)}"><b>${p.overall}</b><span>${esc(p.name)}<small>${esc(p.position)} · запас</small></span></button>` : "";
  }).join("");
  const reserves = players.filter(p => !state.tacticSlots.includes(String(p.id)) && !benchIds.has(String(p.id)))
    .sort((a,b)=>b.overall-a.overall)
    .map(p=>`<button class="tactic-player-row reserve-player" data-player-id="${esc(p.id)}"><b>${p.overall}</b><span>${esc(p.name)}<small>${esc(p.position)} · резерв</small></span></button>`).join("");
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
        <div class="panel-head"><h3>Тактическое поле</h3><span>Нажми на двух игроков, чтобы поменять местами · можно перетаскивать</span></div>
        <div class="pitch pitch-football" id="tactic-pitch"><div class="pitch-line"></div><div class="pitch-box pitch-box-top"></div><div class="pitch-box pitch-box-bottom"></div><div class="pitch-circle"></div>${pitchPlayers}</div>
        <div class="catalog-note"><span>ⓘ</span><span>ОВР на поле учитывает позиционный штраф. Родная и дополнительная позиция не снижают рейтинг. Позиция вратаря и полевого игрока — штраф 40.</span></div>
        <div class="squad-bench-block"><div class="panel-head"><h3>Запас</h3><span>от 5 до 9 игроков</span></div><div class="tactic-roster-grid" id="tactic-bench">${bench || '<p class="empty-state">Скамейка пуста</p>'}</div></div>
        <div class="squad-bench-block"><div class="panel-head"><h3>Резерв</h3><span>Остальные футболисты</span></div><div class="tactic-roster-grid reserves-list" id="tactic-reserves">${reserves || '<p class="empty-state">В резерве пока нет игроков</p>'}</div></div>
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
function swapTacticPlayers(slotIndex, playerId) {
  const id=String(playerId);
  const current=state.tacticSlots[slotIndex];
  const fromSlot=state.tacticSlots.indexOf(id);
  if(fromSlot>=0){
    state.tacticSlots[slotIndex]=id;
    state.tacticSlots[fromSlot]=current || null;
  }else{
    state.tacticSlots[slotIndex]=id;
    state.tacticBench=state.tacticBench.filter(x=>x!==id);
    if(current && state.tacticBench.length<9 && !state.tacticBench.includes(current)) state.tacticBench.push(current);
  }
  state.selectedTacticSlot=null;
  renderCurrent();
}
function setupTacticsInteractions() {
  document.getElementById("formation")?.addEventListener("change",event=>{
    const result=optimiseLineup(state.squad,event.target.value);
    state.tacticSlots=result.starters.map(p=>String(p.id));
    state.tacticBench=result.remaining.slice(0,7).map(p=>String(p.id));
    state.tacticSettings.formation=event.target.value;
    renderCurrent();
  });
  document.getElementById("auto-lineup")?.addEventListener("click",()=>{
    const formation=document.getElementById("formation").value;
    const result=optimiseLineup(state.squad,formation);
    state.tacticSlots=result.starters.map(p=>String(p.id));
    state.tacticBench=result.remaining.slice(0,7).map(p=>String(p.id));
    renderCurrent();
  });
  document.querySelectorAll("[data-pitch-slot]").forEach(button=>button.addEventListener("click",()=>{
    const slot=Number(button.dataset.pitchSlot);
    if(state.selectedTacticSlot!==null && state.selectedTacticSlot!==slot){
      const a=state.tacticSlots[state.selectedTacticSlot], b=state.tacticSlots[slot];
      state.tacticSlots[slot]=a; state.tacticSlots[state.selectedTacticSlot]=b;
      state.selectedTacticSlot=null; renderCurrent(); return;
    }
    state.selectedTacticSlot=state.selectedTacticSlot===slot?null:slot; renderCurrent();
  }));
  document.querySelectorAll(".tactic-player-row").forEach(button=>button.addEventListener("click",()=>{
    if(state.selectedTacticSlot===null){
      toast("Сначала выбери позицию на поле",true); return;
    }
    swapTacticPlayers(state.selectedTacticSlot,button.dataset.playerId);
  }));
  const pitch=document.getElementById("tactic-pitch");
  pitch?.querySelectorAll("[data-pitch-slot]").forEach(slot=>{
    slot.addEventListener("dragstart",event=>{event.dataTransfer.setData("text/player-id",state.tacticSlots[Number(slot.dataset.pitchSlot)]||"");});
  });
  document.querySelectorAll("[data-player-id]").forEach(node=>{
    node.addEventListener("dragstart",event=>event.dataTransfer.setData("text/player-id",node.dataset.playerId));
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
      const key=id.replace(/-([a-z])/g,(_,c)=>c.toUpperCase()).replace(/^buildUp$/,"build_up").replace(/^chanceCreation$/,"chance_creation").replace(/^defensiveApproach$/,"defensive_approach");
      state.tacticSettings[key]=event.target.value;
    });
  });
  document.getElementById("tactic-width")?.addEventListener("input",event=>{
    state.tacticSettings.width=Number(event.target.value);document.getElementById("width-value").textContent=event.target.value;
  });
  document.getElementById("tactic-depth")?.addEventListener("input",event=>{
    state.tacticSettings.depth=Number(event.target.value);document.getElementById("depth-value").textContent=event.target.value;
  });
  document.querySelectorAll("[data-player-role]").forEach(node=>node.addEventListener("change",event=>{
    state.tacticSettings.player_roles[event.target.dataset.playerRole]=event.target.value;
  }));
  document.getElementById("save-tactics")?.addEventListener("click",saveTactics);
}
function renderFixtures(rows) {
  if(!rows.length) return `${pageHead("РАСПИСАНИЕ","Календарь","Календарь сезона 2026/27.")}<section class="panel"><div class="empty-state">Матчей пока нет</div></section>`;
  if(!state.calendarMonth){
    const date=new Date(state.save?.game_date || "2026-07-01T12:00:00");
    state.calendarMonth=new Date(date.getFullYear(),date.getMonth(),1);
  }
  const month=new Date(state.calendarMonth.getFullYear(),state.calendarMonth.getMonth(),1);
  const monthLabel=month.toLocaleDateString("ru-RU",{month:"long",year:"numeric"});
  const keyDate=value=>{const d=new Date(value);return `${d.getFullYear()}-${String(d.getMonth()+1).padStart(2,"0")}-${String(d.getDate()).padStart(2,"0")}`;};
  const byDate=new Map();
  rows.forEach(row=>{const k=keyDate(row.match_date);if(!byDate.has(k))byDate.set(k,[]);byDate.get(k).push(row);});
  const offset=(month.getDay()+6)%7;
  const days=new Date(month.getFullYear(),month.getMonth()+1,0).getDate();
  const cells=[];
  for(let i=0;i<offset;i++) cells.push('<div class="calendar-empty"></div>');
  for(let day=1;day<=days;day++){
    const key=`${month.getFullYear()}-${String(month.getMonth()+1).padStart(2,"0")}-${String(day).padStart(2,"0")}`;
    const events=byDate.get(key)||[];
    cells.push(`<button class="calendar-day ${state.selectedCalendarDate===key?"selected":""} ${events.length?"has-event":""}" data-calendar-date="${key}">
      <b>${day}</b>${events.length?`<span>${events.length} МАТЧ</span>`:""}
    </button>`);
  }
  const selected=state.selectedCalendarDate || keyDate(state.save?.game_date || "2026-07-01T12:00:00");
  const selectedRows=byDate.get(selected)||[];
  const selectedContent=selectedRows.length?selectedRows.map(f=>`<div class="calendar-match-row">
    <small>ТУР ${f.matchday||"—"} · ${f.status==="completed"?"СЫГРАН":"ЗАПЛАНИРОВАН"}</small>
    <b>${esc(f.home_name)} <span>${f.status==="completed"?`${f.home_score} : ${f.away_score}`:"— : —"}</span> ${esc(f.away_name)}</b>
  </div>`).join(""):'<div class="empty-state">На выбранную дату матчей нет</div>';
  const weekdays=["ПН","ВТ","СР","ЧТ","ПТ","СБ","ВС"].map(d=>`<span>${d}</span>`).join("");
  return `${pageHead("СЕЗОН 2026/27","Календарь","Месячный календарь матчей и событий твоей карьеры.")}
    <div class="calendar-layout panel">
      <section class="calendar-main">
        <div class="calendar-month-nav"><button class="btn-quiet" id="calendar-prev">‹</button><h2>${monthLabel}</h2><button class="btn-quiet" id="calendar-next">›</button></div>
        <div class="calendar-weekdays">${weekdays}</div><div class="calendar-grid">${cells.join("")}</div>
        <div class="calendar-legend"><span class="event-dot"></span> Матч лиги <span class="badge-soft">Сезон 2026/27</span></div>
      </section>
      <aside class="calendar-selected"><div class="eyebrow">ВЫБРАННЫЙ ДЕНЬ</div><h3>${dateLabel(selected+"T12:00:00")}</h3>${selectedContent}</aside>
    </div>`;
}
function setupCalendarInteractions() {
  document.getElementById("calendar-prev")?.addEventListener("click",()=>{state.calendarMonth=new Date(state.calendarMonth.getFullYear(),state.calendarMonth.getMonth()-1,1);renderCurrent();});
  document.getElementById("calendar-next")?.addEventListener("click",()=>{state.calendarMonth=new Date(state.calendarMonth.getFullYear(),state.calendarMonth.getMonth()+1,1);renderCurrent();});
  document.querySelectorAll("[data-calendar-date]").forEach(button=>button.addEventListener("click",()=>{
    state.selectedCalendarDate=button.dataset.calendarDate;renderCurrent();
  }));
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
      document.querySelectorAll('[data-player-details]').forEach(row => row.addEventListener('click', () => showPlayerDetails(row.dataset.playerDetails)));
    } else if (state.tab === 'tactics') {
      const [players,tactics] = await Promise.all([api('/api/squad'),api('/api/tactics')]);
      state.squad=players; state.tactics=tactics; ensureTacticState(players,tactics);
      shell(renderTactics(players,tactics),'Тактика'); setupTacticsInteractions();
    } else if (state.tab === 'fixtures') {
      const rows = await api('/api/fixtures?limit=400'); state.fixtures=rows; shell(renderFixtures(rows),'Календарь'); setupCalendarInteractions();
    } else if (state.tab === 'table') {
      const rows = await api('/api/standings'); shell(renderTable(rows),'Таблица');
    }
  } catch (err) {
    if (err.message.includes('Сохранение не найдено')) { state.save=null; await loadClubPage(); }
    else toast(err.message,true);
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
    const style={...state.tacticSettings,slot_roles:formationSlots(formation).map((slot,index)=>({player_id:starting_xi[index],role:slot.role}))};
    await api('/api/tactics',{method:'PUT',body:JSON.stringify({formation,mentality:'balanced',style,starting_xi,bench})});
    toast('Тактика сохранена'); await renderCurrent();
  } catch(err){toast(err.message,true);if(button){button.disabled=false;button.textContent='Сохранить';}}
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
