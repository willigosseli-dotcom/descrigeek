"""Génération de descriptions via Claude (Anthropic)."""
import os
import json
from pathlib import Path

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
DEMO_MODE = os.getenv("DEMO_MODE", "true").lower() == "true"

SETTINGS_PATH = Path("config/settings.json")
TERMINOLOGY_PATH = Path("config/terminology.json")


def _load_settings() -> dict:
    with open(SETTINGS_PATH, encoding="utf-8") as f:
        return json.load(f)


def _load_terminology() -> list:
    with open(TERMINOLOGY_PATH, encoding="utf-8") as f:
        data = json.load(f)
    return data.get("terms", [])


def _build_terminology_block(terms: list) -> str:
    if not terms:
        return ""
    lines = [f'- "{t["en"]}" → "{t["fr"]}"' for t in terms[:40]]
    return "TERMINOLOGIE FRANÇAISE OBLIGATOIRE (utilise ces traductions exactes) :\n" + "\n".join(lines)


def _build_examples_block(examples: list) -> str:
    if not examples:
        return ""
    block = "EXEMPLES DE DESCRIPTIONS MODÈLES (reproduis ce style, ce ton et cette structure — ne copie pas le contenu) :\n\n"
    for ex in examples[:3]:
        block += f"--- Exemple : {ex.get('title', '')} ({ex.get('vehicle_type', 'tous types')}) ---\n"
        block += ex.get("content", "")[:1200]
        block += "\n\n"
    return block


async def generate_description(
    year: int,
    make: str,
    model: str,
    vehicle_type: str,
    specs_text: str,
    options_accessories: str,
    unique_features: str,
    examples: list,
    adjustment_note: str = "",
) -> dict:
    """Génère une description complète. Retourne dict avec description, target_audience, warnings."""

    if DEMO_MODE or not ANTHROPIC_API_KEY or ANTHROPIC_API_KEY == "your_anthropic_key_here":
        settings = _load_settings()
        closing = settings.get("closing_paragraph", "")
        return _demo_description(year, make, model, vehicle_type, closing,
                                 options_accessories, unique_features)

    settings = _load_settings()
    terms = _load_terminology()
    closing = settings.get("closing_paragraph", "")
    dealer = settings.get("dealership", {})

    terminology_block = _build_terminology_block(terms)
    examples_block = _build_examples_block(examples)

    adjustment_block = ""
    if adjustment_note:
        adjustment_block = f"\nCONSIGNE D'AJUSTEMENT DE L'UTILISATEUR : {adjustment_note}\n"

    system_prompt = f"""Tu es un rédacteur spécialisé en véhicules récréatifs (VR) pour le concessionnaire {dealer.get('name', 'VR Thetford')} au Québec.
Tu rédiges des descriptions de vente en français québécois, professionnelles et chaleureuses.

RÈGLES ABSOLUES :
1. Jamais d'emojis dans les descriptions.
2. Utilise le français québécois standard (pas d'anglicismes inutiles).
3. Les dimensions doivent toujours être en pouces ET en pieds.
4. Ne jamais inventer de spécifications. Si une donnée est manquante, indique "à vérifier".
5. Ton professionnel mais chaleureux — pas froid, pas trop vendeur/exagéré.
6. Les OPTIONS ET ACCESSOIRES et les PARTICULARITÉS UNIQUES fournis par l'utilisateur sont des informations VÉRIFIÉES et PRIORITAIRES. Tu DOIS les intégrer dans la description et dans la liste à puces — chaque option et chaque particularité doit apparaître. Ne les ignore jamais.
7. Corrige automatiquement tout terme technique en utilisant la terminologie française exacte ci-dessous, même si l'utilisateur a utilisé un terme anglais ou informel.

{terminology_block}

FORMAT DE LA DESCRIPTION (respecte exactement cette structure) :
1. Un paragraphe d'introduction vendeur (3-4 phrases) — mentionne les particularités uniques si elles sont valorisantes
2. Une liste à puces des spécifications techniques ET de TOUS les équipements/options (15-25 puces minimum) — inclure TOUTES les options saisies par l'utilisateur
3. Ne PAS ajouter de paragraphe de fermeture — il sera ajouté automatiquement après la génération

{examples_block}

Réponds en JSON avec exactement ces clés :
{{
  "description": "la description complète selon le format",
  "target_audience": "paragraphe de 3-4 phrases identifiant la clientèle cible et expliquant pourquoi ce véhicule lui convient",
  "warnings": ["liste des specs manquantes ou données à vérifier — vide si tout est OK"]
}}"""

    user_prompt = f"""Génère une description de vente pour ce véhicule :

Véhicule : {year} {make} {model} ({vehicle_type})

SPÉCIFICATIONS DU MODÈLE (données de base) :
{specs_text}

OPTIONS ET ACCESSOIRES INSTALLÉS SUR CETTE UNITÉ (information prioritaire et vérifiée — TOUS doivent apparaître dans la liste à puces) :
{options_accessories if options_accessories and options_accessories.strip() else "Aucune option additionnelle spécifiée"}

PARTICULARITÉS UNIQUES DE CETTE UNITÉ (mettre en valeur dans l'intro ou dans les puces) :
{unique_features if unique_features and unique_features.strip() else "Aucune particularité unique spécifiée"}
{adjustment_block}"""

    try:
        import anthropic
        client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
        message = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=2500,
            system=system_prompt,
            messages=[{"role": "user", "content": user_prompt}],
        )
        content = message.content[0].text.strip()

        # Parser le JSON
        if "```json" in content:
            content = content.split("```json")[1].split("```")[0].strip()
        elif "```" in content:
            content = content.split("```")[1].split("```")[0].strip()

        result = json.loads(content)
        description = result.get("description", "")
        if closing and closing not in description:
            description = description.rstrip() + "\n\n" + closing
        return {
            "description": description,
            "target_audience": result.get("target_audience", ""),
            "warnings": result.get("warnings", []),
        }

    except json.JSONDecodeError:
        # Si le JSON est mal formé, retourner le texte brut
        return {
            "description": content,
            "target_audience": "",
            "warnings": ["Impossible de parser la réponse de l'IA — vérifiez manuellement."],
        }
    except Exception as e:
        return {
            "description": "",
            "target_audience": "",
            "warnings": [f"Erreur lors de la génération : {str(e)}"],
            "error": True,
        }


def _demo_description(year: int, make: str, model: str, vehicle_type: str, closing: str = "",
                      options_accessories: str = "", unique_features: str = "") -> dict:
    """Description de démonstration sans clés API."""
    body = f"""Le {year} {make} {model} est un {vehicle_type.lower() if vehicle_type else 'véhicule récréatif'} remarquable qui allie confort, praticité et qualité de construction. Conçu pour les familles et les couples qui souhaitent explorer le Québec et ses régions en toute sérénité, ce modèle se distingue par son aménagement intérieur soigné et ses équipements complets. Que ce soit pour un weekend en pleine nature ou un voyage de plusieurs semaines, le {make} {model} saura répondre à vos attentes.

• Longueur extérieure : 28 pi (336 po)
• Largeur extérieure : 8 pi (96 po)
• Hauteur extérieure : 11 pi (132 po)
• Poids à vide : 5 200 lb
• PNBV (Poids nominal brut du véhicule) : 7 500 lb
• Capacité de chargement utile : 2 300 lb
• Extension coulissante : 1 coulisseau côté salon
• Lit de grandeur queen en chambre arrière séparée
• Salle de bain complète avec douche, toilette et lavabo
• Cuisine équipée : réfrigérateur, cuisinière 3 feux, four à micro-ondes
• Fournaise : 30 000 BTU
• Climatiseur : 13 500 BTU
• Réservoir d'eau potable : 45 gallons
• Réservoir d'eaux grises : 35 gallons
• Réservoir d'eaux noires : 30 gallons
• Réservoir de propane : 2 x 20 lb
• Auvent électrique 16 pi
• Soubassement fermé et isolé"""

    # Ajouter les options saisies par l'utilisateur
    if options_accessories and options_accessories.strip():
        extra_lines = "\n".join(f"• {line.strip().lstrip('•-').strip()}"
                                for line in options_accessories.splitlines()
                                if line.strip())
        body += "\n" + extra_lines

    if unique_features and unique_features.strip():
        body += f"\n\n{unique_features.strip()}"

    body += "\n\n---\nNOTE : Ceci est une description de démonstration. Configurez vos clés API dans le fichier .env pour générer de vraies descriptions avec Claude."

    desc = body.rstrip() + ("\n\n" + closing if closing else "")

    audience = f"Le {year} {make} {model} s'adresse particulièrement aux couples et aux petites familles qui recherchent un premier véhicule récréatif polyvalent. Son aménagement bien pensé et son rapport qualité-prix en font un choix idéal pour les campeurs débutants comme expérimentés. Les retraités actifs apprécieront également le confort de la chambre arrière séparée et l'espace de vie généreux."

    return {
        "description": desc,
        "target_audience": audience,
        "warnings": ["MODE DÉMONSTRATION — Configurez ANTHROPIC_API_KEY dans .env pour de vraies descriptions."],
        "is_demo": True,
    }
