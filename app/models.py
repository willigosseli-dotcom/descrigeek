from sqlalchemy import Column, Integer, String, Text, DateTime, Boolean, ForeignKey, JSON
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
