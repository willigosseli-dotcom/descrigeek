"""Tests unitaires du moteur de comparables (aucune base de données requise)."""
from types import SimpleNamespace

from app.services import comparables_engine as engine


def _listing(**kwargs):
    """Crée une annonce factice avec des valeurs par défaut sûres."""
    base = dict(
        type_unite="Roulotte", marque="Forest River", ligne="Rockwood Mini Lite",
        modele="2205S", annee=2021, prix_affiche=32000, type_vendeur="Concessionnaire",
        ville="Québec", localisation="Québec, QC", longueur_pi=22.0,
        is_usd=False, is_prix_sur_demande=False, is_volee=False,
        is_projet_bricoleur=False, is_doublon=False, is_notre_annonce=False,
    )
    base.update(kwargs)
    return SimpleNamespace(**base)


# --------------------------------------------------------------------------- #
# Critère #2 : exclusions des médianes
# --------------------------------------------------------------------------- #

def test_annonce_volee_exclue_de_tout():
    l = _listing(is_volee=True)
    assert engine.raison_exclusion_totale(l) == "Annonce volée"
    assert engine.raison_exclusion_mediane(l) == "Annonce volée"


def test_notre_annonce_exclue_de_tout():
    l = _listing(is_notre_annonce=True)
    assert engine.raison_exclusion_totale(l) is not None


def test_prix_usd_exclu_de_mediane():
    assert engine.raison_exclusion_mediane(_listing(is_usd=True)) == "Prix en USD"


def test_prix_sur_demande_exclu_de_mediane():
    assert engine.raison_exclusion_mediane(_listing(prix_affiche=None)) is not None
    assert engine.raison_exclusion_mediane(_listing(is_prix_sur_demande=True)) is not None


def test_projet_bricoleur_exclu_par_defaut_mais_inclus_sur_option():
    l = _listing(is_projet_bricoleur=True)
    assert engine.raison_exclusion_mediane(l, inclure_bricoleur=False) == "Projet bricoleur"
    assert engine.raison_exclusion_mediane(l, inclure_bricoleur=True) is None


def test_stats_ignorent_les_cas_limites():
    listings = [
        _listing(prix_affiche=30000),
        _listing(prix_affiche=32000),
        _listing(prix_affiche=34000),
        _listing(prix_affiche=99999, is_volee=True),       # exclue
        _listing(prix_affiche=88888, is_usd=True),          # exclue
        _listing(prix_affiche=None, is_prix_sur_demande=True),  # exclue
        _listing(prix_affiche=5000, is_projet_bricoleur=True),  # exclue par défaut
    ]
    stats = engine.calcul_stats(listings)
    assert stats.n == 3
    assert stats.mediane == 32000
    assert stats.minimum == 30000
    assert stats.maximum == 34000


# --------------------------------------------------------------------------- #
# Critère #3 : dédoublonnage
# --------------------------------------------------------------------------- #

def test_doublon_compte_une_seule_fois():
    l1 = _listing(url_annonce="u1")
    l2 = _listing(url_annonce="u2")  # même modele+annee+prix+ville
    assert len(engine.dedoublonner([l1, l2])) == 1

    # via le pipeline complet (evaluer), le doublon n'est compté qu'une fois
    res = engine.evaluer([l1, l2], type_unite="Roulotte", modele="2205S", annee=2021)
    assert res["stats"].n == 1
    assert len(res["comparables"]) == 1


def test_doublon_explicite_par_drapeau():
    l1 = _listing(url_annonce="u1")
    l2 = _listing(url_annonce="u2", is_doublon=True)
    assert len(engine.dedoublonner([l1, l2])) == 1


# --------------------------------------------------------------------------- #
# Critère #4 : recherche par modèle exact
# --------------------------------------------------------------------------- #

def test_selection_par_modele_exact_et_tri():
    listings = [
        _listing(url_annonce=f"u{i}", modele="2205S", annee=2021, prix_affiche=30000 + i * 500,
                 ville=f"Ville{i}")
        for i in range(6)
    ]
    # une annonce d'un autre modèle mais même ligne → niveau inférieur
    listings.append(_listing(url_annonce="autre", modele="9999X", ligne="Rockwood Mini Lite",
                             annee=2021, prix_affiche=40000, ville="Ailleurs"))
    res = engine.evaluer(listings, type_unite="Roulotte", modele="2205S", ligne="Rockwood Mini Lite",
                         annee=2021)
    assert res["stats"].n >= 5
    assert 5 <= len(res["comparables"]) <= 10
    # le premier comparable doit être une correspondance « même modèle »
    premier = res["comparables"][0]
    assert engine._niveau_correspondance(premier, "2205S", "Rockwood Mini Lite", None, 2.0) == engine.NIVEAU_MODELE


def test_repli_sur_ligne_puis_gabarit():
    # aucun même modèle, mais même ligne
    listings = [
        _listing(url_annonce="u1", modele="1111A", ligne="Rockwood Mini Lite", ville="A"),
        _listing(url_annonce="u2", modele="2222B", ligne="Rockwood Mini Lite", ville="B"),
    ]
    res = engine.evaluer(listings, type_unite="Roulotte", modele="2205S",
                         ligne="Rockwood Mini Lite", annee=2021)
    assert len(res["comparables"]) == 2


# --------------------------------------------------------------------------- #
# Critère #5 : aucun comparable fiable → message, pas de plantage
# --------------------------------------------------------------------------- #

def test_aucun_comparable():
    res = engine.evaluer([], type_unite="Roulotte", modele="INEXISTANT", annee=2021)
    assert res["comparables"] == []
    assert res["stats"].n == 0
    assert res["message"] is not None


def test_comparables_sans_prix_exploitable():
    listings = [
        _listing(url_annonce="u1", is_usd=True),
        _listing(url_annonce="u2", prix_affiche=None, is_prix_sur_demande=True, ville="X"),
    ]
    res = engine.evaluer(listings, type_unite="Roulotte", modele="2205S", annee=2021)
    assert res["stats"].n == 0
    assert res["message"] is not None
    # les annonces restent visibles comme comparables
    assert len(res["comparables"]) >= 1


def test_filtre_par_type_unite():
    listings = [
        _listing(url_annonce="u1", type_unite="Roulotte", ville="A"),
        _listing(url_annonce="u2", type_unite="Fifth wheel", modele="2205S", ville="B"),
    ]
    res = engine.evaluer(listings, type_unite="Roulotte", modele="2205S", annee=2021)
    assert all(c.type_unite == "Roulotte" for c in res["comparables"])
