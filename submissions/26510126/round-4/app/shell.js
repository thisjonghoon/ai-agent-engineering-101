// The app's frame on every screen (11/27, owner): the ⋯ menu, the 보드 tab's badge, and the tabs folding away while
// the chat's keyboard is up on a phone. Each page carries the same header markup (see app/DESIGN.md); this only fills it.
//   /menu.json   written every 30 s by dashboard_r4.py (model, advice team, watch); missing is fine
//   /board.json  written by board_r4.py; the badge counts the cards in 내 차례 that are not sent yet,
//                plus the agent's MeshKit consents waiting in /api/state
(() => {
  const $ = id => document.getElementById(id);
  const esc = s => String(s ?? '').replace(/[&<>"']/g, c => ({'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'}[c]));
  const me = (() => { try { return localStorage.getItem('miniapp-user') || 'jonghoon'; } catch (e) { return 'jonghoon'; } })();
  const get = async path => { try { const r = await fetch(path, {cache: 'no-store'}); return r.ok ? r.json() : null; } catch (e) { return null; } };

  // ⋯ : a bottom sheet on a phone, a small panel under the button on wide screens (ui.css #menu)
  const btn = $('morebtn'), shade = $('menu');
  let menu = null;
  function drawMenu() {
    const rows = (menu && menu.rows) || [];
    $('menu-body').innerHTML = (rows.length
      ? `<div class="kv">${rows.map(r => `<div><span>${esc(r.k)}</span><span>${esc(r.v)}${r.sub ? `<small>${esc(r.sub)}</small>` : ''}</span></div>`).join('')}</div>`
      : '<p class="sub">현황이 아직 쓰이지 않았습니다.</p>')
      + `<button type="button" class="mbtn" id="copylink">앱 주소 복사</button>`
      + (menu && menu.at ? `<p class="note" style="margin:10px 0 0">기준 <span class="num">${esc(menu.at)}</span></p>` : '')
      + `<p class="note credit">미니앱 키트는 <a href="https://github.com/Q00/meshkit" target="_blank" rel="noopener">MeshKit</a>과 <a href="https://github.com/Q00/ouroboros" target="_blank" rel="noopener">Ouroboros</a>에서 영감을 받았습니다</p>`;
    $('copylink').onclick = async e => {
      try { await navigator.clipboard.writeText(location.origin + '/'); e.target.textContent = '복사했습니다'; } catch (err) { e.target.textContent = location.origin; }
    };
  }
  const open = () => { drawMenu(); shade.hidden = false; btn.setAttribute('aria-expanded', 'true'); shade.querySelector('.sheet').focus(); };
  const close = () => { shade.hidden = true; btn.setAttribute('aria-expanded', 'false'); btn.focus({preventScroll: true}); };
  if (btn && shade) {
    btn.onclick = () => (shade.hidden ? open() : close());
    shade.addEventListener('click', e => { if (e.target === shade) close(); });
    document.addEventListener('keydown', e => { if (e.key === 'Escape' && !shade.hidden) close(); });
  }
  async function refreshMenu() {
    menu = await get('/menu.json');
    const pip = btn && btn.querySelector('.pip');
    if (pip) pip.hidden = !(menu && menu.warn);
    if (shade && !shade.hidden) drawMenu();
  }

  // the 보드 badge: what waits for the owner
  let board = null, consents = 0;
  window.appShell = {board: () => board, me};
  function badge() {
    const el = $('boardbadge');
    if (!el) return;
    const chat = window.appShell.chat || [];
    const waiting = ((board && board.cards) || []).filter(c => c.status === 'owner' && !window.appShell.isSent?.(c, chat)).length + consents;
    el.hidden = !waiting;
    el.textContent = waiting;
    el.setAttribute('aria-label', `내 차례 ${waiting}건`);
  }
  async function refreshBoard() {
    board = await get('/board.json');
    if (!window.miniapp) {                       // 현황 has no miniapp.js: ask the state ourselves for the consents
      const s = await get('/api/state');
      if (s) { consents = (s.calls || []).filter(c => c.kind === 'consent').length; window.appShell.chat = s.chat || []; }
    }
    badge();
    document.dispatchEvent(new CustomEvent('board', {detail: board}));
  }
  if (window.miniapp) window.miniapp.onState(s => { consents = (s.consents || []).length; window.appShell.chat = s.chat || []; badge(); });
  window.appShell.isSent = (c, chat) => c.kind === 'order' && c.draft &&
    (chat || []).some(m => m.who === me && m.ts >= (c.at || 0) - 5 && m.text.trim() === c.draft.trim());
  window.appShell.refresh = refreshBoard;

  // the chat's keyboard: fold the tabs while the message box has focus on a phone (ui.css body.typing)
  const field = $('t');
  if (field && matchMedia('(pointer: coarse)').matches) {
    field.addEventListener('focus', () => document.body.classList.add('typing'));
    field.addEventListener('blur', () => document.body.classList.remove('typing'));
  }

  refreshMenu(); refreshBoard();
  setInterval(refreshMenu, 30000);
  setInterval(refreshBoard, 10000);
})();
