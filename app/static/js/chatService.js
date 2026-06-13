/**
 * DescriGeek — Chat Service
 *
 * BACKEND ACTUEL : Supabase (table `messages` + Realtime Broadcast pour la cloche)
 * FALLBACK       : BroadcastChannel + localStorage (si Supabase non disponible)
 *
 * Interface publique (inchangée pour chat.js) :
 *   new ChatService({ username, displayName })
 *   .sendMessage(text)   → msg
 *   .onMessage(handler)
 *   .sendBell()
 *   .onBell(handler)
 *   .getHistory()        → msg[]  (mis en cache dès le chargement)
 *   .onReady(handler)    → appelé quand l'historique initial est chargé
 *   .getUnreadCount()    → number
 *   .markAllRead()
 */

class ChatService {
  constructor({ username, displayName }) {
    this.username    = username;
    this.displayName = displayName;

    this._history       = [];
    this._handlers      = [];
    this._bellHandlers  = [];
    this._readyHandlers = [];
    this._ready         = false;
    this._UNREAD_KEY    = 'dg_chat_unread';
    this._sentIds       = new Set(); // évite les doublons (echo de nos propres inserts)

    if (window._supabase) {
      this._initSupabase();
    } else {
      this._initLocal();
    }
  }

  // ═══════════════════════════════════════════════════════════════════════
  // BACKEND SUPABASE
  // ═══════════════════════════════════════════════════════════════════════

  async _initSupabase() {
    const sb = window._supabase;

    // 1. Charger l'historique récent (100 derniers messages)
    try {
      const { data, error } = await sb
        .from('messages')
        .select('id, username, display_name, text, avatar_url, timestamp')
        .order('timestamp', { ascending: true })
        .limit(100);

      if (!error && data) {
        this._history = data.map(r => this._rowToMsg(r));
      }
    } catch (e) {
      console.warn('[Chat] Impossible de charger l\'historique :', e);
    }

    this._markReady();

    // 2. S'abonner aux nouveaux messages ET aux broadcasts cloche
    this._sbChannel = sb.channel('descrigeek-chat', {
      config: { broadcast: { self: false } },
    });

    this._sbChannel
      .on('postgres_changes',
        { event: 'INSERT', schema: 'public', table: 'messages' },
        payload => {
          const r = payload.new;
          // Ignorer nos propres inserts (déjà ajoutés localement)
          if (this._sentIds.has(r.id)) { this._sentIds.delete(r.id); return; }
          const msg = this._rowToMsg(r);
          this._history.push(msg);
          this._incrementUnread();
          this._handlers.forEach(h => h(msg));
        }
      )
      .on('broadcast', { event: 'bell' }, ({ payload }) => {
        this._bellHandlers.forEach(h => h(payload));
      })
      .subscribe(status => {
        if (status === 'SUBSCRIBED') console.info('[Chat] Realtime connecté ✓');
      });
  }

  _rowToMsg(r) {
    return {
      id:        r.id,
      username:  r.username,
      from:      r.display_name,
      text:      r.text,
      avatar:    r.avatar_url || null,
      timestamp: r.timestamp,
    };
  }

  // ═══════════════════════════════════════════════════════════════════════
  // FALLBACK LOCAL (BroadcastChannel + localStorage)
  // ═══════════════════════════════════════════════════════════════════════

  _initLocal() {
    this._HISTORY_KEY = 'dg_chat_history';

    try {
      const raw = localStorage.getItem(this._HISTORY_KEY);
      this._history = raw ? JSON.parse(raw) : [];
    } catch { this._history = []; }

    this._markReady();

    if (typeof BroadcastChannel !== 'undefined') {
      this._bc = new BroadcastChannel('descrigeek_chat');
      this._bc.onmessage = ({ data }) => {
        if (!data) return;
        if (data.type === 'MSG') {
          this._history.push(data.msg);
          this._saveLocal();
          this._incrementUnread();
          this._handlers.forEach(h => h(data.msg));
        } else if (data.type === 'BELL') {
          this._bellHandlers.forEach(h => h(data.bell));
        }
      };
    } else {
      window.addEventListener('storage', e => {
        if (e.key === 'dg_chat_bc' && e.newValue) {
          try {
            const d = JSON.parse(e.newValue);
            if (d.type === 'MSG') {
              this._history.push(d.msg); this._saveLocal();
              this._incrementUnread(); this._handlers.forEach(h => h(d.msg));
            } else if (d.type === 'BELL') {
              this._bellHandlers.forEach(h => h(d.bell));
            }
          } catch {}
        }
      });
    }
  }

  _saveLocal() {
    try { localStorage.setItem(this._HISTORY_KEY, JSON.stringify(this._history.slice(-200))); } catch {}
  }

  _broadcastLocal(data) {
    if (this._bc) {
      this._bc.postMessage(data);
    } else {
      localStorage.setItem('dg_chat_bc', JSON.stringify(data));
      setTimeout(() => localStorage.removeItem('dg_chat_bc'), 100);
    }
  }

  // ═══════════════════════════════════════════════════════════════════════
  // API PUBLIQUE
  // ═══════════════════════════════════════════════════════════════════════

  sendMessage(text) {
    const avatarUrl = window._avatarSvc ? window._avatarSvc.getAvatarUrl(this.username) : null;
    const id = (typeof crypto !== 'undefined' && crypto.randomUUID)
      ? crypto.randomUUID() : Date.now().toString();

    const localMsg = {
      id, username: this.username, from: this.displayName,
      text, avatar: avatarUrl, timestamp: new Date().toISOString(),
    };

    this._history.push(localMsg);

    if (window._supabase) {
      // ⚡ SUPABASE — INSERT
      this._sentIds.add(id);
      window._supabase.from('messages').insert({
        id, username: this.username, display_name: this.displayName,
        text, avatar_url: avatarUrl, timestamp: localMsg.timestamp,
      }).then(({ error }) => {
        if (error) { console.error('[Chat] Erreur envoi :', error.message); this._sentIds.delete(id); }
      });
    } else {
      this._saveLocal();
      this._broadcastLocal({ type: 'MSG', msg: localMsg });
    }

    return localMsg;
  }

  sendBell() {
    const bell = { username: this.username, from: this.displayName, timestamp: new Date().toISOString() };
    if (window._supabase && this._sbChannel) {
      // ⚡ SUPABASE — Broadcast éphémère (pas stocké en DB)
      this._sbChannel.send({ type: 'broadcast', event: 'bell', payload: bell });
    } else {
      this._broadcastLocal({ type: 'BELL', bell });
    }
  }

  onMessage(handler)  { this._handlers.push(handler); }
  onBell(handler)     { this._bellHandlers.push(handler); }
  onReady(handler)    { this._ready ? handler() : this._readyHandlers.push(handler); }

  getHistory()        { return this._history; }
  getUnreadCount()    { return parseInt(localStorage.getItem(this._UNREAD_KEY) || '0', 10); }
  markAllRead()       { localStorage.setItem(this._UNREAD_KEY, '0'); }
  _markReady()        { this._ready = true; this._readyHandlers.forEach(h => h()); }
  _incrementUnread()  { localStorage.setItem(this._UNREAD_KEY, String(this.getUnreadCount() + 1)); }

  destroy() { this._sbChannel?.unsubscribe(); this._bc?.close(); }
}

window.ChatService = ChatService;
