# Telegram Growth Bot — Railway + Python + PostgreSQL

Bot Telegram avec :
- validation des groupes depuis admin
- campagnes pub texte/photo
- auto-publication tous les 100 messages
- suppression auto après 20 min
- bouton "Recevoir des médias"
- lien d'invitation unique par utilisateur/groupe
- tracking des invités
- validation après 10 minutes
- paliers Gofile / récompenses
- anti-mots interdits dans pseudo/nom
- notification admins
- participation à un seul groupe à la fois

## Stack
- Python 3.11+
- FastAPI
- python-telegram-bot
- SQLAlchemy async
- PostgreSQL
- Railway

## Variables Railway

```env
BOT_TOKEN=123456:ABC
DATABASE_URL=postgresql+asyncpg://user:pass@host:port/db
WEBHOOK_BASE_URL=https://ton-app.up.railway.app
ADMIN_TOKEN=change-moi
ADMIN_IDS=123456789,987654321
SECRET_KEY=change-moi-long
```

## Installation locale

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
python -m app.main
```

## Déploiement Railway

1. Créer projet Railway
2. Ajouter PostgreSQL
3. Ajouter les variables d'environnement
4. Déployer depuis GitHub
5. Railway expose l'app FastAPI
6. Au démarrage, le webhook Telegram est configuré automatiquement

## Notes Telegram importantes

Le bot doit être admin des groupes avec :
- can_delete_messages
- can_invite_users
- can_restrict_members
- can_manage_chat idéalement

Pour tracker les entrées classiques, on utilise `chat_member`.
Pour les liens avec demande d'approbation, Telegram peut envoyer `chat_join_request`.
