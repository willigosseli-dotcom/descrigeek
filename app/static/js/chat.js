/**
 * DescriGeek — Chat UI
 * Dépend de chatService.js (chargé avant ce fichier).
 * Ne contient aucune logique de transport — tout passe par window.chatService.
 */

(function () {
  if (!window.CHAT_USER || !window.ChatService) return;

  // ─── Initialisation des services ────────────────────────────────────────
  const svc    = new ChatService({
    username:    window.CHAT_USER.username,
    displayName: window.CHAT_USER.displayName,
  });
  window.chatService = svc;

  // Réutiliser l'instance avatarService créée dans base.html si disponible
  const avatarSvc = window._avatarSvc || new AvatarService();
  window._avatarSvc = avatarSvc;

  // Mettre à jour les avatars dans le chat quand un autre user change le sien
  avatarSvc.onUpdate((username) => {
    document.querySelectorAll(`.chat-avatar[data-user="${CSS.escape(username)}"]`)
      .forEach(img => { img.src = avatarSvc.getAvatar(username); });
  });

  // ─── Références DOM ─────────────────────────────────────────────────────
  const toggleBtn  = document.getElementById('chat-toggle-btn');
  const panel      = document.getElementById('chat-panel');
  const badge      = document.getElementById('chat-badge');
  const messagesEl = document.getElementById('chat-messages');
  const input      = document.getElementById('chat-input');
  const sendBtn    = document.getElementById('chat-send-btn');
  const closeBtn   = document.getElementById('chat-close-btn');
  const bellBtn    = document.getElementById('chat-bell-btn');

  let isOpen = false;

  // ─── Ouvrir / fermer le panel ───────────────────────────────────────────
  toggleBtn.addEventListener('click', () => isOpen ? closeChat() : openChat());
  closeBtn.addEventListener('click', closeChat);

  function openChat() {
    isOpen = true;
    panel.style.display = 'flex';
    toggleBtn.classList.add('active');
    svc.markAllRead();
    updateBadge(0);
    renderHistory();
    scrollBottom();
    input.focus();
  }

  // Re-rendre l'historique quand Supabase a fini de charger
  svc.onReady(() => {
    if (isOpen) { renderHistory(); scrollBottom(); }
  });

  function closeChat() {
    isOpen = false;
    panel.style.display = 'none';
    toggleBtn.classList.remove('active');
  }

  // ─── Historique ─────────────────────────────────────────────────────────
  function renderHistory() {
    messagesEl.innerHTML = '';
    const history = svc.getHistory().slice(-100);
    history.forEach(msg => appendMessage(msg, false));
  }

  // ─── Affichage d'un message ─────────────────────────────────────────────
  function appendMessage(msg, animate) {
    const isMine = msg.username === window.CHAT_USER.username;
    const time   = new Date(msg.timestamp).toLocaleTimeString('fr-CA',
      { hour: '2-digit', minute: '2-digit' });
    // Préférer l'URL stockée dans le message (Supabase), sinon lire depuis avatarSvc
    const avatar = msg.avatar || avatarSvc.getAvatar(msg.username);

    const el = document.createElement('div');
    el.className = 'chat-msg' + (isMine ? ' chat-msg-mine' : '') + (animate ? ' chat-msg-new' : '');
    el.innerHTML = `
      <img class="chat-avatar" src="${escHtml(avatar)}"
           data-user="${escHtml(msg.username)}" alt="${escHtml(msg.from)}">
      <div class="chat-msg-body">
        <div class="chat-msg-meta">
          ${!isMine ? `<span class="chat-msg-from">${escHtml(msg.from)}</span>` : ''}
          <span class="chat-msg-time">${time}</span>
        </div>
        <div class="chat-msg-bubble">${escHtml(msg.text)}</div>
      </div>`;
    messagesEl.appendChild(el);
  }

  function scrollBottom() {
    messagesEl.scrollTop = messagesEl.scrollHeight;
  }

  // ─── Envoi d'un message ─────────────────────────────────────────────────
  function sendMessage() {
    const text = input.value.trim();
    if (!text) return;
    const msg = svc.sendMessage(text);
    if (msg) {
      appendMessage(msg, true);
      scrollBottom();
    }
    input.value = '';
    input.focus();
  }

  sendBtn.addEventListener('click', sendMessage);
  input.addEventListener('keydown', e => {
    if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); sendMessage(); }
  });

  // ─── Réception d'un message (autre onglet) ──────────────────────────────
  svc.onMessage(msg => {
    if (isOpen) {
      appendMessage(msg, true);
      scrollBottom();
      svc.markAllRead();
    } else {
      updateBadge(svc.getUnreadCount());
      shakeToggleBtn();
    }
  });

  // ─── Badge non lus ──────────────────────────────────────────────────────
  function updateBadge(n) {
    if (n > 0) {
      badge.textContent = n > 99 ? '99+' : n;
      badge.style.display = 'flex';
    } else {
      badge.style.display = 'none';
    }
  }
  updateBadge(svc.getUnreadCount());

  function shakeToggleBtn() {
    toggleBtn.classList.remove('chat-shake');
    void toggleBtn.offsetWidth; // reflow pour relancer l'animation
    toggleBtn.classList.add('chat-shake');
    setTimeout(() => toggleBtn.classList.remove('chat-shake'), 600);
  }

  // ─── Cloche ─────────────────────────────────────────────────────────────
  bellBtn.addEventListener('click', () => {
    svc.sendBell();
    // Feedback visuel local
    bellBtn.textContent = '💨';
    setTimeout(() => { bellBtn.textContent = '🔔'; }, 1500);
    // Le son joue aussi pour soi-même
    playFart();
    shakeScreen();
    appendBellNotif('Vous avez envoyé une cloche 🔔');
    scrollBottom();
  });

  svc.onBell(bell => {
    playFart();
    shakeScreen();
    if (isOpen) {
      appendBellNotif(`${escHtml(bell.from)} a envoyé une cloche 🔔`);
      scrollBottom();
    } else {
      shakeToggleBtn();
      // Flash rouge sur le bouton de chat
      toggleBtn.classList.add('chat-bell-flash');
      setTimeout(() => toggleBtn.classList.remove('chat-bell-flash'), 1000);
    }
  });

  function appendBellNotif(text) {
    const el = document.createElement('div');
    el.className = 'chat-notif';
    el.textContent = text;
    messagesEl.appendChild(el);
  }

  // ─── Son de pet (Web Audio API — aucun fichier externe) ─────────────────
  function playFart() {
    try {
      const ctx = new (window.AudioContext || window.webkitAudioContext)();
      const sr = ctx.sampleRate;
      const duration = 0.75;
      const frames = Math.floor(sr * duration);

      const buf = ctx.createBuffer(1, frames, sr);
      const data = buf.getChannelData(0);

      for (let i = 0; i < frames; i++) {
        const t = i / sr;
        const progress = t / duration;
        // Bruit blanc modulé par une sinusoïde descendante (effet "prrrrt")
        const flutter = Math.sin(2 * Math.PI * (28 - progress * 18) * t);
        const envelope = Math.pow(1 - progress, 0.6);
        data[i] = (Math.random() * 2 - 1) * flutter * envelope * 1.8;
      }

      const src = ctx.createBufferSource();
      src.buffer = buf;

      // Filtre passe-bas: son grave et étouffé
      const lpf = ctx.createBiquadFilter();
      lpf.type = 'lowpass';
      lpf.frequency.setValueAtTime(500, ctx.currentTime);
      lpf.frequency.exponentialRampToValueAtTime(70, ctx.currentTime + duration);

      // Gain global avec fade-out
      const gain = ctx.createGain();
      gain.gain.setValueAtTime(2.2, ctx.currentTime);
      gain.gain.linearRampToValueAtTime(0, ctx.currentTime + duration);

      src.connect(lpf);
      lpf.connect(gain);
      gain.connect(ctx.destination);
      src.start();
      src.stop(ctx.currentTime + duration + 0.05);
    } catch (e) {
      console.warn('[Chat] Son non disponible :', e);
    }
  }

  // ─── Vibration de l'écran ───────────────────────────────────────────────
  function shakeScreen() {
    const target = document.querySelector('.main-content') || document.body;
    target.classList.remove('dg-shake');
    void target.offsetWidth;
    target.classList.add('dg-shake');
    setTimeout(() => target.classList.remove('dg-shake'), 550);
    // Vibration mobile si disponible
    if (navigator.vibrate) navigator.vibrate([80, 40, 80, 40, 120]);
  }

  // ─── Utilitaires ────────────────────────────────────────────────────────
  function escHtml(str) {
    return String(str)
      .replace(/&/g, '&amp;').replace(/</g, '&lt;')
      .replace(/>/g, '&gt;').replace(/"/g, '&quot;');
  }
})();
