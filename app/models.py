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

    avatar_url = Column(String(500), nullable=True)

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


class StockNeuf(Base):
    """Stock NEUF chez les compétiteurs (pour l'outil de mise en vente).

    Même structure que Listing (usagés) mais jeu de données séparé : l'évaluation
    utilise les usagés, la mise en vente utilise ce stock neuf. Clé stable : url_annonce.
    """
    __tablename__ = "stock_neuf"

    id = Column(Integer, primary_key=True, index=True)
    url_annonce = Column(String(1000), unique=True, nullable=False, index=True)

    type_unite = Column(String(50), nullable=True, index=True)
    marque = Column(String(120), nullable=True)
    ligne = Column(String(160), nullable=True)
    modele = Column(String(160), nullable=True, index=True)
    annee = Column(Integer, nullable=True, index=True)
    prix_affiche = Column(Integer, nullable=True)
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
    ancien_prix = Column(Integer, nullable=True)
    notes = Column(Text, nullable=True)

    ville = Column(String(160), nullable=True)

    is_usd = Column(Boolean, default=False)
    is_prix_sur_demande = Column(Boolean, default=False)
    is_volee = Column(Boolean, default=False)
    is_projet_bricoleur = Column(Boolean, default=False)
    is_doublon = Column(Boolean, default=False)
    is_notre_annonce = Column(Boolean, default=False)

    premier_import_le = Column(DateTime, default=datetime.utcnow)
    dernier_import_le = Column(DateTime, default=datetime.utcnow)
    disparue = Column(Boolean, default=False, index=True)
    prix_precedent = Column(Integer, nullable=True)


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


class UserEstimation(Base):
    """Estimation de valeur marchande saisie manuellement par un utilisateur.

    Sert de comparable « Utilisateur » lors des évaluations futures (même modèle
    ou modèle similaire). Trace qui l'a entrée, quand. N'entre PAS dans la médiane.
    """
    __tablename__ = "user_estimations"

    id = Column(Integer, primary_key=True, index=True)

    # Identité du véhicule évalué
    type_unite = Column(String(50), nullable=True, index=True)
    marque = Column(String(120), nullable=True)
    ligne = Column(String(160), nullable=True)
    modele = Column(String(160), nullable=True, index=True)
    annee = Column(Integer, nullable=True, index=True)
    longueur_pi = Column(Float, nullable=True)   # déduite au moment de l'évaluation

    valeur_estimee = Column(Integer, nullable=False)   # estimation en CAD
    note = Column(Text, nullable=True)

    # Traçabilité
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    auteur = Column(String(120), nullable=True)   # nom affiché figé au moment de la saisie
    created_at = Column(DateTime, default=datetime.utcnow)


class AppConfig(Base):
    """Configuration globale de l'app (une seule ligne, id=1).

    Contient le mot de passe général partagé (haché) exigé à la connexion et à
    l'inscription, modifiable par un admin et changé « de temps en temps ».
    """
    __tablename__ = "app_config"

    id = Column(Integer, primary_key=True)
    general_password_hash = Column(String(255), nullable=True)
    general_password_updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class EvaluationLog(Base):
    """Journal des évaluations effectuées (historique persistant des unités évaluées)."""
    __tablename__ = "evaluation_logs"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    auteur = Column(String(120), nullable=True)

    type_unite = Column(String(50), nullable=True)
    marque = Column(String(120), nullable=True)
    ligne = Column(String(160), nullable=True)
    modele = Column(String(160), nullable=True)
    annee = Column(Integer, nullable=True)
    gamme = Column(String(20), nullable=True)

    prix_median = Column(Integer, nullable=True)
    nb_comparables = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.utcnow, index=True)


class GammeModele(Base):
    """Gamme de qualité de fabrication d'un modèle (au niveau marque + ligne).

    Classée automatiquement (IA/web) puis corrigeable à la main. Sert à ne comparer
    qu'entre gammes équivalentes (une roulotte fibre/Azdel n'est pas comparée à une
    entrée de gamme OSB/aluminium).
    """
    __tablename__ = "gammes_modeles"

    id = Column(Integer, primary_key=True, index=True)
    type_unite = Column(String(50), nullable=True)
    marque = Column(String(120), nullable=False, index=True)
    ligne = Column(String(160), nullable=True, index=True)

    gamme = Column(String(20), nullable=True)   # "entrée", "milieu", "haut"
    murs = Column(String(120), nullable=True)       # ex. "fibre de verre", "aluminium"
    substrat = Column(String(120), nullable=True)   # ex. "Azdel", "bois / Luan"
    plancher = Column(String(120), nullable=True)   # ex. "contreplaqué", "OSB"
    justification = Column(Text, nullable=True)

    source = Column(String(20), default="IA")   # "IA", "démo", "manuel"
    is_manuel = Column(Boolean, default=False)  # override manuel -> ne pas réécraser
    cached_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


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


# =====================================================================
# ÉVALUATION DE PRIX — VTT & CÔTE-À-CÔTE
# =====================================================================

class VttListing(Base):
    """Annonce de VTT/côte-à-côte usagé importée depuis CSV."""
    __tablename__ = "vtt_listings"

    id = Column(Integer, primary_key=True, index=True)
    url_annonce = Column(String(1000), unique=True, nullable=False, index=True)

    type_unite = Column(String(50), nullable=True, index=True)   # VTT, Côte-à-côte, Motoneige
    marque = Column(String(120), nullable=True)
    gamme = Column(String(160), nullable=True)                    # ex. Ranger, RZR
    modele = Column(String(160), nullable=True, index=True)
    annee = Column(Integer, nullable=True, index=True)
    cylindree_cc = Column(Integer, nullable=True)                 # ex. 700
    prix_affiche = Column(Integer, nullable=True)
    kilometrage = Column(Integer, nullable=True)
    heures = Column(Integer, nullable=True)
    vendeur = Column(String(200), nullable=True)
    type_vendeur = Column(String(60), nullable=True)
    localisation = Column(String(200), nullable=True)
    ville = Column(String(160), nullable=True)
    etat_declare = Column(String(120), nullable=True)
    statut = Column(String(60), nullable=True)
    notes = Column(Text, nullable=True)
    date_collecte = Column(Date, nullable=True)
    date_derniere_observation = Column(Date, nullable=True)

    is_usd = Column(Boolean, default=False)
    is_prix_sur_demande = Column(Boolean, default=False)
    is_volee = Column(Boolean, default=False)
    is_notre_annonce = Column(Boolean, default=False)
    is_doublon = Column(Boolean, default=False)

    premier_import_le = Column(DateTime, default=datetime.utcnow)
    dernier_import_le = Column(DateTime, default=datetime.utcnow)
    disparue = Column(Boolean, default=False, index=True)
    prix_precedent = Column(Integer, nullable=True)


class VttImportBatch(Base):
    """Historique des imports CSV VTT."""
    __tablename__ = "vtt_import_batches"

    id = Column(Integer, primary_key=True, index=True)
    imported_at = Column(DateTime, default=datetime.utcnow)
    imported_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    nom_fichier = Column(String(255), nullable=True)
    nb_lignes_csv = Column(Integer, default=0)
    nb_importees = Column(Integer, default=0)
    nb_creees = Column(Integer, default=0)
    nb_maj = Column(Integer, default=0)
    details = Column(JSON, nullable=True)


class VttUserEstimation(Base):
    """Estimation manuelle d'un VTT par un utilisateur."""
    __tablename__ = "vtt_user_estimations"

    id = Column(Integer, primary_key=True, index=True)
    type_unite = Column(String(50), nullable=True, index=True)
    marque = Column(String(120), nullable=True)
    gamme = Column(String(160), nullable=True)
    modele = Column(String(160), nullable=True, index=True)
    annee = Column(Integer, nullable=True, index=True)
    cylindree_cc = Column(Integer, nullable=True)
    valeur_estimee = Column(Integer, nullable=False)
    note = Column(Text, nullable=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    auteur = Column(String(120), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)


class VttEvaluationLog(Base):
    """Historique des évaluations VTT."""
    __tablename__ = "vtt_evaluation_logs"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    auteur = Column(String(120), nullable=True)
    type_unite = Column(String(50), nullable=True)
    marque = Column(String(120), nullable=True)
    modele = Column(String(160), nullable=True)
    annee = Column(Integer, nullable=True)
    cylindree_cc = Column(Integer, nullable=True)
    prix_median = Column(Integer, nullable=True)
    nb_comparables = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.utcnow, index=True)
