const app = document.getElementById('app');
const toastRoot = document.getElementById('toast-root');
const state = { manager: null, save: null, summary: null, clubs: [], leagues: [], tab: 'home', squad: [], fixtures: [], tactics: null, search: '', league: '', clubTotal: 0, clubOffset: 0, calendarMonth: null, selectedCalendarDate: null, tacticSlots: [], tacticBench: [], selectedTacticSlot: null, tacticSettings: {}, tacticFormation: '4-3-3' };

const esc = (value) => String(value ?? '').replace(/[&<>"']/g, (ch) => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[ch]));
const initials = (value) => String(value || 'SM').split(/[\s-]+/).slice(0,2).map((part) => part[0] || '').join('').toUpperCase();
function flagImage(code,label='') {
  const value=String(code||'').toLowerCase();
  if(!/^(?:[a-z]{2}|gb-(?:eng|sct|wls|nir))$/.test(value)) return '<span class="player-flag flag-empty" aria-hidden="true"></span>';
  const src='https://cdn.jsdelivr.net/gh/lipis/flag-icons@7.3.2/flags/4x3/'+value+'.svg';
  return '<img class="player-flag" src="'+src+'" alt="'+esc(label)+'" loading="lazy" decoding="async" referrerpolicy="no-referrer" onerror="this.replaceWith(Object.assign(document.createElement(\'span\'),{className:\'player-flag flag-empty\'}))">';
}
function conditionGems(value) {
  const level=Math.max(0,Math.min(5,Math.ceil(Number(value??85)/20)));
  const colors=['#e65b63','#ed9753','#e9c65a','#70c98a','#58b8d4'];
  return '<span class="condition-gems" title="Тонус: '+level+' из 5">'+colors.map((color,index)=>'<svg viewBox="0 0 16 20" class="'+(index<level?'active':'')+'" aria-hidden="true"><path d="M8 1 14 6 11.8 16 8 19 4.2 16 2 6Z" fill="'+(index<level?color:'#23342e')+'" stroke="'+(index<level?color:'#42554b')+'" stroke-width="1.2"/><path d="M8 2.5 8 17.5M3.5 6.5 12.5 6.5" stroke="#fff" stroke-opacity="'+(index<level?'.38':'.08')+'" stroke-width="1"/></svg>').join('')+'</span>';
}
function moodFace(value) {
  const level=Math.max(1,Math.min(5,Math.ceil(Number(value??70)/20)));
  const tones=['#e66b65','#e99c5a','#e7c65b','#86c779','#54c5a5'];
  const mouths=['M7 14 Q12 10 17 14','M7 14 Q12 12 17 14','M7 14 H17','M7 14 Q12 17 17 14','M7 12 Q12 19 17 12'];
  const color=tones[level-1];
  return '<span class="mood-face" title="Настрой: '+level+' из 5"><svg viewBox="0 0 24 24" aria-hidden="true"><circle cx="12" cy="12" r="10" fill="'+color+'" stroke="#fff" stroke-opacity=".38" stroke-width="1"/><path d="M7.5 9.5h.3M16.2 9.5h.3" stroke="#18251f" stroke-width="2.2" stroke-linecap="round"/><path d="'+mouths[level-1]+'" fill="none" stroke="#18251f" stroke-width="1.6" stroke-linecap="round"/></svg></span>';
}
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
  if (!window.confirm('Начать новую карьеру? Все текущие сохранения и связанные игровые данные будут удалены. Новая карьера начнётся с исходных данных SM27.')) return;
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
  const rows=players.map(player=>{
    const ratingSource=player.rating_source||'SM27 estimate';
    const valueSource=player.market_value_source||'SM27 estimate';
    const valueLabel=player.market_value?money(player.market_value):'—';
    const sourceTone=ratingSource.toLowerCase().includes('ea fc 27')?'source-official':'source-estimate';
    return '<tr class="player-row" data-player-details="'+esc(player.id)+'">'+
      '<td><span class="rating" title="'+esc(ratingSource)+'">'+(player.dynamic_overall??player.overall)+'</span><small class="data-source '+sourceTone+'">'+(ratingSource.toLowerCase().includes('ea fc 27')?'FC 27':'SM27')+'</small></td>'+
      '<td><span class="player-name">'+flagImage(player.nationality_flag,player.nationality)+' '+esc(player.name)+'</span>'+(player.original_data?.generated?'<div class="player-source-generated">Вымышленный игрок SM27</div>':'')+'</td>'+
      '<td><span class="position-tag">'+esc(player.position)+'</span></td>'+
      '<td>'+(player.secondary_positions||[]).map(pos=>'<span class="secondary-position">'+esc(pos)+'</span>').join(' ')+'</td>'+
      '<td>'+player.age+'</td><td><span class="potential-rating">'+player.potential+'</span></td>'+
      '<td class="value" title="'+esc(valueSource)+'">'+valueLabel+'<div class="data-source">'+esc(valueSource)+'</div></td>'+
      '<td>'+(player.contract_end?new Date(player.contract_end).toLocaleDateString('ru-RU',{month:'short',year:'numeric'}):'—')+'</td>'+
      '<td>'+money(player.weekly_wage)+'<div class="data-source">/ нед.</div><div class="data-source">'+esc(player.wage_source||'SM27 estimate')+'</div></td>'+
      '<td>'+conditionGems(player.sharpness)+'</td><td>'+moodFace(player.morale)+'</td></tr>';
  }).join('');
  return pageHead('ПЕРВАЯ КОМАНДА','Состав',players.length+' игроков · выбери футболиста, чтобы открыть профиль')+
    '<section class="panel"><div class="panel-head"><h3>Игроки первой команды</h3><span>OVR / POTENTIAL / VALUE</span></div>'+
    '<div class="table-wrap squad-table-wrap"><table class="squad-table"><thead><tr><th>OVR</th><th>ИГРОК</th><th>ПОЗ.</th><th>ДОП. ПОЗ.</th><th>ВОЗР.</th><th>POT</th><th>РЫНОЧНАЯ СТОИМОСТЬ</th><th>КОНТРАКТ</th><th>ЗАРПЛАТА</th><th>ТОНУС</th><th>НАСТРОЙ</th></tr></thead><tbody>'+(rows||'<tr><td colspan="11">Состав не загружен</td></tr>')+'</tbody></table></div>'+
    '<div class="squad-legend"><span>'+conditionGems(100)+' Тонус</span><span>'+moodFace(100)+' Настрой</span></div>'+
    '<div class="catalog-note" style="margin-top:18px"><span>ⓘ</span><span>Рейтинги и зарплаты FC 27 имеют пометку источника. Для остальных показывается оценка SM27. Рыночная стоимость подписывается Sofascore только после подтверждённой синхронизации.</span></div></section>';
}
function showPlayerDetails(playerId) {
  const player=state.squad.find(item=>String(item.id)===String(playerId));
  if(!player)return;
  document.getElementById('player-detail-modal')?.remove();
  const stats=player.attributes||{},keeper=player.position==='GK';
  const labels=keeper?[['DIV','Отражение'],['HAN','Игра руками'],['KIC','Удар'],['REF','Реакция'],['SPE','Скорость'],['POS','Позиционирование']]:[['PAC','Скорость'],['SHO','Удар'],['PAS','Пас'],['DRI','Дриблинг'],['DEF','Защита'],['PHY','Физика']];
  const bars=labels.map(([code,label])=>'<div class="attribute-item"><div><b>'+code+'</b><span>'+label+'</span><strong>'+(stats[code]??player.overall)+'</strong></div><i><span style="width:'+(stats[code]??player.overall)+'%"></span></i></div>').join('');
  const detailLabels={acceleration:'Ускорение',sprint_speed:'Скорость бега',finishing:'Завершение',attacking_position:'Позиционирование атаки',shot_power:'Сила удара',long_shots:'Дальние удары',penalties:'Пенальти',volleys:'Удары с лёта',vision:'Видение',crossing:'Навесы',fk_accuracy:'Штрафные',long_passing:'Длинный пас',short_passing:'Короткий пас',curve:'Подкрутка',agility:'Ловкость',balance:'Баланс',reactions:'Реакция',composure:'Хладнокровие',ball_control:'Контроль мяча',dribbling:'Дриблинг',interceptions:'Перехваты',heading_accuracy:'Игра головой',defending_awareness:'Оборонительное чутьё',standing_tackle:'Отбор',sliding_tackle:'Подкат',jumping:'Прыжки',stamina:'Выносливость',strength:'Сила',aggression:'Агрессия'};
  const details=Object.entries(stats).filter(([key,value])=>!labels.some(([code])=>code===key)&&Number.isFinite(Number(value))).map(([key,value])=>'<div class="attribute-detail"><span>'+esc(detailLabels[key]||key.replaceAll('_',' '))+'</span><b>'+Number(value)+'</b></div>').join('');
  const trained=player.secondary_positions||[],training=player.position_training_target;
  const trainable={GK:[],RB:['RWB','CB','LB','RM'],LB:['LWB','CB','RB','LM'],CB:['RB','LB','CDM'],RWB:['RB','RM','LB'],LWB:['LB','LM','RB'],CDM:['CM','CB','CAM'],CM:['CDM','CAM','RM','LM'],CAM:['CM','CF','RM','LM'],RM:['RW','RB','CM'],LM:['LW','LB','CM'],RW:['RM','LW','ST'],LW:['LM','RW','ST'],ST:['CF','CAM','LW','RW'],CF:['ST','CAM','RW','LW']};
  const available=(trainable[player.position]||[]).filter(pos=>pos!==player.position&&!trained.includes(pos));
  const weeks=Math.max(0,Math.min(8,Number(player.position_training_weeks||0)));
  let trainingMarkup='';
  if(training){trainingMarkup='<div class="training-progress"><span>'+esc(training)+' · '+weeks+'/8 игровых недель</span><i><b style="width:'+(weeks/8*100)+'%"></b></i></div>';}
  else if(available.length&&trained.length<2){trainingMarkup='<form id="position-training-form"><select id="training-position" class="select-input">'+available.map(pos=>'<option value="'+pos+'">'+pos+'</option>').join('')+'</select><button class="btn-secondary" type="submit">Начать обучение · 8 недель</button></form>';}
  else trainingMarkup='<small class="training-complete">Все доступные позиции изучены</small>';
  const toneLevel=Math.max(1,Math.min(5,Math.ceil(Number(player.sharpness??85)/20)));
  const moodLevel=Math.max(1,Math.min(5,Math.ceil(Number(player.morale??70)/20)));
  const modal=document.createElement('div');modal.id='player-detail-modal';modal.className='player-modal-backdrop';
  modal.innerHTML='<section class="player-modal panel">'+
    '<button class="modal-close" id="close-player-modal" aria-label="Закрыть">×</button>'+
    '<div class="player-modal-head"><div class="player-modal-flag">'+flagImage(player.nationality_flag,player.nationality)+'</div><div><div class="eyebrow">ПРОФИЛЬ ФУТБОЛИСТА</div><h2>'+esc(player.name)+'</h2><p>'+esc(player.nationality||'Национальность не указана')+' · '+player.age+' лет · '+esc(player.position)+'</p></div><div class="player-modal-ratings"><b>'+(player.dynamic_overall??player.overall)+'</b><span>OVR</span><b>'+player.potential+'</b><span>POT</span></div></div>'+
    '<div class="player-modal-grid"><div class="player-metric"><small>Дополнительные позиции</small><b>'+(trained.map(esc).join(' · ')||'Не изучены')+'</b><em>Открываются через обучение</em></div>'+
    '<div class="player-metric"><small>Рыночная стоимость</small><b>'+money(player.market_value)+'</b><em>'+esc(player.market_value_source||'SM27 estimate')+'</em></div>'+
    '<div class="player-metric"><small>Контракт до</small><b>'+(player.contract_end?dateLabel(player.contract_end):'—')+'</b><em>'+esc(player.rating_source||'SM27 estimate')+'</em></div>'+
    '<div class="player-metric"><small>Зарплата в неделю</small><b>'+money(player.weekly_wage)+'</b><em>'+esc(player.wage_source||'SM27 estimate')+'</em></div></div>'+
    '<div class="player-state-grid player-state-grid-visual"><div><small>Тонус · '+toneLevel+'/5</small>'+conditionGems(player.sharpness)+'</div><div><small>Настрой · '+moodLevel+'/5</small>'+moodFace(player.morale)+'</div></div>'+
    '<div class="position-training panel-inset"><div><b>Обучение новой позиции</b><small>'+(training?'Игрок сейчас изучает новую позицию':'Вторые позиции необходимо изучать')+'</small></div>'+trainingMarkup+'</div>'+
    '<div class="panel-head"><h3>Характеристики '+(keeper?'вратаря':'полевого игрока')+'</h3><span>ШКАЛА 1–99</span></div><div class="attribute-grid">'+bars+'</div>'+
    (details?'<details class="attribute-details"><summary>Подробные характеристики</summary><div class="attribute-details-grid">'+details+'</div></details>':'')+
    '<div class="catalog-note"><span>ⓘ</span><span>Показатели FC 27 указываются с источником. Для остальных игроков значения SM27 остаются оценочными, пока не подтверждены спортивной статистикой.</span></div></section>';
  document.body.appendChild(modal);
  document.getElementById('close-player-modal').addEventListener('click',()=>modal.remove());
  modal.addEventListener('click',event=>{if(event.target===modal)modal.remove();});
  document.getElementById('position-training-form')?.addEventListener('submit',async event=>{
    event.preventDefault();const position=document.getElementById('training-position')?.value;
    try{await api('/api/squad/'+encodeURIComponent(player.id)+'/train-position',{method:'POST',body:JSON.stringify({position})});state.squad=await api('/api/squad');toast('Начато обучение позиции '+position+'. Она откроется после 8 игровых недель.');showPlayerDetails(player.id);}
    catch(error){toast(error.message,true);}
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
  const remaining = [...players];
  const starters = [];
  for (const slot of formationSlots(formation)) {
    if (!remaining.length) break;
    remaining.sort((a,b) => (b.overall + positionPenalty(b,slot.role)) - (a.overall + positionPenalty(a,slot.role)));
    starters.push(remaining.shift());
  }
  return {starters,remaining};
}
function ensureTacticState(players,tactics) {
  const formation=tactics.formation||'4-3-3';
  const existing=new Map(players.map(player=>[String(player.id),player]));
  let starters=(tactics.starting_xi||[]).map(id=>existing.get(String(id))).filter(Boolean);
  let rest=players.filter(p=>!starters.some(s=>String(s.id)===String(p.id)));
  if(starters.length!==11){const optimized=optimiseLineup(players,formation);starters=optimized.starters;rest=optimized.remaining;}
  state.tacticFormation=formation;
  state.tacticSlots=starters.slice(0,11).map(p=>String(p.id));
  const savedBench=(tactics.bench||[]).map(String).filter(id=>existing.has(id)&&!state.tacticSlots.includes(id));
  state.tacticBench=savedBench.slice(0,9);
  const fillBench=rest.filter(p=>!state.tacticBench.includes(String(p.id))).sort((a,b)=>(b.dynamic_overall??b.overall)-(a.dynamic_overall??a.overall));
  while(state.tacticBench.length<7&&fillBench.length)state.tacticBench.push(String(fillBench.shift().id));
  state.tacticSettings={build_up:'balanced',chance_creation:'balanced',pressing:'on_mistake',defensive_approach:'balanced',width:50,depth:55,tempo:'balanced',focus:'balanced',player_roles:{},...(tactics.style||{})};
  state.tacticSettings.player_roles||={};
  state.selectedTacticSlot=null;
  state.selectedTacticPlayerId=null;
  state.tacticReserveOrder=[];
}
function redrawTactics() {
  const tactics={formation:state.tacticFormation,mentality:'balanced',style:state.tacticSettings,starting_xi:state.tacticSlots,bench:state.tacticBench};
  shell(renderTactics(state.squad,tactics),'Тактика');
  setupTacticsInteractions();
}
function playerTag(player,slotIndex=null) {
  if(!player)return '';
  return '<div class="pitch-player-card" draggable="true" data-player-id="'+esc(player.id)+'" '+(slotIndex!==null?'data-pitch-slot="'+slotIndex+'"':'')+'><b>'+(player.dynamic_overall??player.overall)+'</b><small>'+esc(player.name.split(' ').slice(-1)[0])+'</small></div>';
}
function renderTactics(players,tactics) {
  const formation=tactics.formation||'4-3-3';
  const slots=formationSlots(formation);
  const byId=new Map(players.map(player=>[String(player.id),player]));
  const pitchPlayers=slots.map((slot,index)=>{
    const player=byId.get(state.tacticSlots[index]);
    const selected=player&&state.selectedTacticPlayerId===String(player.id);
    const rating=player?(player.dynamic_overall??player.overall)+positionPenalty(player,slot.role):null;
    return '<button class="pitch-player '+(selected?'selected-player ':'')+(player?'':'empty')+'" style="left:'+slot.left+'%;top:'+slot.top+'%" data-pitch-slot="'+index+'" data-drop-slot="'+index+'" draggable="'+Boolean(player)+'" '+(player?'data-player-id="'+esc(player.id)+'"':'')+'>'+
      '<strong>'+(player?rating:'+')+'</strong><small>'+esc(slot.role)+'</small><em>'+(player?esc(player.name.split(' ').slice(-1)[0]):'Пусто')+'</em></button>';
  }).join('');
  const benchIds=new Set(state.tacticBench.map(String));
  let reservePlayers=players.filter(p=>!state.tacticSlots.includes(String(p.id))&&!benchIds.has(String(p.id)));
  if(state.tacticReserveOrder.length){
    const order=new Map(state.tacticReserveOrder.map((id,index)=>[id,index]));
    reservePlayers.sort((a,b)=>(order.get(String(a.id))??9999)-(order.get(String(b.id))??9999)||(b.dynamic_overall??b.overall)-(a.dynamic_overall??a.overall));
  }else reservePlayers.sort((a,b)=>(b.dynamic_overall??b.overall)-(a.dynamic_overall??a.overall));
  const bench=state.tacticBench.map(id=>{
    const p=byId.get(String(id));if(!p)return '';
    const selected=state.selectedTacticPlayerId===String(id);
    return '<div class="tactic-roster-item"><button class="tactic-player-row bench-player '+(selected?'selected-player':'')+'" draggable="true" data-player-id="'+esc(id)+'"><b>'+(p.dynamic_overall??p.overall)+'</b><span>'+esc(p.name)+'<small>'+esc(p.position)+' · запас</small></span></button><button class="roster-action" data-release-player="'+esc(id)+'" title="Переместить в резерв">В резерв</button></div>';
  }).join('');
  const reserves=reservePlayers.map(p=>{
    const selected=state.selectedTacticPlayerId===String(p.id);
    return '<div class="tactic-roster-item"><button class="tactic-player-row reserve-player '+(selected?'selected-player':'')+'" draggable="true" data-player-id="'+esc(p.id)+'"><b>'+(p.dynamic_overall??p.overall)+'</b><span>'+esc(p.name)+'<small>'+esc(p.position)+' · резерв</small></span></button><button class="roster-action" data-promote-player="'+esc(p.id)+'" title="Добавить в запас">В запас</button></div>';
  }).join('');
  const settings=state.tacticSettings;
  const select=(id,label,value,options)=>'<label class="tactic-setting"><span>'+label+'</span><select id="'+id+'" class="select-input">'+options.map(([v,l])=>'<option value="'+v+'" '+(value===v?'selected':'')+'>'+l+'</option>').join('')+'</select></label>';
  return pageHead('ПЛАН НА МАТЧ','Тактика','Выбери схему, расставь футболистов и настрой поведение команды.')+
    '<div class="tactic-toolbar panel"><label>СХЕМА<select id="formation" class="select-input">'+FORMATIONS.map(f=>'<option value="'+esc(f)+'" '+(formation===f?'selected':'')+'>'+esc(f)+'</option>').join('')+'</select></label>'+
    '<span class="lineup-counter">'+state.tacticSlots.filter(Boolean).length+'/11 В ОСНОВЕ</span><span class="lineup-counter">'+state.tacticBench.length+'/9 В ЗАПАСЕ</span>'+
    '<button id="auto-lineup" class="btn-secondary">Лучший состав</button><button id="save-tactics" class="btn-primary">Сохранить</button></div>'+
    '<div class="tactic-layout tactic-layout-full"><section class="panel tactic-board-panel">'+
    '<div class="panel-head"><h3>Тактическое поле</h3><span>Выбери любого игрока, затем другого — они поменяются местами между полем, запасом и резервом.</span></div>'+
    '<div class="pitch pitch-football" id="tactic-pitch"><div class="pitch-line"></div><div class="pitch-box pitch-box-top"></div><div class="pitch-box pitch-box-bottom"></div><div class="pitch-circle"></div>'+pitchPlayers+'</div>'+
    '<div class="catalog-note"><span>ⓘ</span><span>ОВР на поле учитывает позиционный штраф. Родная и изученная позиция не снижают рейтинг. Вратарь на любой полевой позиции получает штраф 40.</span></div>'+
    '<div class="squad-bench-block"><div class="panel-head"><h3>Запас</h3><span>от 5 до 9 игроков</span></div><div class="tactic-roster-grid" id="tactic-bench">'+(bench||'<p class="empty-state">Скамейка пуста</p>')+'</div></div>'+
    '<div class="squad-bench-block"><div class="panel-head"><h3>Резерв</h3><span>Остальные футболисты</span></div><div class="tactic-roster-grid reserves-list" id="tactic-reserves">'+(reserves||'<p class="empty-state">В резерве пока нет игроков</p>')+'</div></div></section>'+
    '<aside class="panel tactic-controls tactic-settings-panel"><div class="panel-head"><h3>Тактика команды</h3><span>Установки на матч</span></div>'+
    select('build-up','Построение атаки',settings.build_up,[['balanced','Сбалансированно'],['short','Короткий пас'],['direct','Вертикальные передачи'],['fast','Быстрый выход'],['possession','Контроль мяча']])+
    select('chance-creation','Создание моментов',settings.chance_creation,[['balanced','Сбалансированно'],['wide','Через фланги'],['centre','Через центр'],['direct','Забросы за спину'],['patience','Терпеливое владение']])+
    select('pressing','Прессинг',settings.pressing,[['on_mistake','После потери'],['high','Высокий'],['mid','Средний блок'],['low','Низкий блок'],['heavy','Постоянный']])+
    select('defensive-approach','Оборона',settings.defensive_approach,[['balanced','Сбалансированно'],['aggressive','Агрессивно'],['conservative','Сдержанно'],['high','Высокая линия'],['low','Глубокая линия']])+
    select('tempo','Темп',settings.tempo,[['slow','Низкий'],['balanced','Средний'],['fast','Высокий']])+
    select('focus','Фокус',settings.focus,[['balanced','Сбалансированный'],['left','Левый фланг'],['right','Правый фланг'],['centre','Центр']])+
    '<label class="tactic-setting"><span>Ширина <b id="width-value">'+(settings.width??50)+'</b></span><input id="tactic-width" type="range" min="0" max="100" value="'+(settings.width??50)+'"></label>'+
    '<label class="tactic-setting"><span>Высота обороны <b id="depth-value">'+(settings.depth??55)+'</b></span><input id="tactic-depth" type="range" min="0" max="100" value="'+(settings.depth??55)+'"></label></aside></div>';
}
function reservePlayerIds() {
  return state.squad.filter(p=>!state.tacticSlots.includes(String(p.id))&&!state.tacticBench.includes(String(p.id)))
    .sort((a,b)=>(b.dynamic_overall??b.overall)-(a.dynamic_overall??a.overall)).map(p=>String(p.id));
}
function moveTacticPlayerToSlot(playerId,slotIndex) {
  const id=String(playerId),target=state.tacticSlots[slotIndex];
  if(!id||slotIndex<0||slotIndex>=11)return;
  const fromSlot=state.tacticSlots.indexOf(id),fromBench=state.tacticBench.indexOf(id);
  if(fromSlot>=0){
    if(target){const targetSlot=state.tacticSlots.indexOf(String(target));state.tacticSlots[targetSlot]=id;state.tacticSlots[fromSlot]=target;}
    else{state.tacticSlots[slotIndex]=id;state.tacticSlots[fromSlot]=null;}
  }else{
    state.tacticSlots[slotIndex]=id;
    state.tacticBench=state.tacticBench.filter(x=>String(x)!==id);
    if(target&&fromBench>=0)state.tacticBench[fromBench]=String(target);
    else if(target&&state.tacticBench.length<9&&state.tacticBench.length<7)state.tacticBench.push(String(target));
  }
  state.selectedTacticPlayerId=null;state.selectedTacticSlot=null;redrawTactics();
}
function swapTacticRosterPlayers(firstId,secondId) {
  const a=String(firstId),b=String(secondId);
  if(!a||!b||a===b){state.selectedTacticPlayerId=null;redrawTactics();return;}
  const aSlot=state.tacticSlots.indexOf(a),bSlot=state.tacticSlots.indexOf(b);
  const aBench=state.tacticBench.indexOf(a),bBench=state.tacticBench.indexOf(b);
  if(aSlot>=0&&bSlot>=0){[state.tacticSlots[aSlot],state.tacticSlots[bSlot]]=[state.tacticSlots[bSlot],state.tacticSlots[aSlot]];}
  else if(aSlot>=0&&bBench>=0){state.tacticSlots[aSlot]=b;state.tacticBench[bBench]=a;}
  else if(bSlot>=0&&aBench>=0){state.tacticSlots[bSlot]=a;state.tacticBench[aBench]=b;}
  else if(aBench>=0&&bBench>=0){[state.tacticBench[aBench],state.tacticBench[bBench]]=[state.tacticBench[bBench],state.tacticBench[aBench]];}
  else if(aSlot>=0){state.tacticSlots[aSlot]=b;}
  else if(bSlot>=0){state.tacticSlots[bSlot]=a;}
  else if(aBench>=0){state.tacticBench[aBench]=b;}
  else if(bBench>=0){state.tacticBench[bBench]=a;}
  else{
    const order=state.tacticReserveOrder.length?state.tacticReserveOrder:reservePlayerIds();
    const ia=order.indexOf(a),ib=order.indexOf(b);
    if(ia>=0&&ib>=0)[order[ia],order[ib]]=[order[ib],order[ia]];
    state.tacticReserveOrder=order;
  }
  state.selectedTacticPlayerId=null;state.selectedTacticSlot=null;redrawTactics();
}
function selectTacticPlayer(playerId) {
  const id=String(playerId);
  if(!state.selectedTacticPlayerId){state.selectedTacticPlayerId=id;redrawTactics();return;}
  swapTacticRosterPlayers(state.selectedTacticPlayerId,id);
}
function swapTacticPlayers(slotIndex,playerId) { moveTacticPlayerToSlot(playerId,slotIndex); }
function setupTacticsInteractions() {
  document.getElementById('formation')?.addEventListener('change',event=>{
    const result=optimiseLineup(state.squad,event.target.value);
    state.tacticSlots=result.starters.map(p=>String(p.id));state.tacticBench=result.remaining.slice(0,7).map(p=>String(p.id));
    state.tacticFormation=event.target.value;state.selectedTacticPlayerId=null;redrawTactics();
  });
  document.getElementById('auto-lineup')?.addEventListener('click',()=>{
    const formation=document.getElementById('formation').value,result=optimiseLineup(state.squad,formation);
    state.tacticSlots=result.starters.map(p=>String(p.id));state.tacticBench=result.remaining.slice(0,7).map(p=>String(p.id));
    state.tacticFormation=formation;state.selectedTacticPlayerId=null;redrawTactics();
  });
  document.querySelectorAll('[data-pitch-slot]').forEach(button=>button.addEventListener('click',()=>{
    const slot=Number(button.dataset.pitchSlot),id=state.tacticSlots[slot];
    if(!id&&state.selectedTacticPlayerId){moveTacticPlayerToSlot(state.selectedTacticPlayerId,slot);return;}
    if(id)selectTacticPlayer(id);
  }));
  document.querySelectorAll('.tactic-player-row').forEach(button=>button.addEventListener('click',()=>selectTacticPlayer(button.dataset.playerId)));
  document.querySelectorAll('[data-release-player]').forEach(button=>button.addEventListener('click',event=>{
    event.stopPropagation();
    if(state.tacticBench.length<=5){toast('В запасе должно остаться минимум 5 игроков',true);return;}
    state.tacticBench=state.tacticBench.filter(id=>String(id)!==String(button.dataset.releasePlayer));redrawTactics();
  }));
  document.querySelectorAll('[data-promote-player]').forEach(button=>button.addEventListener('click',event=>{
    event.stopPropagation();
    if(state.tacticBench.length>=9){toast('В запасе может быть максимум 9 игроков',true);return;}
    state.tacticBench.push(String(button.dataset.promotePlayer));redrawTactics();
  }));
  const pitch=document.getElementById('tactic-pitch');
  document.querySelectorAll('[data-player-id]').forEach(node=>node.addEventListener('dragstart',event=>event.dataTransfer.setData('text/player-id',node.dataset.playerId)));
  pitch?.querySelectorAll('[data-pitch-slot]').forEach(slot=>{
    slot.addEventListener('dragover',event=>event.preventDefault());
    slot.addEventListener('drop',event=>{event.preventDefault();const id=event.dataTransfer.getData('text/player-id');if(id)moveTacticPlayerToSlot(id,Number(slot.dataset.dropSlot));});
  });
  ['build-up','chance-creation','pressing','defensive-approach','tempo','focus'].forEach(id=>{
    document.getElementById(id)?.addEventListener('change',event=>{
      const key=id.replace(/-([a-z])/g,(_,c)=>c.toUpperCase()).replace(/^buildUp$/,'build_up').replace(/^chanceCreation$/,'chance_creation').replace(/^defensiveApproach$/,'defensive_approach');
      state.tacticSettings[key]=event.target.value;
    });
  });
  document.getElementById('tactic-width')?.addEventListener('input',event=>{state.tacticSettings.width=Number(event.target.value);document.getElementById('width-value').textContent=event.target.value;});
  document.getElementById('tactic-depth')?.addEventListener('input',event=>{state.tacticSettings.depth=Number(event.target.value);document.getElementById('depth-value').textContent=event.target.value;});
  document.querySelectorAll('[data-player-role]').forEach(node=>node.addEventListener('change',event=>{state.tacticSettings.player_roles[event.target.dataset.playerRole]=event.target.value;}));
  document.getElementById('save-tactics')?.addEventListener('click',saveTactics);
}

function renderFixtures(rows) {
  if(!rows.length)return pageHead('РАСПИСАНИЕ','Календарь','Календарь сезона 2026/27.')+'<section class="panel"><div class="empty-state">Матчей пока нет</div></section>';
  if(!state.calendarMonth){const date=new Date(state.save?.game_date||'2026-07-01T12:00:00');state.calendarMonth=new Date(date.getFullYear(),date.getMonth(),1);}
  const month=new Date(state.calendarMonth.getFullYear(),state.calendarMonth.getMonth(),1);
  const monthLabel=month.toLocaleDateString('ru-RU',{month:'long',year:'numeric'});
  const keyDate=value=>{const d=new Date(value);return d.getFullYear()+'-'+String(d.getMonth()+1).padStart(2,'0')+'-'+String(d.getDate()).padStart(2,'0');};
  const byDate=new Map();rows.forEach(row=>{const key=keyDate(row.match_date);if(!byDate.has(key))byDate.set(key,[]);byDate.get(key).push(row);});
  const resultFor=f=>{
    if(f.status!=='completed'||f.home_score===null||f.away_score===null)return 'scheduled';
    const own=f.is_home?Number(f.home_score):Number(f.away_score),opp=f.is_home?Number(f.away_score):Number(f.home_score);
    return own>opp?'win':own<opp?'loss':'draw';
  };
  const scoreFor=f=>f.status==='completed'?String(f.home_score)+' : '+String(f.away_score):'— : —';
  const offset=(month.getDay()+6)%7,days=new Date(month.getFullYear(),month.getMonth()+1,0).getDate(),cells=[];
  for(let i=0;i<offset;i++)cells.push('<div class="calendar-empty"></div>');
  for(let day=1;day<=days;day++){
    const key=month.getFullYear()+'-'+String(month.getMonth()+1).padStart(2,'0')+'-'+String(day).padStart(2,'0');
    const events=byDate.get(key)||[];
    const eventMarkup=events.slice(0,2).map(f=>{
      const result=resultFor(f),stage=f.stage||('Тур '+(f.matchday||'—'));
      const scoreClass=result==='scheduled'?'':' score-'+result;
      const title=(f.opponent_name||'Соперник')+' · '+(f.tournament_name||'Турнир')+' · '+stage+' · '+(f.is_home?'Дома':'В гостях');
      return '<span class="calendar-day-match" title="'+esc(title)+'"><span class="calendar-day-crest">'+crest(f.opponent_name||'Соперник',f.opponent_logo)+'</span>'+
        (f.status==='completed'?'<b class="calendar-day-score'+scoreClass+'">'+scoreFor(f)+'</b>':'<small>'+esc(f.is_home?'Д':'В')+'</small>')+'</span>';
    }).join('');
    cells.push('<button class="calendar-day '+(state.selectedCalendarDate===key?'selected ':'')+(events.length?'has-event':'')+'" data-calendar-date="'+key+'"><b>'+day+'</b>'+
      (eventMarkup?'<div class="calendar-day-events">'+eventMarkup+'</div>':'')+(events.length>2?'<span class="calendar-more">+'+(events.length-2)+'</span>':'')+'</button>');
  }
  const selected=state.selectedCalendarDate||keyDate(state.save?.game_date||'2026-07-01T12:00:00');
  const selectedRows=byDate.get(selected)||[];
  const selectedContent=selectedRows.length?selectedRows.map(f=>{
    const result=resultFor(f),scoreClass=result==='scheduled'?'':' score-'+result;
    const stage=f.stage?esc(f.stage):'ТУР '+esc(f.matchday||'—');
    const location=f.is_home?'ДОМА':'В ГОСТЯХ';
    return '<div class="calendar-match-row"><div class="calendar-match-meta"><span>'+esc(f.tournament_name||'Турнир')+'</span><b>'+stage+'</b><em>'+location+'</em></div>'+
      '<div class="calendar-match-opponent">'+crest(f.opponent_name||'Соперник',f.opponent_logo,'large')+'<div><b>'+esc(f.opponent_name||'Соперник')+'</b><small>'+(f.is_home?'Домашний матч':'Выездной матч')+'</small></div>'+
      '<strong class="calendar-match-score'+scoreClass+'">'+scoreFor(f)+'</strong></div></div>';
  }).join(''):'<div class="empty-state">На выбранную дату матчей нет</div>';
  const weekdays=['ПН','ВТ','СР','ЧТ','ПТ','СБ','ВС'].map(d=>'<span>'+d+'</span>').join('');
  return pageHead('СЕЗОН 2026/27','Календарь','Матчи, соперники и результаты по дням сезона.')+
    '<div class="calendar-layout panel"><section class="calendar-main"><div class="calendar-month-nav"><button class="btn-quiet" id="calendar-prev">‹</button><h2>'+monthLabel+'</h2><button class="btn-quiet" id="calendar-next">›</button></div>'+
    '<div class="calendar-weekdays">'+weekdays+'</div><div class="calendar-grid">'+cells.join('')+'</div>'+
    '<div class="calendar-legend"><span class="score-legend win"></span> Победа <span class="score-legend draw"></span> Ничья <span class="score-legend loss"></span> Поражение</div></section>'+
    '<aside class="calendar-selected"><div class="eyebrow">ВЫБРАННЫЙ ДЕНЬ</div><h3>'+dateLabel(selected+'T12:00:00')+'</h3>'+selectedContent+'</aside></div>';
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
    <section class="panel"><div class="panel-head"><h3>${esc(state.save?.league || 'Лига')}</h3><span>СЕЗОН 2026 / 27</span></div><div class="table-wrap"><table><thead><tr><th>#</th><th>Клуб</th><th>И</th><th>В</th><th>Н</th><th>П</th><th>ЗМ</th><th>ПМ</th><th>РМ</th><th>ОЧКИ</th></tr></thead><tbody>${rows.map((r,i)=>`<tr class="${r.name===state.save?.club_name?'me-row':''}"><td>${i+1}</td><td><div class="team-cell">${crest(r.name, r.logo_url)}${esc(r.name)}</div></td><td>${r.played}</td><td>${r.won}</td><td>${r.drawn}</td><td>${r.lost}</td><td>${r.goals_for}</td><td>${r.goals_against}</td><td>${r.goal_difference||0}</td><td><b>${r.points}</b></td></tr>`).join('') || '<tr><td colspan="10">Таблица пока пустая</td></tr>'}</tbody></table></div></section>`;
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
