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

# ===================== TKINTER - INTERFACE =====================
import tkinter as tk
from tkinter import ttk

def choisir_site():
    root = tk.Tk()
    root.title("🛠 Scraper d'Offres d'Emploi")
    root.geometry("500x280")
    root.resizable(False, False)

    tk.Label(root, text="Quel site veux-tu scraper ?", font=("Arial", 12, "bold")).pack(pady=10)

    SITES = {
        "Choisir le Service Public": "service_public",
        "Bachem.ch": "bachem"
    }

    site_var = tk.StringVar()
    site_var.set(list(SITES.keys())[0])

    combo = ttk.Combobox(root, textvariable=site_var, values=list(SITES.keys()), state="readonly", width=45)
    combo.pack(pady=5)

    # === BARRE MOTS-CLÉS EN BAS ===
    tk.Label(root, text="Mots-clés (un seul mot recommandé) :", font=("Arial", 10)).pack(pady=(15, 5))
    keyword_entry = tk.Entry(root, width=50, font=("Arial", 11))
    keyword_entry.insert(0, "biologie")
    keyword_entry.pack(pady=5)

    tk.Label(root, text="⚠️ Mots-clés utilisés uniquement pour Service Public\n(Bachem affiche tous les postes)", 
             font=("Arial", 9), fg="gray").pack(pady=5)

    def lancer():
        global SITE_CHOISI, KEYWORD
        SITE_CHOISI = SITES[site_var.get()]
        KEYWORD = keyword_entry.get().strip()
        root.destroy()

    tk.Button(root, text="🚀 Lancer le scraping", font=("Arial", 12), bg="#4CAF50", fg="white", command=lancer).pack(pady=15)
    root.mainloop()

# ===================== CONFIG =====================
headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/134.0.0.0 Safari/537.36"
}

MAX_PAGES = 30

# ===================== AUTH DRIVE =====================
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

def upload_to_drive(file_path):
    service = get_drive_service()
    file_metadata = {"name": os.path.basename(file_path)}
    media = MediaFileUpload(file_path, mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", resumable=True)
    file = service.files().create(body=file_metadata, media_body=media, fields="id").execute()
    print(f"✅ Upload Drive réussi ! ID : {file.get('id')}")

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

# ===================== SCRAPE SERVICE PUBLIC (URL dynamique) =====================
def scrape_service_public(search_url):
    jobs = []
    page = 1
    while page <= MAX_PAGES:
        url = search_url.rstrip("/") + ("" if page == 1 else f"/page/{page}/")
        print(f"🔍 Service Public - page {page} → {url}")
        try:
            r = requests.get(url, headers=headers, timeout=15)
            soup = BeautifulSoup(r.text, "html.parser")
            page_jobs = []
            for a in soup.find_all("a", href=True):
                href = a.get("href", "")
                if "/offre-emploi/" not in href: continue
                title = a.get_text(strip=True)
                if len(title) < 15: continue
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

                page_jobs.append({
                    "Titre": title, "Lien": link, "Catégorie": categorie,
                    "Localisation": localisation, "Fonction publique": fonction_publique,
                    "Employeur": employeur, "Date en ligne": date_en_ligne
                })
            if not page_jobs:
                print(f"✅ Fin du scraping (page {page} vide)")
                break
            jobs.extend(page_jobs)
            print(f"   → {len(page_jobs)} offres")
            time.sleep(random.uniform(1.0, 2.0))
            page += 1
        except:
            break
    return jobs

# ===================== SCRAPE BACHEM (inchangé - tous les postes) =====================
def scrape_bachem():
    URL = "https://careers.bachem.com/search?locale=fr_FR"
    print(f"🔍 Scraping Bachem → {URL}")
    try:
        r = requests.get(URL, headers=headers, timeout=15)
        soup = BeautifulSoup(r.text, "html.parser")
        jobs = []
        for a in soup.find_all("a", href=True):
            href = a.get("href", "")
            if "/job/" not in href: continue
            title = a.get_text(strip=True)
            if len(title) < 5: continue
            full_link = "https://careers.bachem.com" + href if href.startswith("/") else href

            tr = a.find_parent("tr")
            if not tr: continue
            tds = tr.find_all("td")
            if len(tds) < 6: continue

            localisation = tds[1].get_text(strip=True)
            categorie = tds[2].get_text(strip=True)
            fonction = tds[3].get_text(strip=True)
            date_en_ligne = tds[5].get_text(strip=True)

            jobs.append({
                "Titre": title,
                "Lien": full_link,
                "Catégorie": categorie,
                "Localisation": localisation,
                "Fonction publique": fonction,
                "Employeur": "Bachem AG",
                "Date en ligne": date_en_ligne
            })
        print(f"✅ {len(jobs)} postes récupérés chez Bachem.")
        return jobs
    except Exception as e:
        print(f"❌ Erreur Bachem : {e}")
        return []

# ===================== PROGRAMME PRINCIPAL =====================
if __name__ == "__main__":
    choisir_site()

    print(f"\n🚀 Démarrage pour : {SITE_CHOISI}")

    if SITE_CHOISI == "service_public":
        if not KEYWORD:
            KEYWORD = "biologie"
        keyword_slug = KEYWORD.lower().replace(" ", "-")
        SEARCH_URL = f"https://choisirleservicepublic.gouv.fr/nos-offres/filtres/mot-cles/{keyword_slug}/date-de-publication/7_derniers_jours/"
        print(f"   URL construite : {SEARCH_URL}")

        jobs_base = scrape_service_public(SEARCH_URL)
        filtered_jobs = jobs_base                    # déjà filtré par l'URL
        excel_filename = f"offres_service_public_{keyword_slug}.xlsx"

    else:  # bachem
        if KEYWORD and KEYWORD.lower() != "biologie":
            print("⚠️ Mots-clés ignorés pour Bachem (tous les postes sont affichés)")
        jobs_base = scrape_bachem()
        filtered_jobs = jobs_base
        excel_filename = "offres_bachem.xlsx"

    if filtered_jobs:
        df = pd.DataFrame(filtered_jobs).drop_duplicates(subset="Lien")
        df["Date_parsed"] = df["Date en ligne"].apply(parse_fr_date)
        df = df.sort_values(by="Date_parsed", ascending=False).drop(columns=["Date_parsed"])

        df.to_excel(excel_filename, index=False)
        print(f"📊 Excel créé : {excel_filename}")
        # upload_to_drive(excel_filename)  #ligne ignoré mais je garde pour une utilisation ulterieur
    else:
        print("❌ Aucune offre trouvée.")

    print("🎉 Script terminé !")