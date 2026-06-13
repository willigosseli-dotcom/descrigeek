# DescriGeek — Générateur de descriptions VR

Application web interne pour **VR Thetford**, développée en collaboration avec **Les Geeks du VR**.

---

## Installation et démarrage

### Première fois

1. Assurez-vous d'avoir **Python 3.11 ou plus récent** installé.
   - Vérifiez : ouvrez une invite de commandes et tapez `python --version`
   - Téléchargement : https://www.python.org/downloads/

2. Double-cliquez sur **`lancer.bat`**.
   - L'environnement virtuel et les dépendances sont installés automatiquement.

3. Ouvrez votre navigateur à l'adresse : **http://localhost:8000**

4. Connectez-vous avec :
   - **Nom d'utilisateur :** `admin`
   - **Mot de passe :** `admin123`
   - **Important :** Changez ce mot de passe dès la première connexion (Mes réglages → Changer mon mot de passe).

### Démarrages suivants

Double-cliquez simplement sur **`lancer.bat`**.

---

## Configuration des clés API

Ouvrez le fichier **`.env`** dans un éditeur de texte et remplacez les valeurs :

```
ANTHROPIC_API_KEY=sk-ant-...    ← Votre clé Anthropic (console.anthropic.com)
TAVILY_API_KEY=tvly-...          ← Votre clé Tavily (tavily.com)
DEMO_MODE=false                  ← Mettre false une fois les clés configurées
```

---

## Structure des dossiers importants

```
data/
├── specs/          ← Déposez ici vos fiches de specs (PDF, Excel, CSV)
└── assets/logos/   ← Déposez ici vos logos :
                        vr-thetford.png
                        geeks-du-vr.png

config/
├── settings.json   ← Réglages du concessionnaire et texte de fermeture
└── terminology.json ← Termes techniques français (modifiable dans l'admin)
```

---

## Logos

Déposez vos fichiers logo dans `data/assets/logos/` :
- `vr-thetford.png` — Logo VR Thetford
- `geeks-du-vr.png` — Logo Les Geeks du VR

---

## Comptes utilisateurs

- **Administrateur** : accès complet (gestion des comptes, réglages, exemples modèles, tout l'historique)
- **Utilisateur régulier** : peut générer des descriptions et voir son propre historique

Gestion des comptes : **Administration → Utilisateurs**

---

## Fonctionnalités principales

1. **Générer** une description : menu *Générer*
2. **Historique** des descriptions : menu *Historique* (recherche par numéro de stock)
3. **Exemples modèles** : Administration → Exemples (guide le style de l'IA)
4. **Terminologie** : Administration → Réglages → Terminologie
5. **Réglages personnels** : icône engrenage en haut à droite (taille du texte, couleurs)

---

## Déploiement sur serveur

L'application est prête pour un déploiement sur un serveur Linux avec :
- **Base de données** : remplacer SQLite par PostgreSQL (modifier `DATABASE_URL` dans `.env`)
- **Serveur web** : Nginx + Gunicorn/Uvicorn
- **HTTPS** : Certbot (Let's Encrypt)

Contactez votre équipe technique pour le déploiement.

---

*DescriGeek — VR Thetford × Les Geeks du VR*
