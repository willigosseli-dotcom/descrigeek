"""Tests d'import CSV : parsing, upsert, détection des disparitions et des baisses."""
from pathlib import Path

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from sqlalchemy.pool import StaticPool

from sqlalchemy import select, func

from app.models import Base, Listing, StockNeuf
from app.services import csv_import

CSV_PATH = Path(__file__).parent / "test_data_cas_limites.csv"
CONTENU = CSV_PATH.read_text(encoding="utf-8")


@pytest_asyncio.fixture
async def session():
    engine = create_async_engine(
        "sqlite+aiosqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    Maker = async_sessionmaker(engine, expire_on_commit=False)
    async with Maker() as s:
        yield s
    await engine.dispose()


# --------------------------------------------------------------------------- #
# Critère #1 : le CSV s'importe sans erreur, le nombre de lignes correspond
# --------------------------------------------------------------------------- #

def test_parsing_nombre_de_lignes():
    lignes = csv_import.parser_csv(CONTENU)
    assert len(lignes) == 13


def test_parsing_nettoyage_valeurs():
    lignes = {l["url_annonce"]: l for l in csv_import.parser_csv(CONTENU)}
    # prix avec espace « 34 900 » → 34900
    assert lignes["https://exemple.ca/a/3"]["prix_affiche"] == 34900
    # prix quoté « 82,900 » → 82900
    assert lignes["https://exemple.ca/a/13"]["prix_affiche"] == 82900
    # N/D → None
    assert lignes["https://exemple.ca/a/5"]["prix_affiche"] is None
    # localisation quotée avec virgule → ville extraite
    assert lignes["https://exemple.ca/a/1"]["ville"] == "Québec"
    # prix barré : prix final retenu (31900), ancien_prix conservé (35900)
    assert lignes["https://exemple.ca/a/10"]["prix_affiche"] == 31900
    assert lignes["https://exemple.ca/a/10"]["ancien_prix"] == 35900


def test_parsing_drapeaux_cas_limites():
    lignes = {l["url_annonce"]: l for l in csv_import.parser_csv(CONTENU)}
    assert lignes["https://exemple.ca/a/4"]["is_usd"] is True
    assert lignes["https://exemple.ca/a/5"]["is_prix_sur_demande"] is True
    assert lignes["https://exemple.ca/a/6"]["is_volee"] is True
    assert lignes["https://exemple.ca/a/7"]["is_projet_bricoleur"] is True
    assert lignes["https://exemple.ca/a/8"]["is_doublon"] is True
    assert lignes["https://facebook.com/marketplace/item/999"]["is_notre_annonce"] is True


def test_entete_invalide_leve_erreur():
    with pytest.raises(csv_import.ImportError_):
        csv_import.parser_csv("colonne1,colonne2\nx,y")


@pytest.mark.asyncio
async def test_import_en_base(session):
    resume = await csv_import.importer_csv(session, CONTENU, nom_fichier="test.csv")
    assert resume["nb_lignes_csv"] == 13
    assert resume["nb_creees"] == 13
    assert resume["nb_disparues"] == 0
    assert resume["nb_baisses"] == 0


@pytest.mark.asyncio
async def test_stock_neuf_separe_des_usages(session):
    # Import usagés -> table Listing
    await csv_import.importer_csv(session, CONTENU)
    # Import stock neuf -> table StockNeuf (jeu séparé)
    header = CONTENU.splitlines()[0]
    row = ('Roulotte,Jayco,Eagle,26.5RLDS,2026,68900,VR X,Concessionnaire,"Sherbrooke, QC",'
           '30,N/D,Neuf,3,https://neuf/1,2026-07-01,2026-07-08,active,N/D,')
    await csv_import.importer_csv(session, header + "\n" + row, model=StockNeuf, creer_batch=False)

    n_listing = (await session.execute(select(func.count()).select_from(Listing))).scalar()
    n_neuf = (await session.execute(select(func.count()).select_from(StockNeuf))).scalar()
    assert n_neuf == 1          # le neuf est bien à part
    assert n_listing == 13      # les usagés ne sont pas touchés


# --------------------------------------------------------------------------- #
# Critère #7 : 2e import → disparitions marquées + baisse détectée
# --------------------------------------------------------------------------- #

@pytest.mark.asyncio
async def test_second_import_disparitions_et_baisses(session):
    # 1er import
    await csv_import.importer_csv(session, CONTENU, nom_fichier="import1.csv")

    # Construire un 2e CSV : retirer l'annonce a/2 (disparue) et baisser le prix de a/1
    lignes = CONTENU.splitlines()
    entete = lignes[0]
    corps = []
    for ligne in lignes[1:]:
        if "https://exemple.ca/a/2" in ligne:
            continue  # annonce disparue
        if ligne.startswith("Roulotte,Forest River,Rockwood Mini Lite,2205S,2021,32900,VR Québec,Concessionnaire,\"Québec, QC\""):
            ligne = ligne.replace(",32900,", ",30900,")  # baisse de prix
        corps.append(ligne)
    contenu2 = "\n".join([entete] + corps)

    resume2 = await csv_import.importer_csv(session, contenu2, nom_fichier="import2.csv")

    assert resume2["nb_disparues"] >= 1
    assert resume2["nb_baisses"] >= 1
    # la baisse détectée passe bien de 32900 à 30900
    baisse = next(b for b in resume2["baisses"] if b["url"] == "https://exemple.ca/a/1")
    assert baisse["avant"] == 32900
    assert baisse["apres"] == 30900
