# 🤖 Bot CFr — Accueil & Candidatures

Ce bot est conçu pour le serveur de test CFr.

## Fonctionnement

### 👋 PRÉSENTATION
Le bouton ouvre directement le salon `#présentation`.

### 📋 CANDIDATURE
Le bouton :
1. active le mode candidature pour le membre ;
2. lui fournit un lien direct vers `#présentation` ;
3. attend son prochain message dans `#présentation` ;
4. crée automatiquement un ticket privé `recruteur-pseudo` ;
5. copie le contenu de la candidature dans le ticket ;
6. donne accès au ticket au candidat et au rôle `Recruteur`.

Le message original reste dans `#présentation`, comme demandé.

## Installation

### 1. Installer Python

Installe Python 3.11 ou plus récent.

### 2. Installer les dépendances

Dans le dossier du bot :

```powershell
py -m pip install -r requirements.txt
```

### 3. Créer l'application Discord

Va sur :

https://discord.com/developers/applications

Crée une nouvelle application, puis ajoute un Bot.

Dans l'onglet **Bot**, active :

- **Message Content Intent**

Le bot doit pouvoir :
- voir les salons concernés ;
- envoyer des messages ;
- gérer les salons ;
- gérer les messages si nécessaire.

Invite ensuite le bot sur ton serveur de test avec les scopes :
- `bot`
- `applications.commands`

### 4. Mettre le token

Ne partage jamais le token du bot.

Dans PowerShell :

```powershell
$env:DISCORD_TOKEN="TON_TOKEN_ICI"
py bot.py
```

### 5. Configurer le serveur

Une fois le bot connecté, dans Discord :

```text
/config
```

Choisis :
- **presentation** → `#présentation`
- **recruteur** → le rôle `Recruteur`
- **categorie** → la catégorie où tu veux créer les tickets

Puis :

```text
/welcome
```

Le bot publiera le message avec les deux boutons.

## Important

Discord ne permet pas à un bouton interactif de faire une navigation automatique comme un lien tout en exécutant une interaction. Le bouton **CANDIDATURE** active donc d'abord le mode candidature puis affiche au membre un lien cliquable vers `#présentation`.

Le bouton **PRÉSENTATION**, lui, est un vrai bouton-lien et ouvre directement `#présentation`.

## Sécurité

- Ne donne jamais le token du bot à quelqu'un.
- Si le token est exposé, régénère-le immédiatement dans le Developer Portal.
- Commence sur le serveur de test avant de l'ajouter au serveur CFr principal.