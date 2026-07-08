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


# --------------------------------------------------------------------------- #
# Estimations utilisateur : visibles mais hors médiane, jamais dédoublonnées
# --------------------------------------------------------------------------- #

def test_estimation_utilisateur_visible_hors_mediane():
    listings = [
        _listing(url_annonce="u1", prix_affiche=30000, ville="A"),
        _listing(url_annonce="u2", prix_affiche=32000, ville="B"),
    ]
    est = _listing(url_annonce=None, prix_affiche=50000, ville=None,
                   type_vendeur="Utilisateur", is_estimation_utilisateur=True)
    res = engine.evaluer(listings + [est], type_unite="Roulotte", modele="2205S", annee=2021)

    # exclue de la médiane
    assert engine.raison_exclusion_mediane(est) == "Estimation utilisateur"
    assert res["stats"].n == 2
    assert res["stats"].mediane == 31000
    assert res["stats"].maximum == 32000  # le 50000 de l'estimation n'entre pas
    # mais bien présente dans les comparables affichés
    assert any(getattr(c, "is_estimation_utilisateur", False) for c in res["comparables"])


def test_estimations_jamais_dedoublonnees():
    e1 = _listing(url_annonce=None, prix_affiche=40000, ville=None, is_estimation_utilisateur=True)
    e2 = _listing(url_annonce=None, prix_affiche=40000, ville=None, is_estimation_utilisateur=True)
    assert len(engine.dedoublonner([e1, e2])) == 2


# --------------------------------------------------------------------------- #
# Filtre des prix aberrants
# --------------------------------------------------------------------------- #

def test_filtrer_aberrants_bas_et_haut():
    ls = [_listing(url_annonce=f"u{i}", prix_affiche=p, ville=f"v{i}")
          for i, p in enumerate([20000, 21000, 22000, 23000, 6000, 60000])]
    kept = sorted(l.prix_affiche for l in engine.filtrer_aberrants(ls))
    assert 6000 not in kept and 60000 not in kept
    assert kept == [20000, 21000, 22000, 23000]


def test_filtre_aberrant_pas_applique_si_trop_peu_de_donnees():
    # Moins de 4 prix -> on ne juge pas, rien n'est retiré
    ls = [_listing(url_annonce="u1", prix_affiche=20000, ville="A"),
          _listing(url_annonce="u2", prix_affiche=6000, ville="B")]
    assert len(engine.filtrer_aberrants(ls)) == 2


def test_annonce_aberrante_absente_des_suggestions():
    listings = [
        _listing(url_annonce="u1", prix_affiche=20000, ville="A"),
        _listing(url_annonce="u2", prix_affiche=21000, ville="B"),
        _listing(url_annonce="u3", prix_affiche=22000, ville="C"),
        _listing(url_annonce="u4", prix_affiche=23000, ville="D"),
        _listing(url_annonce="u5", prix_affiche=6000, ville="E"),  # marketplace aberrant
    ]
    res = engine.evaluer(listings, type_unite="Roulotte", modele="2205S", annee=2021)
    prix = [c.prix_affiche for c in res["comparables"]]
    assert 6000 not in prix
    assert res["stats"].minimum >= 20000


def test_estimation_utilisateur_jamais_ecartee_comme_aberrante():
    # Beaucoup d'annonces ~20 000 $, plus une estimation utilisateur volontairement basse
    listings = [_listing(url_annonce=f"u{i}", prix_affiche=p, ville=f"v{i}")
                for i, p in enumerate([20000, 21000, 22000, 23000])]
    est = _listing(url_annonce=None, prix_affiche=6000, ville=None,
                   type_vendeur="Utilisateur", is_estimation_utilisateur=True)
    res = engine.evaluer(listings + [est], type_unite="Roulotte", modele="2205S", annee=2021)
    assert any(getattr(c, "is_estimation_utilisateur", False) for c in res["comparables"])


# --------------------------------------------------------------------------- #
# Restriction par année (filtre STRICT)
# --------------------------------------------------------------------------- #

def test_annee_hors_fenetre_exclue():
    # Demande 2015 : un 2024 ne doit JAMAIS apparaître (fenêtre ±2 → 2013–2017)
    listings = [
        _listing(url_annonce="u1", annee=2015, prix_affiche=20000, ville="A"),
        _listing(url_annonce="u2", annee=2016, prix_affiche=21000, ville="B"),
        _listing(url_annonce="u3", annee=2024, prix_affiche=40000, ville="C"),  # trop récent
    ]
    res = engine.evaluer(listings, type_unite="Roulotte", modele="2205S",
                         annee=2015, fenetre_annees=2)
    annees = [c.annee for c in res["comparables"]]
    assert 2024 not in annees
    assert set(annees) == {2015, 2016}


def test_fenetre_annees_configurable():
    listings = [
        _listing(url_annonce="u1", annee=2015, ville="A"),
        _listing(url_annonce="u2", annee=2020, ville="B"),
    ]
    # fenêtre ±1 → seul 2015 ; fenêtre ±6 → les deux
    r1 = engine.evaluer(listings, type_unite="Roulotte", modele="2205S", annee=2015, fenetre_annees=1)
    assert {c.annee for c in r1["comparables"]} == {2015}
    r6 = engine.evaluer(listings, type_unite="Roulotte", modele="2205S", annee=2015, fenetre_annees=6)
    assert {c.annee for c in r6["comparables"]} == {2015, 2020}


# --------------------------------------------------------------------------- #
# Équivalents d'autres marques (gabarit similaire par longueur)
# --------------------------------------------------------------------------- #

def test_longueur_deduite_du_modele():
    # Aucune longueur saisie : elle est déduite des annonces du même modèle (22 pi)
    listings = [
        _listing(url_annonce="u1", modele="2205S", longueur_pi=22.0, ville="A"),
        _listing(url_annonce="u2", modele="2205S", longueur_pi=22.0, ville="B"),
    ]
    lg = engine.longueur_cible(listings, type_unite="Roulotte", modele="2205S")
    assert lg == 22.0


def test_equivalents_autres_marques_par_gabarit():
    listings = [
        # modèle exact demandé (Forest River), 22 pi
        _listing(url_annonce="u1", marque="Forest River", modele="2205S",
                 longueur_pi=22.0, prix_affiche=32000, annee=2021, ville="A"),
        # autre marque, autre modèle, MÊME gabarit (~22 pi) → doit être inclus
        _listing(url_annonce="u2", marque="Jayco", ligne="Jay Feather", modele="22RB",
                 longueur_pi=22.5, prix_affiche=31000, annee=2021, ville="B"),
        # autre marque mais gabarit très différent (30 pi) → exclu
        _listing(url_annonce="u3", marque="Grand Design", ligne="Imagine", modele="3100RD",
                 longueur_pi=30.0, prix_affiche=45000, annee=2021, ville="C"),
    ]
    res = engine.evaluer(listings, type_unite="Roulotte", modele="2205S",
                         ligne="Rockwood Mini Lite", annee=2021, tolerance_longueur=2.0)
    urls = {c.url_annonce for c in res["comparables"]}
    assert "u1" in urls          # modèle exact
    assert "u2" in urls          # équivalent d'une autre marque
    assert "u3" not in urls      # gabarit trop différent
