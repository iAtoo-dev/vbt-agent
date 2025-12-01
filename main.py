# main.py
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import Optional
import requests
import json
import smtplib
from email.message import EmailMessage
import os
from oscaro_session import get_oscaro_session  # ← session persistante + headers réalistes

app = FastAPI(title="VBT Dépannage - Assistant Vocal Tools")

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
async def lookup_plate(req: PlateRequest):
    plate = clean_plate(req.plate)
    session = get_oscaro_session()

    # 1. Init client → récupère le token
    init_resp = session.get("https://www.oscaro.com/xhr/init-client", timeout=15)
    if init_resp.status_code != 200:
        raise HTTPException(500, "Oscaro: erreur init")
    token = init_resp.json().get("csrf-token")
    if not token:
        raise HTTPException(500, "Token CSRF non trouvé")

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

    marque = labels["core-label"]["fr"].split()[0]
    modele_complet = labels.get("full-label", {}).get("fr", "")
    energie = v.get("energy", {}).get("label", {}).get("fr", "Inconnue")

    # Extraction puissance (ex: "130 cv" → 130)
    puissance = "?"
    for word in modele_complet.split():
        if word.isdigit() and 40 <= int(word) <= 600:
            puissance = word
            break
        if "cv" in word.lower():
            try:
                puissance = "".join(filter(str.isdigit, word))
            except:
                pass

    return {
        "marque": marque,
        "modele_complet": modele_complet,
        "energie": energie,
        "puissance_cv": puissance,
        "raw": v  # au cas où tu veuilles plus d’infos plus tard
    }

@app.post("/send_recap_email")
async def send_recap_email(recap: EmailRecap):
    if not all([os.getenv("SMTP_USER"), os.getenv("SMTP_PASS"), os.getenv("EMAIL_DEST")]):
        raise HTTPException 500, "Variables email manquantes"

    msg = EmailMessage()
    msg["From"] = os.getenv("SMTP_USER")
    msg["To"] = os.getenv("EMAIL_DEST")
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
        with smtplib.SMTP("smtp.hostinger.com", 465) as server:
            server.starttls()
            server.login(os.getenv("SMTP_USER"), os.getenv("SMTP_PASS"))
            server.send_message(msg)
        return {"status": "email envoyé avec succès"}
    except Exception as e:
        raise HTTPException(500, f"Erreur envoi email : {str(e)}")

@app.get("/")
async def root():
    return {"status": "VBT Dépannage API prête", "docs": "/docs"}
