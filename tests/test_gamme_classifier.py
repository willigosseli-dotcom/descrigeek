"""Tests du classement de gamme (heuristique de repli, sans IA ni base)."""
from app.services import gamme_classifier as gc


def test_heuristique_marques_connues():
    assert gc._classer_heuristique("Forest River", "Rockwood Mini Lite")["gamme"] == "haut"
    assert gc._classer_heuristique("Forest River", "Salem")["gamme"] == "entrée"
    assert gc._classer_heuristique("Jayco", "Jay Feather")["gamme"] == "milieu"


def test_heuristique_marque_inconnue():
    res = gc._classer_heuristique("MarqueInconnue", "LigneX")
    assert res["gamme"] is None
    assert res["source"] == "démo"


def test_cle_normalise_accents_et_casse():
    assert gc.cle("Forest River", "Rockwood") == gc.cle("forest river ", " ROCKWOOD")
