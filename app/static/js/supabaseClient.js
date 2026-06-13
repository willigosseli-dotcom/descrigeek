/**
 * DescriGeek — Initialisation du client Supabase
 *
 * Ce fichier doit être chargé APRÈS le SDK Supabase (CDN) et AVANT
 * chatService.js, avatarService.js et chat.js.
 *
 * window._supabase  → client Supabase prêt à l'emploi
 *                     (undefined si le SDK n'est pas chargé → fallback local)
 */

(function () {
  const SUPABASE_URL = 'https://qhmgomzhrvbtqinujtpy.supabase.co';
  const SUPABASE_KEY = 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InFobWdvbXpocnZidHFpbnVqdHB5Iiwicm9sZSI6ImFub24iLCJpYXQiOjE3ODEzMDMwMzAsImV4cCI6MjA5Njg3OTAzMH0.LutDwaa-V9Pg8oa9rE1kfJOO-HSREnKkZ9o97Zuswj8';

  try {
    if (window.supabase && typeof window.supabase.createClient === 'function') {
      window._supabase = window.supabase.createClient(SUPABASE_URL, SUPABASE_KEY, {
        realtime: { params: { eventsPerSecond: 10 } },
      });
      console.info('[DescriGeek] Supabase connecté ✓');
    } else {
      console.warn('[DescriGeek] SDK Supabase non disponible — mode local (BroadcastChannel)');
    }
  } catch (e) {
    console.error('[DescriGeek] Erreur init Supabase :', e);
  }

  // Exposer l'URL publique pour construire les URLs Storage
  window._SUPABASE_URL = SUPABASE_URL;
})();
