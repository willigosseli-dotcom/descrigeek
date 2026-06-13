"""Normalisation automatique de la terminologie RV française.

Convertit les termes saisis informellement (abréviations, anglais, fautes)
en termes techniques français québécois officiels avant envoi à l'IA.
"""
import json
import re
import unicodedata
from pathlib import Path

TERMINOLOGY_PATH = Path("config/terminology.json")

# Termes supplémentaires hardcodés pour les cas courants non couverts par le fichier
EXTRA_CORRECTIONS = {
    # Vérins / jacks
    "verin avant": "Vérin électrique avant",
    "jack avant": "Vérin électrique avant",
    "jack de langue": "Vérin électrique avant",
    "tongue jack": "Vérin électrique avant",
    "verin electrique": "Vérin électrique avant",
    "verin": "Vérin électrique avant",

    # Portes
    "porte laterale": "Porte piéton latérale",
    "porte pietonne": "Porte piéton latérale",
    "side door": "Porte piéton latérale",
    "entry door": "Porte piéton latérale",

    # Auvent
    "awning": "Auvent",
    "store": "Auvent",
    "auvent electrique": "Auvent électrique",
    "power awning": "Auvent électrique",

    # Stabilisateurs
    "jacks stabilisateurs": "Vérins stabilisateurs",
    "stabilizer jacks": "Vérins stabilisateurs",
    "stabilisateurs": "Vérins stabilisateurs",
    "pieds stabilisateurs": "Vérins stabilisateurs",
    "jacks electriques": "Vérins électriques",

    # Extension coulissante
    "slide": "Extension coulissante",
    "slideout": "Extension coulissante",
    "coulissant": "Extension coulissante",
    "extension": "Extension coulissante",
    "slide out": "Extension coulissante",

    # Panneaux solaires
    "solar": "Panneau solaire",
    "solaire": "Panneau solaire",
    "panneaux solaires": "Panneaux solaires",

    # Réservoirs
    "tank eau propre": "Réservoir d'eau potable",
    "fresh water": "Réservoir d'eau potable",
    "grey water": "Réservoir d'eaux grises",
    "gray water": "Réservoir d'eaux grises",
    "black water": "Réservoir d'eaux noires",
    "eaux usees": "Réservoir d'eaux noires",

    # Attelage
    "hitch": "Attelage",
    "boule d'attelage": "Attelage",
    "weight distribution": "Attelage à distribution de poids",
    "distribution de poids": "Attelage à distribution de poids",

    # Climatisation / chauffage
    "ac": "Climatiseur",
    "air conditionne": "Climatiseur",
    "air conditioning": "Climatiseur",
    "a/c": "Climatiseur",
    "furnace": "Fournaise",
    "heat pump": "Thermopompe",
    "pompe a chaleur": "Thermopompe",

    # Chauffe-eau
    "chauffe eau": "Chauffe-eau",
    "water heater": "Chauffe-eau",
    "hot water": "Chauffe-eau",
    "tankless": "Chauffe-eau sans réservoir",

    # Caméra
    "camera recul": "Caméra de recul",
    "backup cam": "Caméra de recul",
    "backup camera": "Caméra de recul",

    # Génératrice
    "generatrice": "Génératrice",
    "generator": "Génératrice",
    "gen": "Génératrice",

    # Soubassement
    "underbelly": "Soubassement fermé",
    "enclosed underbelly": "Soubassement fermé",
    "heated underbelly": "Soubassement chauffé",
    "soubassement chauffe": "Soubassement chauffé",
    "soubassement ferme": "Soubassement fermé",

    # Lits
    "queen": "Lit de grandeur queen",
    "king": "Lit de grandeur king",
    "bunk": "Lits superposés",
    "bunks": "Lits superposés",
    "lits superposes": "Lits superposés",

    # Autres
    "pass-through": "Rangement traversant",
    "pass through": "Rangement traversant",
    "rangement traversant": "Rangement traversant",
    "outdoor kitchen": "Cuisine extérieure",
    "cuisine exterieure": "Cuisine extérieure",
    "foyer": "Foyer",
    "fireplace": "Foyer",
    "skylight": "Lanterneau",
    "lanterneau": "Lanterneau",
    "tank monitor": "Panneau de surveillance des réservoirs",
    "50 amp": "Service 50 ampères",
    "30 amp": "Service 30 ampères",
    "leveling": "Système de mise à niveau",
    "mise a niveau": "Système de mise à niveau",
    "auto level": "Mise à niveau automatique",
    "auto leveling": "Mise à niveau automatique",
}


def _remove_accents(text: str) -> str:
    return ''.join(
        c for c in unicodedata.normalize('NFD', text)
        if unicodedata.category(c) != 'Mn'
    )


def _normalize_key(text: str) -> str:
    return _remove_accents(text.lower().strip())


def _build_correction_map() -> dict:
    """Construit le dictionnaire de corrections depuis le fichier + les extras."""
    corrections = {}

    # Extras hardcodés
    for k, v in EXTRA_CORRECTIONS.items():
        corrections[_normalize_key(k)] = v

    # Fichier terminology.json
    try:
        with open(TERMINOLOGY_PATH, encoding="utf-8") as f:
            data = json.load(f)
        for term in data.get("terms", []):
            en = term.get("en", "")
            fr = term.get("fr", "")
            if en and fr:
                corrections[_normalize_key(en)] = fr
            if fr:
                # La version sans accent du terme FR pointe vers lui-même (correction orthographique)
                corrections[_normalize_key(fr)] = fr
    except Exception:
        pass

    return corrections


def normalize_user_input(text: str) -> tuple[str, list[str]]:
    """
    Normalise le texte de l'utilisateur en appliquant la terminologie correcte.
    Retourne (texte_corrigé, liste_des_corrections_appliquées).
    """
    if not text or not text.strip():
        return text, []

    corrections_map = _build_correction_map()
    corrections_applied = []

    # Traiter ligne par ligne pour préserver la mise en forme
    lines = text.split('\n')
    result_lines = []

    for line in lines:
        corrected_line = line
        # Trier par longueur décroissante pour éviter les substitutions partielles
        sorted_keys = sorted(corrections_map.keys(), key=len, reverse=True)

        for key in sorted_keys:
            value = corrections_map[key]
            # Chercher le terme dans la ligne (insensible à la casse et aux accents)
            pattern = re.compile(
                r'\b' + re.escape(key.replace(' ', r'\s+')) + r'\b',
                re.IGNORECASE
            )
            # Normaliser la ligne pour la comparaison
            line_normalized = _normalize_key(corrected_line)
            if key in line_normalized:
                # Remplacer dans le texte original en préservant la ponctuation
                def replace_match(m):
                    original = m.group(0)
                    if original.lower() != value.lower():
                        corrections_applied.append(f'"{original}" → "{value}"')
                    return value

                # Essayer une substitution tolérante aux accents
                re_pattern = re.compile(
                    r'(?i)' + re.escape(key).replace(r'\ ', r'[\s\-]+'),
                    re.IGNORECASE
                )
                new_line = re_pattern.sub(replace_match, corrected_line, count=1)
                if new_line != corrected_line:
                    corrected_line = new_line

        result_lines.append(corrected_line)

    corrected_text = '\n'.join(result_lines)
    # Dédupliquer les corrections
    corrections_applied = list(dict.fromkeys(corrections_applied))
    return corrected_text, corrections_applied
