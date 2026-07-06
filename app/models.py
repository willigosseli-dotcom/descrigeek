from sqlalchemy import Column, Integer, String, Text, DateTime, Date, Boolean, Float, ForeignKey, JSON
from sqlalchemy.orm import declarative_base, relationship
from datetime import datetime

Base = declarative_base()


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(50), unique=True, nullable=False, index=True)
    email = Column(String(100), unique=True, nullable=True)
    hashed_password = Column(String(255), nullable=False)
    full_name = Column(String(100), nullable=True)
    role = Column(String(20), default="user")  # "admin" or "user"
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    # Préférences d'affichage
    text_size = Column(String(20), default="normal")  # tiny, normal, large, xlarge
    color_theme = Column(String(20), default="vr-thetford")
    custom_accent_color = Column(String(7), nullable=True)  # ex: #1B9DE0

    descriptions = relationship("Description", back_populates="user")


class Description(Base):
    __tablename__ = "descriptions"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    stock_number = Column(String(50), nullable=False, index=True)

    # Identité du véhicule
    vehicle_year = Column(Integer, nullable=True)
    vehicle_make = Column(String(100), nullable=True)
    vehicle_model = Column(String(100), nullable=True)
    vehicle_type = Column(String(50), nullable=True)

    # Données saisies par l'utilisateur
    options_accessories = Column(Text, nullable=True)
    unique_features = Column(Text, nullable=True)
    adjustment_note = Column(Text, nullable=True)

    # Résultat généré
    generated_description = Column(Text, nullable=True)
    target_audience = Column(Text, nullable=True)
    specs_used = Column(JSON, nullable=True)
    specs_source = Column(String(500), nullable=True)
    specs_warnings = Column(JSON, nullable=True)

    # Statut
    status = Column(String(20), default="draft")  # draft, approved, published

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    user = relationship("User", back_populates="descriptions")


class SpecsCache(Base):
    __tablename__ = "specs_cache"

    id = Column(Integer, primary_key=True, index=True)
    vehicle_year = Column(Integer, nullable=False)
    vehicle_make = Column(String(100), nullable=False)
    vehicle_model = Column(String(100), nullable=False)
    vehicle_type = Column(String(50), nullable=True)
    specs_data = Column(JSON, nullable=False)
    source_url = Column(String(500), nullable=True)
    source_name = Column(String(200), nullable=True)
    source_type = Column(String(20), default="web")  # "web", "file"
    cached_at = Column(DateTime, default=datetime.utcnow)
    is_manual = Column(Boolean, default=False)


class DescriptionExample(Base):
    __tablename__ = "description_examples"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String(200), nullable=False)
    vehicle_type = Column(String(50), nullable=True)
    content = Column(Text, nullable=False)
    notes = Column(Text, nullable=True)
    created_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)


# =====================================================================
# ÉVALUATION DE PRIX DE VR USAGÉS
# =====================================================================

class Listing(Base):
    """Une annonce de VR usagé importée depuis le CSV maître.

    Clé stable d'un import à l'autre : url_annonce (unique).
    """
    __tablename__ = "listings"

    id = Column(Integer, primary_key=True, index=True)
    url_annonce = Column(String(1000), unique=True, nullable=False, index=True)

    # --- Champs bruts du CSV (19 colonnes) ---
    type_unite = Column(String(50), nullable=True, index=True)
    marque = Column(String(120), nullable=True)
    ligne = Column(String(160), nullable=True)
    modele = Column(String(160), nullable=True, index=True)
    annee = Column(Integer, nullable=True, index=True)
    prix_affiche = Column(Integer, nullable=True)   # prix FINAL nettoyé, en CAD
    vendeur = Column(String(200), nullable=True)
    type_vendeur = Column(String(60), nullable=True)
    localisation = Column(String(200), nullable=True)
    longueur_pi = Column(Float, nullable=True)
    kilometrage = Column(Integer, nullable=True)
    etat_declare = Column(String(120), nullable=True)
    extensions = Column(String(120), nullable=True)
    date_collecte = Column(Date, nullable=True)
    date_derniere_observation = Column(Date, nullable=True)
    statut = Column(String(60), nullable=True)
    ancien_prix = Column(Integer, nullable=True)    # prix barré du CSV (informatif)
    notes = Column(Text, nullable=True)

    # --- Champs normalisés / calculés à l'import ---
    ville = Column(String(160), nullable=True)      # extrait de « Ville, QC »

    is_usd = Column(Boolean, default=False)
    is_prix_sur_demande = Column(Boolean, default=False)
    is_volee = Column(Boolean, default=False)
    is_projet_bricoleur = Column(Boolean, default=False)
    is_doublon = Column(Boolean, default=False)
    is_notre_annonce = Column(Boolean, default=False)

    # --- Suivi inter-imports ---
    premier_import_le = Column(DateTime, default=datetime.utcnow)
    dernier_import_le = Column(DateTime, default=datetime.utcnow)
    disparue = Column(Boolean, default=False, index=True)
    prix_precedent = Column(Integer, nullable=True)  # pour détecter les baisses


class ImportBatch(Base):
    """Historique des imports de CSV (résumé de chaque import)."""
    __tablename__ = "import_batches"

    id = Column(Integer, primary_key=True, index=True)
    imported_at = Column(DateTime, default=datetime.utcnow)
    imported_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    nom_fichier = Column(String(255), nullable=True)
    nb_lignes_csv = Column(Integer, default=0)
    nb_importees = Column(Integer, default=0)     # créées + mises à jour
    nb_creees = Column(Integer, default=0)
    nb_maj = Column(Integer, default=0)
    nb_disparues = Column(Integer, default=0)
    nb_baisses = Column(Integer, default=0)
    details = Column(JSON, nullable=True)         # ex. listes d'exemples de baisses


class EvalSetting(Base):
    """Réglages du moteur d'évaluation (une seule ligne, id=1)."""
    __tablename__ = "eval_settings"

    id = Column(Integer, primary_key=True)
    fenetre_annees = Column(Integer, default=2)
    inclure_projets_bricoleur = Column(Boolean, default=False)
    decote_bricoleur_pct = Column(Integer, default=40)
    ponderation_particulier_pct = Column(Integer, default=15)
    tolerance_longueur_pi = Column(Float, default=2.0)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
