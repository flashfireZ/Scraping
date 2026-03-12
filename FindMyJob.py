import requests
from bs4 import BeautifulSoup
import pandas as pd
import time
import random
import re
import os
import pickle

from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request

# ===================== TKINTER - INTERFACE DE CHOIX =====================
import tkinter as tk
from tkinter import ttk

def choisir_site():
    root = tk.Tk()
    root.title("🛠 Sélecteur de Site à Scraper")
    root.geometry("420x180")
    root.resizable(False, False)

    tk.Label(root, text="Quel site veux-tu scraper ?", font=("Arial", 12)).pack(pady=15)

    # Ajoute ici d'autres sites plus tard !
    SITES = {
        "Choisir le Service Public (biologie - 7 derniers jours)": 
            "https://choisirleservicepublic.gouv.fr/nos-offres/filtres/mot-cles/biologie/date-de-publication/7_derniers_jours/"
        # Exemple futur : "Pôle Emploi": "https://candidat.pole-emploi.fr/offres/..."
    }

    site_var = tk.StringVar()
    site_var.set(list(SITES.keys())[0])   # sélection par défaut

    combo = ttk.Combobox(root, textvariable=site_var, values=list(SITES.keys()), state="readonly", width=50)
    combo.pack(pady=10)

    def lancer():
        global SEARCH_URL
        SEARCH_URL = SITES[site_var.get()]
        root.destroy()

    tk.Button(root, text="🚀 Lancer le scraping", font=("Arial", 11), bg="#4CAF50", fg="white", command=lancer).pack(pady=15)

    root.mainloop()

# ===================== CONFIG (devient dynamique) =====================
headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/134.0.0.0 Safari/537.36"
}

MAX_PAGES = 30

# ===================== AUTH DRIVE =====================
# (identique à avant)
SCOPES = ["https://www.googleapis.com/auth/drive.file"]
CREDENTIALS_FILE = "credentials.json"
TOKEN_FILE = "token.pickle"

def get_drive_service():
    creds = None
    if os.path.exists(TOKEN_FILE):
        with open(TOKEN_FILE, "rb") as token:
            creds = pickle.load(token)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(CREDENTIALS_FILE, SCOPES)
            creds = flow.run_local_server(port=0)
        with open(TOKEN_FILE, "wb") as token:
            pickle.dump(creds, token)
    return build("drive", "v3", credentials=creds)

def upload_to_drive(file_path, folder_id=None):
    service = get_drive_service()
    file_metadata = {"name": os.path.basename(file_path)}
    if folder_id:
        file_metadata["parents"] = [folder_id]
    media = MediaFileUpload(file_path, mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", resumable=True)
    file = service.files().create(body=file_metadata, media_body=media, fields="id").execute()
    print(f"✅ Upload Drive réussi ! ID : {file.get('id')}")
    return file.get('id')

# ===================== PARSING DATE =====================
MONTH_MAP = {
    "janvier": 1, "février": 2, "mars": 3, "avril": 4, "mai": 5, "juin": 6,
    "juillet": 7, "août": 8, "septembre": 9, "octobre": 10,
    "novembre": 11, "décembre": 12
}

def parse_fr_date(date_str):
    if not date_str: return None
    try:
        parts = date_str.strip().split()
        day = int(parts[0])
        month = MONTH_MAP[parts[1].lower()]
        year = int(parts[2])
        return pd.Timestamp(year=year, month=month, day=day)
    except:
        return None

# ===================== SCRAPE UNE PAGE =====================
def scrape_jobs_from_page(url):
    print(f"🔍 Scraping → {url}")
    try:
        r = requests.get(url, headers=headers, timeout=15)
        if r.status_code != 200:
            return []
        soup = BeautifulSoup(r.text, "html.parser")

        jobs = []
        for a in soup.find_all("a", href=True):
            href = a.get("href", "")
            if "/offre-emploi/" not in href:
                continue
            title = a.get_text(strip=True)
            if len(title) < 15:
                continue

            link = "https://choisirleservicepublic.gouv.fr" + href if href.startswith("/") else href

            card = a.find_parent("li") or a.parent
            meta_texts = [li.get_text(strip=True) for li in card.find_all("li") if li.get_text(strip=True)]

            categorie = localisation = fonction_publique = employeur = date_en_ligne = ""
            for m in meta_texts:
                m_clean = m.strip()
                if "Fonction publique" in m_clean:
                    fonction_publique = m_clean
                elif "En ligne depuis" in m_clean:
                    date_en_ligne = re.sub(r"En ligne depuis le\s*", "", m_clean, flags=re.IGNORECASE).strip()
                elif "*" in m_clean and not localisation:
                    split = [p.strip() for p in m_clean.split("*") if p.strip()]
                    categorie = split[0] if split else ""
                    localisation = split[1] if len(split) > 1 else ""
                elif not employeur and not any(k in m_clean for k in ["Fonction publique", "En ligne depuis"]):
                    employeur = m_clean

            jobs.append({
                "Titre": title,
                "Lien": link,
                "Catégorie": categorie,
                "Localisation": localisation,
                "Fonction publique": fonction_publique,
                "Employeur": employeur,
                "Date en ligne": date_en_ligne
            })
        return jobs
    except Exception as e:
        print(f"❌ Erreur : {e}")
        return []

# ===================== PROGRAMME PRINCIPAL =====================
if __name__ == "__main__":
    # 1. Fenêtre de choix
    choisir_site()

    # 2. Scraping de toutes les pages
    print(f"\n🔍 Démarrage du scraping sur : {SEARCH_URL}")
    jobs_base = []
    page = 1

    while page <= MAX_PAGES:
        url = SEARCH_URL.rstrip("/") + ("/" if page == 1 else f"/page/{page}/")
        page_jobs = scrape_jobs_from_page(url)
        
        if not page_jobs:
            print(f"✅ Fin du scraping (page {page} vide)")
            break
            
        jobs_base.extend(page_jobs)
        print(f"   → {len(page_jobs)} offres sur la page {page}")
        
        time.sleep(random.uniform(1.0, 2.0))
        page += 1

    print(f"✅ {len(jobs_base)} offres récupérées au total.")

    # 3. Filtrage + Excel
    filtered_jobs = [job for job in jobs_base if "biologie" in job["Titre"].lower()]

    print(f"✅ {len(filtered_jobs)} offres gardées (filtre 'biologie' dans le titre).")

    if filtered_jobs:
        df = pd.DataFrame(filtered_jobs).drop_duplicates(subset="Lien")
        df["Date_parsed"] = df["Date en ligne"].apply(parse_fr_date)
        df = df.sort_values(by="Date_parsed", ascending=False).drop(columns=["Date_parsed"])

        excel_filename = "offres_service_public_biologie.xlsx"
        df.to_excel(excel_filename, index=False)
        print(f"📊 Excel créé : {excel_filename}")
        # garder upload_to_drive pour une eventuelle utilisation
        #upload_to_drive(excel_filename)
    else:
        print("❌ Aucune offre trouvée.")

    print("🎉 Script terminé !")