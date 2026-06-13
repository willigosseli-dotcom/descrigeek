"""
Client Supabase partagé pour le backend Python.
Utilisé uniquement pour notifier les autres utilisateurs quand une nouvelle
description est générée (table descriptions_events).

Remplacer SUPABASE_KEY par la clé service_role pour bypasser RLS côté serveur.
"""

import os
from typing import Optional

SUPABASE_URL = "https://qhmgomzhrvbtqinujtpy.supabase.co"
# Clé anon publique (suffisant avec les politiques RLS INSERT ouvertes)
# Pour la prod, utiliser la clé service_role depuis une variable d'environnement
SUPABASE_KEY = os.getenv(
    "SUPABASE_KEY",
    "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9"
    ".eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InFobWdvbXpocnZidHFpbnVqdHB5Iiwicm9sZSI6ImFub24iLCJpYXQiOjE3ODEzMDMwMzAsImV4cCI6MjA5Njg3OTAzMH0"
    ".LutDwaa-V9Pg8oa9rE1kfJOO-HSREnKkZ9o97Zuswj8",
)

_client = None


def get_supabase():
    global _client
    if _client is not None:
        return _client
    try:
        from supabase import create_client
        _client = create_client(SUPABASE_URL, SUPABASE_KEY)
        return _client
    except Exception as e:
        print(f"[Supabase] Client non disponible : {e}")
        return None


async def notify_new_description(
    desc_id: int,
    username: str,
    display_name: str,
    vehicle: str,
    stock_number: Optional[str] = None,
) -> None:
    """Insère un événement dans descriptions_events pour déclencher le Realtime."""
    sb = get_supabase()
    if sb is None:
        return
    try:
        sb.table("descriptions_events").insert({
            "desc_id":      desc_id,
            "username":     username,
            "display_name": display_name,
            "vehicle":      vehicle,
            "stock_number": stock_number,
        }).execute()
    except Exception as e:
        print(f"[Supabase] Erreur notify_new_description : {e}")
