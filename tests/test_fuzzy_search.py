"""Tests de la recherche floue (normalisation + classement rapidfuzz)."""
from app.services import fuzzy_search as fs

COMBOS = [
    {"marque": "Jayco", "ligne": "Eagle", "modele": "26.5RLDS"},
    {"marque": "Keystone", "ligne": "Passport", "modele": "268BH"},
    {"marque": "Forest River", "ligne": "Rockwood Mini Lite", "modele": "2205S"},
    {"marque": "Jayco", "ligne": "Jay Feather", "modele": "22RB"},
]


def test_normaliser():
    assert fs.normaliser("  Forêt-Verte  ") == "foret verte"
    assert fs.normaliser("Jayco   Eagle") == "jayco eagle"
    assert fs.normaliser(None) == ""


def test_acceptation_jaco_eagl():
    res = fs.classer("jaco eagl", COMBOS, limit=1)
    assert res and res[0][1]["marque"] == "Jayco" and res[0][1]["ligne"] == "Eagle"


def test_acceptation_passeport_268():
    res = fs.classer("passeport 268", COMBOS, limit=1)
    assert res and res[0][1]["ligne"] == "Passport"


def test_requete_hors_sujet_ne_matche_pas():
    assert fs.classer("zzzz qqqq wwww", COMBOS) == []


def test_requete_vide():
    assert fs.classer("", COMBOS) == []
