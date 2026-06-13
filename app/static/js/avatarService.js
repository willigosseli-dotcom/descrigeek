/**
 * DescriGeek — Avatar Service
 *
 * BACKEND ACTUEL : Supabase Storage (bucket « avatars ») + table « profils »
 *                  + Realtime Broadcast pour sync entre onglets/appareils
 * FALLBACK       : localStorage base64 + BroadcastChannel (si Supabase non dispo)
 *
 * Interface publique (inchangée) :
 *   .getAvatar(username)         → URL string (synchrone depuis cache)
 *   .getAvatarUrl(username)      → URL publique Supabase ou null
 *   .setAvatar(username, dataUrl)→ Promise
 *   .processFile(file, maxSize)  → Promise<dataUrl>
 *   .getDefault(username)        → SVG data URL
 *   .onUpdate(handler)
 */

class AvatarService {
  constructor() {
    this._cache     = {};
    this._handlers  = [];
    this._LS_PREFIX = 'dg_avatar_';

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

    // Pré-charger tous les profils pour que getAvatar() soit synchrone
    try {
      const { data } = await sb.from('profils').select('username, avatar_url');
      if (data) {
        data.forEach(p => { if (p.avatar_url) this._cache[p.username] = p.avatar_url; });
      }
    } catch (e) {
      console.warn('[Avatar] Impossible de charger les profils :', e);
    }

    // S'abonner aux broadcasts de mise à jour d'avatar
    this._sbChannel = sb.channel('descrigeek-avatars', {
      config: { broadcast: { self: false } },
    });
    this._sbChannel
      .on('broadcast', { event: 'avatar_update' }, ({ payload }) => {
        if (payload?.username && payload?.avatar_url) {
          this._cache[payload.username] = payload.avatar_url;
          this._handlers.forEach(h => h(payload.username, payload.avatar_url));
        }
      })
      .subscribe();
  }

  // ═══════════════════════════════════════════════════════════════════════
  // FALLBACK LOCAL (BroadcastChannel + localStorage)
  // ═══════════════════════════════════════════════════════════════════════

  _initLocal() {
    if (typeof BroadcastChannel !== 'undefined') {
      this._bc = new BroadcastChannel('descrigeek_avatars');
      this._bc.onmessage = ({ data }) => {
        if (!data || data.type !== 'AVATAR_UPDATE') return;
        this._cache[data.username] = data.avatar;
        try { localStorage.setItem(this._LS_PREFIX + data.username, data.avatar); } catch {}
        this._handlers.forEach(h => h(data.username, data.avatar));
      };
    } else {
      window.addEventListener('storage', e => {
        if (e.key === 'dg_avatar_broadcast' && e.newValue) {
          try {
            const d = JSON.parse(e.newValue);
            if (d.type === 'AVATAR_UPDATE') {
              this._cache[d.username] = d.avatar;
              this._handlers.forEach(h => h(d.username, d.avatar));
            }
          } catch {}
        }
      });
    }
  }

  // ═══════════════════════════════════════════════════════════════════════
  // API PUBLIQUE
  // ═══════════════════════════════════════════════════════════════════════

  /** Retourne l'URL de l'avatar (cache -> localStorage -> SVG). Toujours synchrone. */
  getAvatar(username) {
    if (this._cache[username]) return this._cache[username];
    if (!window._supabase) {
      const stored = localStorage.getItem(this._LS_PREFIX + username);
      if (stored) { this._cache[username] = stored; return stored; }
    }
    return this.getDefault(username);
  }

  /** URL publique Supabase ou null (pour stocker dans la table messages). */
  getAvatarUrl(username) {
    const av = this.getAvatar(username);
    return av.startsWith('data:image/svg') ? null : av;
  }

  /** Upload + mise a jour profil + broadcast. */
  async setAvatar(username, dataUrl) {
    if (window._supabase) {
      await this._setAvatarSupabase(username, dataUrl);
    } else {
      this._setAvatarLocal(username, dataUrl);
    }
  }

  async _setAvatarSupabase(username, dataUrl) {
    const sb = window._supabase;

    // Convertir dataUrl -> Blob
    const blob = await (await fetch(dataUrl)).blob();
    const path = `${username}.jpg`;

    // SUPABASE STORAGE - upload (upsert)
    const { error: uploadErr } = await sb.storage
      .from('avatars')
      .upload(path, blob, { contentType: 'image/jpeg', upsert: true });

    if (uploadErr) throw new Error('Upload echoue : ' + uploadErr.message);

    const publicUrl = `${window._SUPABASE_URL}/storage/v1/object/public/avatars/${path}`;

    // SUPABASE - upsert dans la table profils
    await sb.from('profils').upsert({
      username,
      display_name: window.CHAT_USER ? window.CHAT_USER.displayName : username,
      avatar_url:   publicUrl,
      updated_at:   new Date().toISOString(),
    }, { onConflict: 'username' });

    this._cache[username] = publicUrl;

    // SUPABASE - Broadcast vers les autres onglets/appareils
    if (this._sbChannel) {
      this._sbChannel.send({
        type: 'broadcast', event: 'avatar_update',
        payload: { username, avatar_url: publicUrl },
      });
    }

    this._handlers.forEach(h => h(username, publicUrl));
  }

  _setAvatarLocal(username, dataUrl) {
    try { localStorage.setItem(this._LS_PREFIX + username, dataUrl); } catch {}
    this._cache[username] = dataUrl;
    const data = { type: 'AVATAR_UPDATE', username, avatar: dataUrl };
    if (this._bc) {
      this._bc.postMessage(data);
    } else {
      localStorage.setItem('dg_avatar_broadcast', JSON.stringify(data));
      setTimeout(() => localStorage.removeItem('dg_avatar_broadcast'), 100);
    }
    this._handlers.forEach(h => h(username, dataUrl));
  }

  onUpdate(handler) { this._handlers.push(handler); }

  /** Avatar SVG par defaut - initiales + couleur deterministe. */
  getDefault(username) {
    const initials = (username || '?').substring(0, 2).toUpperCase();
    const hue = [...(username || '')].reduce((h, c) => h + c.charCodeAt(0), 0) % 360;
    const svg = `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 80 80">
      <circle cx="40" cy="40" r="40" fill="hsl(${hue},52%,42%)"/>
      <text x="40" y="53" text-anchor="middle"
            font-family="'Segoe UI',system-ui,sans-serif"
            font-size="30" font-weight="700" fill="white">${initials}</text>
    </svg>`;
    return 'data:image/svg+xml;base64,' + btoa(unescape(encodeURIComponent(svg)));
  }

  /** Crop + resize Canvas -> JPEG base64. */
  async processFile(file, maxSize = 200) {
    return new Promise((resolve, reject) => {
      if (!file || !file.type.startsWith('image/')) { reject(new Error('Fichier invalide')); return; }
      const reader = new FileReader();
      reader.onerror = reject;
      reader.onload = ({ target: { result } }) => {
        const img = new Image();
        img.onerror = reject;
        img.onload = () => {
          const canvas = document.createElement('canvas');
          canvas.width = maxSize; canvas.height = maxSize;
          const ctx  = canvas.getContext('2d');
          const side = Math.min(img.width, img.height);
          const sx   = (img.width  - side) / 2;
          const sy   = (img.height - side) / 2;
          ctx.drawImage(img, sx, sy, side, side, 0, 0, maxSize, maxSize);
          resolve(canvas.toDataURL('image/jpeg', 0.88));
        };
        img.src = result;
      };
      reader.readAsDataURL(file);
    });
  }

  destroy() { if (this._sbChannel) this._sbChannel.unsubscribe(); if (this._bc) this._bc.close(); }
}

window.AvatarService = AvatarService;
