# VBT Dépannage - API Assistant Vocal

API utilisée par l’agent vocal ElevenLabs pour :
- Recherche véhicule par plaque (Oscaro)
- Envoi automatique du récap par email

Déploiement : https://render.com → "New Web Service" → Connecter ce repo → Deploy !

Variables d’environnement à remplir dans Render :
- SMTP_USER → tonemail@gmail.com
- SMTP_PASS → ton App Password Gmail (16 caractères)
- EMAIL_DEST → l’email du patron
