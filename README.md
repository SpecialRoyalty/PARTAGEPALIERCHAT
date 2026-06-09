# Telegram Growth Bot — Admin 100% Telegram

Tout se gère depuis Telegram.

## Fonctions

### Admin Telegram
Quand un admin fait `/start`, le bot détecte son ID avec `ADMIN_IDS` et affiche :

- 🆕 Groupes en attente
- ✅ Groupes validés
- 📢 Campagnes pub
- 🎁 Paliers / Gofile
- 🚫 Mots bannis
- 📊 Statistiques
- ℹ️ Info bot

### Utilisateur
- voit la pub dans un groupe
- clique "🎁 Recevoir des médias"
- reçoit son lien unique
- reçoit une notification quand quelqu'un rejoint avec son lien
- reçoit une notification après validation
- reçoit automatiquement les liens Gofile quand il atteint un palier

## Variables Railway

```env
BOT_TOKEN=token_botfather
DATABASE_URL=postgresql+asyncpg://postgres:pass@postgres.railway.internal:5432/railway
WEBHOOK_BASE_URL=https://ton-app.up.railway.app
ADMIN_IDS=ton_id_telegram,autre_id
```

## Important Telegram

Dans BotFather :
- désactiver Group Privacy

Dans les groupes :
- le bot doit être admin
- droits nécessaires : supprimer messages, bannir membres, créer liens d'invitation

## Déploiement Railway

1. Upload sur GitHub
2. Connecte Railway
3. Ajoute PostgreSQL
4. Mets les variables
5. Deploy
6. Va sur Telegram et fais `/start`
