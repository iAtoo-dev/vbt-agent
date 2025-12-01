# main.py
from fastapi import FastAPI, HTTPException, Header, Depends
from fastapi.security import APIKeyHeader
from pydantic import BaseModel
from typing import Optional
import requests
import os
from email.message import EmailMessage
import smtplib
from oscaro_session import get_oscaro_session

app = FastAPI(title="VBT Dépannage - Assistant Vocal Tools")

# ==================== SÉCURITÉ : CLÉ API ====================
API_KEY = os.getenv("VBT_API_KEY", "change-me-immediately")  # À définir dans Render !
api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)

async def verify_api_key(x_api_key: str = Depends(api_key_header)):
    if not x_api_key or x_api_key != API_KEY:
        raise HTTPException(status_code=403, detail="Clé API manquante ou invalide")

# ===========================================================

class PlateRequest(BaseModel):
    plate: str

class EmailRecap(BaseModel):
    phone: str
    plate: Optional[str] = None
    vehicle_info: str
    request_type: str
    location: str
    availability: str
    call_summary: str
    client_mood: str

def clean_plate(plate: str) -> str:
    return plate.upper().replace(" ", "").replace("-", "")

@app.post("/lookup_plate")
async def lookup_plate(req: PlateRequest, _: str = Depends(verify_api_key)):
    plate = clean_plate(req.plate)
    session = get_oscaro_session()

    # 1. Récupération du token Oscaro
    init_resp = session.get("https://www.oscaro.com/xhr/init-client", timeout=15)
    if init_resp.status_code != 200:
        raise HTTPException(status_code=500, detail="Oscaro: erreur init")
    token = init_resp.json().get("csrf-token")
    if not token:
        raise HTTPException(status_code=500, detail="Token CSRF non trouvé")

    # 2. Recherche plaque
    search_url = "https://www.oscaro.com/xhr/dionysos-search/fr/fr"
    headers = {
        "X-Csrf-Token": token,
        "X-Requested-With": "XMLHttpRequest",
        "Accept": "application/json",
    }
    r = session.get(search_url, params={"plate": plate}, headers=headers, timeout=15)

    if r.status_code != 200 or not r.json().get("vehicles"):
        return {"error": "Plaque non trouvée ou véhicule inconnu"}

    v = r.json()["vehicles"][0]
    labels = v["labels"]
    marque = labels.get("core-label", {}).get("fr", "Inconnue").split()[0]
    modele_complet = labels.get("full-label", {}).get("fr", "")
    energie = v.get("energy", {}).get("label", {}).get("fr", "Inconnue")

    # Extraction puissance fiable (cherche le nombre juste avant "cv")
    puissance = "?"
    words = modele_complet.lower().split()
    for i, word in enumerate(words):
        if "cv" in word and i > 0:
            prev = words[i-1]
            if prev.isdigit() and 40 <= int(prev) <= 600:
                puissance = prev
                break
    if puissance == "?":
        for word in words:
            if word.isdigit() and 40 <= int(word) <= 600:
                puissance = word
                break

    return {
        "marque": marque,
        "modele_complet": modele_complet,
        "energie": energie,
        "puissance_cv": puissance,
        "raw": v
    }

@app.post("/send_recap_email")
async def send_recap_email(recap: EmailRecap, _: str = Depends(verify_api_key)):
    smtp_user = os.getenv("SMTP_USER")
    smtp_pass = os.getenv("SMTP_PASS")
    email_dest = os.getenv("EMAIL_DEST")
    
    if not all([smtp_user, smtp_pass, email_dest]):
        raise HTTPException(status_code=500, detail="Variables SMTP manquantes")

    msg = EmailMessage()
    msg["From"] = smtp_user
    msg["To"] = email_dest
    msg["Subject"] = f"Nouvelle demande - {recap.plate or 'Sans plaque'} - {recap.request_type}"

    body = f"""
NOUVELLE DEMANDE REÇUE

Téléphone : {recap.phone}
Immatriculation : {recap.plate or "Non fournie"}
Véhicule : {recap.vehicle_info}
Demande : {recap.request_type}
Localisation : {recap.location}
Disponibilités : {recap.availability}

Résumé appel :
{recap.call_summary}

Humeur client : {recap.client_mood}
    """.strip()
    msg.set_content(body)

    try:
        # === SOLUTION QUI MARCHE À 100% AVEC HOSTINGER SUR RENDER ===
        import ssl
        context = ssl.create_default_context()
        with smtplib.SMTP_SSL("smtp.hostinger.com", 465, context=context) as server:
            server.login(smtp_user, smtp_pass)
            server.send_message(msg)
        # ===========================================================
        return {"status": "Email envoyé avec succès via Hostinger"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erreur SMTP Hostinger : {str(e)}")

@app.get("/")
async def root():
    return {"status": "VBT Dépannage API prête – clé API requise sur /lookup_plate et /send_recap_email", "docs": "/docs"}
