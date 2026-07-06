# Évaluation de prix de VR usagés — guide d'utilisation

Ce module s'ajoute à l'application **DescriGeek** existante. Il permet d'estimer
la valeur de marché d'un VR usagé au Québec à partir de **votre propre base
d'annonces** (un CSV que vous importez et réutilisez à chaque collecte).

---

## Pourquoi cette approche (et pas un projet séparé Next.js/Vercel)

Le module a été **intégré à DescriGeek** plutôt que construit comme une seconde
application indépendante. Concrètement, cela veut dire :

- **Une seule application à administrer**, une seule adresse web, un seul mot de
  passe. Rien de nouveau à installer ou à maintenir.
- **La même base de données Supabase** (PostgreSQL) déjà en place — aucun compte
  ni service supplémentaire à créer.
- **Le même déploiement Railway** déjà branché sur GitHub : quand le code est
  poussé, tout se met à jour automatiquement.
- **La même connexion sécurisée** : aucune page n'est accessible sans être
  connecté (l'authentification de DescriGeek est réutilisée telle quelle).

C'est plus simple, moins cher, et il n'y a qu'un seul endroit où se connecter.

---

## Les trois écrans

Dans le menu de gauche, section **« Évaluation de prix »** :

### 1. Évaluer un véhicule
- Choisissez le **type** en haut (Roulotte, Fifth wheel, Tente-roulotte).
  *VTT* et *Côte à côte* sont visibles mais grisés — ils seront activés plus tard.
- Remplissez **Marque, Ligne (gamme), Modèle, Année**.
- Cliquez le gros bouton rouge **ÉVALUER**.

Vous obtenez :
- **L'analyse de marché** : prix médian, fourchette min–max, zone P25–P75,
  nombre d'annonces retenues, et une phrase de lecture en français clair.
- **Les comparables** : 5 à 10 annonces les plus proches, avec marque/ligne/modèle,
  année, prix, type de vendeur, ville, et un **lien cliquable vers l'annonce**.

### 2. Importer données *(réservé aux administrateurs)*
- **Glissez votre CSV maître** dans la zone prévue (ou cliquez pour le choisir).
- L'application affiche un résumé : nombre d'annonces importées, **annonces
  disparues** depuis le dernier import, et **baisses de prix détectées**.
- C'est **la seule façon de faire entrer des données** : l'application ne lit
  aucun fichier sur votre ordinateur, tout passe par cet import.

Vous pouvez réimporter aussi souvent que vous refaites votre collecte. Les
annonces sont suivies par leur **adresse web (`url_annonce`)** d'un import à
l'autre — c'est ainsi que l'app repère les disparitions et les baisses de prix.

### 3. Réglages évaluation *(réservé aux administrateurs)*
Réglés **une seule fois**, puis oubliés :
- **Fenêtre d'années** (± combien d'années pour les comparables, défaut 2)
- **Tolérance de longueur** (pour le repli « gabarit similaire »)
- **Pondération particulier vs concession** (informatif, affiché dans les nuances)
- **Décote « projet bricoleur »** et **inclusion ou non des projets bricoleur**

---

## Le fichier CSV attendu

- **Format** : virgule comme séparateur, encodage **UTF-8**, en-tête sur la 1re ligne.
- **19 colonnes, dans cet ordre exact** :

```
type_unite,marque,ligne,modele,annee,prix_affiche,vendeur,type_vendeur,
localisation,longueur_pi,kilometrage,etat_declare,extensions,url_annonce,
date_collecte,date_derniere_observation,statut,ancien_prix,notes
```

- Les valeurs inconnues s'écrivent **`N/D`** (elles deviennent « vide » à l'import).
- Les prix peuvent contenir des espaces ou séparateurs (`34 900`, `"82,900"`) —
  ils sont nettoyés automatiquement en nombre entier.
- La **localisation** contient une virgule (`Ville, QC`) : elle doit être entre
  **guillemets** dans le CSV, par exemple `"Québec, QC"`.
- Le **prix retenu est toujours le prix final** (`prix_affiche`), jamais le prix
  barré (`ancien_prix`).

Un exemple complet couvrant tous les cas particuliers se trouve dans
[`tests/test_data_cas_limites.csv`](tests/test_data_cas_limites.csv).

### Cas particuliers gérés automatiquement (via la colonne `notes`)

| Situation | Écrire dans `notes` | Effet |
|---|---|---|
| Prix en dollars américains | `Prix en USD` | Exclu des médianes, mais l'annonce reste visible (badge) |
| Prix sur demande / manquant | `Prix sur demande` (ou `prix_affiche` = `N/D`) | Exclu des médianes, reste visible |
| Annonce volée | `... VOLÉE ...` | Exclue de **toute** analyse (jamais affichée) |
| Projet bricoleur | `Projet bricoleur` | Exclu par défaut (option pour l'inclure avec décote) |
| Doublon | `Doublon probable ...` | Compté une seule fois |
| Nos propres annonces | annonce Facebook Marketplace à **Thetford Mines** | Exclue des comparables |

---

## Vérifier que tout fonctionne (tests automatisés)

Les règles de calcul et l'import sont couverts par des tests. Depuis le dossier
du projet :

```bash
venv\Scripts\python.exe -m pip install -r requirements-dev.txt
venv\Scripts\python.exe -m pytest
```

Les tests vérifient notamment : import d'un CSV conforme, exclusion des cas
particuliers (volée, USD, sur demande, bricoleur), dédoublonnage, recherche par
modèle exact (médiane + 5 à 10 comparables), message clair quand aucun
comparable n'existe, et détection des disparitions / baisses de prix au 2e import.

---

## Déploiement

Aucune étape supplémentaire : le module vit dans DescriGeek. À chaque `git push`,
Railway redéploie l'application. Les nouvelles tables (`listings`,
`import_batches`, `eval_settings`) sont **créées automatiquement** au démarrage
dans la base Supabase existante — rien à migrer à la main.
