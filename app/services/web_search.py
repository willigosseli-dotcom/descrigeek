"""Recherche web des specs via Tavily, avec priorité aux sites fabricants."""
import os
import httpx

TAVILY_API_KEY = os.getenv("TAVILY_API_KEY", "")

# Sites fabricants prioritaires (domaines officiels)
MANUFACTURER_DOMAINS = [
    "jayco.com", "thor.com", "forestriverinc.com", "coachmen.com",
    "keystone-rv.com", "gulfstreamcoach.com", "winnebago.com",
    "airstream.com", "palominorv.com", "crossroadsrv.com",
    "granddesignrv.com", "newmarrv.com", "tiffin.com",
    "polaris.com", "polarisoffroad.com", "polarissnowmobiles.com",
    "can-am.brp.com", "kawasaki.com", "yamaha-motor.ca",
    "arctic-cat.com", "skidoo.com", "ski-doo.com", "brp.com",
    "ezgo.com", "clubcar.com", "yamahalinksys.com",
    "atvtrader.com", "rvtrader.com",  # bases de données reconnues
    "rvusa.com", "rvidirect.com",
]

DEMO_MODE = os.getenv("DEMO_MODE", "true").lower() == "true"


async def search_vehicle_specs(year: int, make: str, model: str, vehicle_type: str = "") -> dict | None:
    """Recherche les specs sur le web. Retourne dict avec specs, source_url, source_name."""
    if DEMO_MODE or not TAVILY_API_KEY or TAVILY_API_KEY == "your_tavily_key_here":
        return _demo_specs(year, make, model, vehicle_type)

    query = f"{year} {make} {model} {vehicle_type} specifications specs dimensions weight".strip()

    # Tentative 1 : sites fabricants
    result = await _tavily_search(query, include_domains=_get_manufacturer_domains(make))
    if result:
        return result

    # Tentative 2 : recherche large avec filtrage
    result = await _tavily_search(query, include_domains=None)
    return result


async def _tavily_search(query: str, include_domains: list | None) -> dict | None:
    payload = {
        "api_key": TAVILY_API_KEY,
        "query": query,
        "search_depth": "advanced",
        "max_results": 5,
        "include_answer": True,
    }
    if include_domains:
        payload["include_domains"] = include_domains

    # Exclure sources peu fiables
    payload["exclude_domains"] = [
        "reddit.com", "facebook.com", "craigslist.org",
        "kijiji.ca", "autotrader.ca", "marketplace.facebook.com",
    ]

    try:
        async with httpx.AsyncClient(timeout=20) as client:
            resp = await client.post("https://api.tavily.com/search", json=payload)
            resp.raise_for_status()
            data = resp.json()
    except Exception:
        return None

    results = data.get("results", [])
    if not results:
        return None

    # Prendre le meilleur résultat
    best = results[0]
    content = best.get("content", "") or data.get("answer", "")

    if len(content) < 100:
        return None

    return {
        "raw_text": content,
        "source_url": best.get("url", ""),
        "source_name": best.get("title", "Recherche web"),
        "source_type": "web",
        "all_results": [{"url": r.get("url"), "title": r.get("title")} for r in results[:3]],
    }


def _get_manufacturer_domains(make: str) -> list:
    """Retourne les domaines prioritaires pour un fabricant donné."""
    make_lower = make.lower()
    known = {
        "jayco": ["jayco.com"],
        "polaris": ["polaris.com", "polarisoffroad.com"],
        "arctic cat": ["arctic-cat.com"],
        "ski-doo": ["ski-doo.com", "brp.com"],
        "skidoo": ["ski-doo.com", "brp.com"],
        "can-am": ["can-am.brp.com", "brp.com"],
        "yamaha": ["yamaha-motor.ca", "yamaha-motor.com"],
        "kawasaki": ["kawasaki.com"],
        "coachmen": ["coachmen.com"],
        "forest river": ["forestriverinc.com"],
        "keystone": ["keystone-rv.com"],
        "grand design": ["granddesignrv.com"],
        "winnebago": ["winnebago.com"],
        "thor": ["thor.com"],
    }
    for key, domains in known.items():
        if key in make_lower:
            return domains
    # Fallback : essayer le domaine probable
    slug = make_lower.replace(" ", "").replace("-", "")
    return [f"{slug}.com"]


def _demo_specs(year: int, make: str, model: str, vehicle_type: str) -> dict:
    """Données de démonstration quand les clés API ne sont pas configurées."""
    return {
        "raw_text": f"""
DEMO MODE — Spécifications fictives pour {year} {make} {model}
Ces données sont générées automatiquement pour tester l'interface.
Configurez vos clés API dans le fichier .env pour obtenir de vraies spécifications.

Longueur extérieure : 28 pi (336 po)
Largeur extérieure : 8 pi (96 po)
Hauteur extérieure : 11 pi (132 po)
Poids à vide : 5 200 lb
PNBV : 7 500 lb
Capacité de chargement utile : 2 300 lb
Réservoir d'eau potable : 45 gal
Réservoir d'eaux grises : 35 gal
Réservoir d'eaux noires : 30 gal
Réservoir de propane : 2 x 20 lb
Climatiseur : 13 500 BTU
Fournaise : 30 000 BTU
Extension coulissante : 1
""",
        "source_url": "",
        "source_name": "Mode démonstration (clés API non configurées)",
        "source_type": "demo",
        "is_demo": True,
    }
