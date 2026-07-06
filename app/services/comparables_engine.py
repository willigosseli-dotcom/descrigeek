"""Moteur de comparables pour l'évaluation de prix de VR usagés.

Fonctions PURES (aucune dépendance à la base de données) : elles opèrent sur
n'importe quel objet exposant les attributs d'une annonce (ORM `Listing` en
production, `types.SimpleNamespace` dans les tests). Cela rend le moteur
directement testable unitairement.

Règles métier appliquées :
  - Exclusions des médianes : volée, prix USD, prix sur demande/N/D,
    notre propre annonce, projet bricoleur (par défaut).
  - Dédoublonnage : drapeau `is_doublon` OU même (modele, annee, prix, ville).
  - Le prix retenu est TOUJOURS le prix final (`prix_affiche`), jamais le barré.
  - Sélection par priorité : même modèle → même ligne → gabarit similaire.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable, Optional
import statistics
import unicodedata


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #

def _norm(value: Optional[str]) -> str:
    """Minuscule, sans accents, sans espaces superflus — pour comparer du texte."""
    if value is None:
        return ""
    txt = unicodedata.normalize("NFD", str(value))
    txt = "".join(c for c in txt if unicodedata.category(c) != "Mn")
    return txt.strip().lower()


def _get(listing, attr, default=None):
    return getattr(listing, attr, default)


# --------------------------------------------------------------------------- #
# Exclusions
# --------------------------------------------------------------------------- #

def raison_exclusion_totale(listing) -> Optional[str]:
    """Annonces à retirer de TOUTE analyse (jamais affichées comme comparables)."""
    if _get(listing, "is_volee"):
        return "Annonce volée"
    if _get(listing, "is_notre_annonce"):
        return "Notre propre annonce"
    return None


def raison_exclusion_mediane(listing, inclure_bricoleur: bool = False) -> Optional[str]:
    """Annonces à retirer des CALCULS de médiane (mais qui restent visibles).

    Retourne la raison (str) si exclue, sinon None.
    """
    totale = raison_exclusion_totale(listing)
    if totale:
        return totale
    if _get(listing, "is_usd"):
        return "Prix en USD"
    if _get(listing, "is_prix_sur_demande") or _get(listing, "prix_affiche") is None:
        return "Prix sur demande / N/D"
    if _get(listing, "is_projet_bricoleur") and not inclure_bricoleur:
        return "Projet bricoleur"
    return None


def _cle_doublon(listing) -> tuple:
    return (
        _norm(_get(listing, "modele")),
        _get(listing, "annee"),
        _get(listing, "prix_affiche"),
        _norm(_get(listing, "ville") or _get(listing, "localisation")),
    )


def dedoublonner(listings: Iterable) -> list:
    """Garde une seule occurrence par annonce identique.

    Un doublon = drapeau `is_doublon` OU même (modele, annee, prix, ville).
    """
    vues: set = set()
    resultat: list = []
    for l in listings:
        if _get(l, "is_doublon"):
            # Signalé explicitement comme doublon : on ne le garde que si sa clé
            # n'a pas déjà été vue.
            cle = _cle_doublon(l)
            if cle in vues:
                continue
            vues.add(cle)
            resultat.append(l)
            continue
        cle = _cle_doublon(l)
        if cle in vues:
            continue
        vues.add(cle)
        resultat.append(l)
    return resultat


# --------------------------------------------------------------------------- #
# Statistiques
# --------------------------------------------------------------------------- #

def _percentile(valeurs_triees: list, p: float) -> float:
    """Percentile par interpolation linéaire (p entre 0 et 100)."""
    if not valeurs_triees:
        return 0.0
    if len(valeurs_triees) == 1:
        return float(valeurs_triees[0])
    rang = (p / 100.0) * (len(valeurs_triees) - 1)
    bas = int(rang)
    haut = min(bas + 1, len(valeurs_triees) - 1)
    frac = rang - bas
    return valeurs_triees[bas] + (valeurs_triees[haut] - valeurs_triees[bas]) * frac


@dataclass
class StatsMarche:
    n: int = 0
    mediane: Optional[int] = None
    minimum: Optional[int] = None
    maximum: Optional[int] = None
    p25: Optional[int] = None
    p75: Optional[int] = None
    prix: list = field(default_factory=list)


def calcul_stats(listings: Iterable, inclure_bricoleur: bool = False) -> StatsMarche:
    """Calcule les statistiques de marché sur les prix finaux retenus."""
    prix = [
        _get(l, "prix_affiche")
        for l in listings
        if raison_exclusion_mediane(l, inclure_bricoleur) is None
    ]
    prix = sorted(p for p in prix if p is not None)
    if not prix:
        return StatsMarche()
    return StatsMarche(
        n=len(prix),
        mediane=int(round(statistics.median(prix))),
        minimum=prix[0],
        maximum=prix[-1],
        p25=int(round(_percentile(prix, 25))),
        p75=int(round(_percentile(prix, 75))),
        prix=prix,
    )


# --------------------------------------------------------------------------- #
# Sélection des comparables
# --------------------------------------------------------------------------- #

# Niveaux de correspondance (0 = meilleur)
NIVEAU_MODELE = 0
NIVEAU_LIGNE = 1
NIVEAU_GABARIT = 2

LIBELLE_NIVEAU = {
    NIVEAU_MODELE: "Même modèle",
    NIVEAU_LIGNE: "Même ligne",
    NIVEAU_GABARIT: "Gabarit similaire",
}


def _niveau_correspondance(listing, modele, ligne, longueur_pi, tolerance_longueur) -> Optional[int]:
    """Détermine à quel niveau de priorité une annonce correspond, ou None."""
    if modele and _norm(_get(listing, "modele")) == _norm(modele):
        return NIVEAU_MODELE
    if ligne and _norm(_get(listing, "ligne")) == _norm(ligne):
        return NIVEAU_LIGNE
    # Gabarit similaire : longueur proche (le type_unite est déjà filtré en amont)
    lp = _get(listing, "longueur_pi")
    if longueur_pi is not None and lp is not None:
        if abs(lp - longueur_pi) <= tolerance_longueur:
            return NIVEAU_GABARIT
    return None


def selectionner_comparables(
    listings: Iterable,
    *,
    type_unite: Optional[str] = None,
    modele: Optional[str] = None,
    ligne: Optional[str] = None,
    annee: Optional[int] = None,
    longueur_pi: Optional[float] = None,
    fenetre_annees: int = 2,
    tolerance_longueur: float = 2.0,
    inclure_bricoleur: bool = False,
    max_resultats: int = 10,
) -> list:
    """Retourne les comparables les plus proches, triés par pertinence.

    Étapes : exclusions totales → filtre type → dédoublonnage → niveau de
    correspondance → tri (niveau, dans/hors fenêtre d'année, écart d'année).
    """
    # 1. Retirer les annonces exclues de toute analyse (volée, notre annonce)
    pool = [l for l in listings if raison_exclusion_totale(l) is None]

    # 2. Filtrer par type d'unité (onglet choisi)
    if type_unite:
        pool = [l for l in pool if _norm(_get(l, "type_unite")) == _norm(type_unite)]

    # 3. Dédoublonner
    pool = dedoublonner(pool)

    # 4. Ne garder que les annonces correspondant à un niveau de priorité
    candidats = []
    for l in pool:
        niveau = _niveau_correspondance(l, modele, ligne, longueur_pi, tolerance_longueur)
        if niveau is None:
            continue
        ecart_annee = abs((_get(l, "annee") or annee or 0) - annee) if annee else 0
        hors_fenetre = 1 if (annee and ecart_annee > fenetre_annees) else 0
        candidats.append((niveau, hors_fenetre, ecart_annee, l))

    # 5. Trier : meilleur niveau, puis dans la fenêtre d'année, puis écart d'année
    candidats.sort(key=lambda t: (t[0], t[1], t[2]))

    return [t[3] for t in candidats[:max_resultats]]


# --------------------------------------------------------------------------- #
# Nuances et phrase de lecture
# --------------------------------------------------------------------------- #

def generer_nuances(comparables: list, annee: Optional[int], inclure_bricoleur: bool = False) -> list:
    """Génère des remarques utiles sur l'échantillon de comparables."""
    nuances: list = []
    retenus = [c for c in comparables if raison_exclusion_mediane(c, inclure_bricoleur) is None]
    if not retenus:
        return nuances

    # Proportion particuliers vs concessionnaires
    n = len(retenus)
    particuliers = sum(1 for c in retenus if _norm(_get(c, "type_vendeur")).startswith("particulier"))
    if particuliers:
        pct = round(100 * particuliers / n)
        nuances.append(
            f"{pct} % des comparables retenus sont des ventes de particulier "
            f"(généralement 10–20 % sous le prix concessionnaire)."
        )

    # Comparables plus vieux/récents que l'année demandée
    if annee:
        annees = [_get(c, "annee") for c in retenus if _get(c, "annee")]
        if annees:
            if all(a > annee for a in annees):
                nuances.append(
                    f"Tous les comparables sont plus récents que {annee} — "
                    "la valeur réelle est probablement un peu plus basse."
                )
            elif all(a < annee for a in annees):
                nuances.append(
                    f"Tous les comparables sont plus vieux que {annee} — "
                    "la valeur réelle est probablement un peu plus haute."
                )

    # Annonces visibles mais exclues des médianes
    exclues = [
        (c, raison_exclusion_mediane(c, inclure_bricoleur))
        for c in comparables
        if raison_exclusion_mediane(c, inclure_bricoleur) is not None
    ]
    if exclues:
        raisons = sorted({r for _, r in exclues})
        nuances.append(
            f"{len(exclues)} annonce(s) affichée(s) mais exclue(s) des calculs "
            f"({', '.join(raisons)})."
        )

    return nuances


def phrase_lecture(stats: StatsMarche) -> str:
    """Phrase en français clair résumant le marché."""
    if stats.n == 0 or stats.mediane is None:
        return "Aucune donnée de prix fiable pour ce modèle."

    def fmt(v):
        return f"{v:,}".replace(",", " ") + " $"

    if stats.n == 1:
        return f"Une seule annonce comparable trouvée, affichée à {fmt(stats.mediane)}."

    return (
        f"Ce modèle se négocie surtout entre {fmt(stats.p25)} et {fmt(stats.p75)}, "
        f"la majorité autour de {fmt(stats.mediane)} "
        f"(fourchette complète {fmt(stats.minimum)}–{fmt(stats.maximum)}, "
        f"sur {stats.n} annonce{'s' if stats.n > 1 else ''} retenue{'s' if stats.n > 1 else ''})."
    )


def evaluer(
    listings: Iterable,
    *,
    type_unite: Optional[str] = None,
    marque: Optional[str] = None,
    ligne: Optional[str] = None,
    modele: Optional[str] = None,
    annee: Optional[int] = None,
    longueur_pi: Optional[float] = None,
    fenetre_annees: int = 2,
    tolerance_longueur: float = 2.0,
    inclure_bricoleur: bool = False,
) -> dict:
    """Point d'entrée : sélectionne les comparables et calcule l'analyse complète.

    Retourne un dictionnaire prêt pour l'affichage. Si aucun comparable fiable,
    `stats.n == 0` et `message` explique la situation (jamais de plantage).
    """
    comparables = selectionner_comparables(
        listings,
        type_unite=type_unite,
        modele=modele,
        ligne=ligne,
        annee=annee,
        longueur_pi=longueur_pi,
        fenetre_annees=fenetre_annees,
        tolerance_longueur=tolerance_longueur,
        inclure_bricoleur=inclure_bricoleur,
        max_resultats=10,
    )
    stats = calcul_stats(comparables, inclure_bricoleur=inclure_bricoleur)
    nuances = generer_nuances(comparables, annee, inclure_bricoleur=inclure_bricoleur)

    message = None
    if not comparables:
        message = (
            "Aucun comparable fiable trouvé pour ce véhicule. "
            "Vérifiez l'orthographe du modèle/de la ligne, ou élargissez la recherche."
        )
    elif stats.n == 0:
        message = (
            "Des annonces existent mais aucune n'a de prix exploitable "
            "(USD, prix sur demande, etc.). Aucune médiane calculable."
        )

    return {
        "comparables": comparables,
        "stats": stats,
        "nuances": nuances,
        "phrase": phrase_lecture(stats),
        "message": message,
        "niveau_libelle": LIBELLE_NIVEAU,
    }
