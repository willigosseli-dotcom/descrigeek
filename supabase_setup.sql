-- ═══════════════════════════════════════════════════════════════════════
--  DescriGeek — Script de configuration Supabase
--  À exécuter UNE SEULE FOIS dans l'éditeur SQL de ton projet Supabase
-- ═══════════════════════════════════════════════════════════════════════

-- ── 1. Table chat (messages) ────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS public.messages (
  id           UUID        DEFAULT gen_random_uuid() PRIMARY KEY,
  username     TEXT        NOT NULL,
  display_name TEXT        NOT NULL,
  text         TEXT        NOT NULL,
  avatar_url   TEXT,
  timestamp    TIMESTAMPTZ DEFAULT NOW()
);

-- ── 2. Table profils utilisateurs ──────────────────────────────────────
CREATE TABLE IF NOT EXISTS public.profils (
  username     TEXT PRIMARY KEY,
  display_name TEXT,
  avatar_url   TEXT,
  updated_at   TIMESTAMPTZ DEFAULT NOW()
);

-- ── 3. Table descriptions (notifications temps réel) ───────────────────
CREATE TABLE IF NOT EXISTS public.descriptions_events (
  id           BIGSERIAL   PRIMARY KEY,
  desc_id      INTEGER     NOT NULL,
  username     TEXT        NOT NULL,
  display_name TEXT        NOT NULL,
  vehicle      TEXT        NOT NULL,   -- ex. "2024 Jayco Eagle"
  stock_number TEXT,
  created_at   TIMESTAMPTZ DEFAULT NOW()
);

-- ── 4. Activer Row Level Security ──────────────────────────────────────
ALTER TABLE public.messages           ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.profils            ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.descriptions_events ENABLE ROW LEVEL SECURITY;

-- ── 5. Politiques : tout le monde peut lire et insérer, personne ne supprime ──
-- Messages
DROP POLICY IF EXISTS "anon_select_messages" ON public.messages;
DROP POLICY IF EXISTS "anon_insert_messages" ON public.messages;
CREATE POLICY "anon_select_messages" ON public.messages FOR SELECT TO anon USING (true);
CREATE POLICY "anon_insert_messages" ON public.messages FOR INSERT TO anon WITH CHECK (true);

-- Profils
DROP POLICY IF EXISTS "anon_select_profils" ON public.profils;
DROP POLICY IF EXISTS "anon_insert_profils" ON public.profils;
DROP POLICY IF EXISTS "anon_update_profils" ON public.profils;
CREATE POLICY "anon_select_profils"  ON public.profils FOR SELECT TO anon USING (true);
CREATE POLICY "anon_insert_profils"  ON public.profils FOR INSERT TO anon WITH CHECK (true);
CREATE POLICY "anon_update_profils"  ON public.profils FOR UPDATE TO anon USING (true) WITH CHECK (true);

-- Descriptions events
DROP POLICY IF EXISTS "anon_select_desc" ON public.descriptions_events;
DROP POLICY IF EXISTS "anon_insert_desc" ON public.descriptions_events;
CREATE POLICY "anon_select_desc" ON public.descriptions_events FOR SELECT TO anon USING (true);
CREATE POLICY "anon_insert_desc" ON public.descriptions_events FOR INSERT TO anon WITH CHECK (true);

-- ── 6. Activer Realtime sur les 3 tables ───────────────────────────────
-- Si "already member" → ignorer l'erreur
ALTER PUBLICATION supabase_realtime ADD TABLE public.messages;
ALTER PUBLICATION supabase_realtime ADD TABLE public.profils;
ALTER PUBLICATION supabase_realtime ADD TABLE public.descriptions_events;

-- ── 7. Bucket Storage pour les photos de profil ────────────────────────
INSERT INTO storage.buckets (id, name, public, file_size_limit, allowed_mime_types)
VALUES (
  'avatars', 'avatars', true,
  5242880,   -- 5 Mo max
  ARRAY['image/jpeg','image/png','image/webp']
)
ON CONFLICT (id) DO NOTHING;

-- Policies storage : lecture publique, écriture anon
DROP POLICY IF EXISTS "avatars_public_select" ON storage.objects;
DROP POLICY IF EXISTS "avatars_anon_insert"   ON storage.objects;
DROP POLICY IF EXISTS "avatars_anon_update"   ON storage.objects;

CREATE POLICY "avatars_public_select" ON storage.objects
  FOR SELECT USING (bucket_id = 'avatars');

CREATE POLICY "avatars_anon_insert" ON storage.objects
  FOR INSERT TO anon WITH CHECK (bucket_id = 'avatars');

CREATE POLICY "avatars_anon_update" ON storage.objects
  FOR UPDATE TO anon USING (bucket_id = 'avatars');
