import requests
from bs4 import BeautifulSoup
import pandas as pd
import time
import random
import re
import os
import pickle
import webbrowser
import threading

from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request

import tkinter as tk
from tkinter import ttk, messagebox

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

# ===================== SCRAPING =====================
def scrape_service_public(search_url):
    jobs = []
    page = 1
    while page <= MAX_PAGES:
        url = search_url.rstrip("/") + ("" if page == 1 else f"/page/{page}/")
        try:
            r = requests.get(url, headers=headers, timeout=15)
            soup = BeautifulSoup(r.text, "html.parser")
            page_jobs = []

            for card in soup.select("li.item div.fr-card--offer"):
                # Titre + Lien
                a_tag = card.select_one("h3.fr-card__title a")
                if not a_tag: continue
                title = a_tag.get_text(strip=True)
                link = a_tag.get("href", "")

                # Catégorie (tag coloré ex: "International", "Catégorie A")
                tag_el = card.select_one("ul.fr-tags-group p.fr-tag")
                categorie = tag_el.get_text(strip=True) if tag_el else ""

                # Localisation (icône map-pin)
                loc_el = card.select_one("li.fr-icon-map-pin-2-line")
                if loc_el:
                    for sr in loc_el.select("span.sr-only"): sr.decompose()
                    localisation = loc_el.get_text(strip=True)
                else:
                    localisation = ""

                # Fonction publique (icône file)
                fp_el = card.select_one("li.fr-icon-file-line")
                if fp_el:
                    for sr in fp_el.select("span.sr-only"): sr.decompose()
                    fonction_publique = fp_el.get_text(strip=True)
                else:
                    fonction_publique = ""

                # Employeur (icône user)
                emp_el = card.select_one("li.fr-icon-user-line")
                if emp_el:
                    for sr in emp_el.select("span.sr-only"): sr.decompose()
                    employeur = emp_el.get_text(strip=True)
                else:
                    employeur = ""

                # Date (icône calendar)
                date_el = card.select_one("li.fr-icon-calendar-line")
                if date_el:
                    date_en_ligne = re.sub(r"En ligne depuis le\s*", "", date_el.get_text(strip=True), flags=re.IGNORECASE).strip()
                else:
                    date_en_ligne = ""

                page_jobs.append({
                    "Titre": title, "Lien": link, "Catégorie": categorie,
                    "Localisation": localisation, "Fonction publique": fonction_publique,
                    "Employeur": employeur, "Date en ligne": date_en_ligne
                })

            if not page_jobs:
                break
            jobs.extend(page_jobs)
            time.sleep(random.uniform(1.0, 2.0))
            page += 1
        except:
            break
    return jobs

def scrape_bachem():
    URL = "https://careers.bachem.com/search?locale=fr_FR"
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
                "Titre": title, "Lien": full_link, "Catégorie": categorie,
                "Localisation": localisation, "Fonction publique": fonction,
                "Employeur": "Bachem AG", "Date en ligne": date_en_ligne
            })
        return jobs
    except Exception as e:
        print(f"❌ Erreur Bachem : {e}")
        return []

# ===================== FENÊTRE RÉSULTATS =====================
def afficher_resultats(df, titre_fenetre):
    win = tk.Toplevel()
    win.title(titre_fenetre)
    win.geometry("1200x650")
    win.configure(bg="#f5f5f5")

    # ---- Header ----
    header = tk.Frame(win, bg="#1a73e8", pady=10)
    header.pack(fill="x")
    tk.Label(header, text=titre_fenetre, font=("Arial", 13, "bold"),
             bg="#1a73e8", fg="white").pack(side="left", padx=15)
    tk.Label(header, text=f"{len(df)} offre(s) trouvée(s)",
             font=("Arial", 11), bg="#1a73e8", fg="#cce0ff").pack(side="left", padx=5)

    # ---- Barre de recherche ----
    search_frame = tk.Frame(win, bg="#f5f5f5", pady=8)
    search_frame.pack(fill="x", padx=15)
    tk.Label(search_frame, text="🔎 Filtrer :", font=("Arial", 10), bg="#f5f5f5").pack(side="left")
    search_var = tk.StringVar()
    search_entry = tk.Entry(search_frame, textvariable=search_var, font=("Arial", 11), width=40)
    search_entry.pack(side="left", padx=8)

    # ---- Tableau ----
    cols = ["Titre", "Employeur", "Localisation", "Catégorie", "Date en ligne"]
    cols = [c for c in cols if c in df.columns]

    frame_tree = tk.Frame(win)
    frame_tree.pack(fill="both", expand=True, padx=15, pady=(0, 5))

    scrollbar_y = ttk.Scrollbar(frame_tree, orient="vertical")
    scrollbar_x = ttk.Scrollbar(frame_tree, orient="horizontal")

    style = ttk.Style()
    style.theme_use("clam")
    style.configure("Treeview", font=("Arial", 10), rowheight=28, background="#ffffff",
                    fieldbackground="#ffffff", foreground="#222")
    style.configure("Treeview.Heading", font=("Arial", 10, "bold"), background="#e8f0fe", foreground="#1a73e8")
    style.map("Treeview", background=[("selected", "#1a73e8")], foreground=[("selected", "white")])

    tree = ttk.Treeview(frame_tree, columns=cols, show="headings",
                        yscrollcommand=scrollbar_y.set, xscrollcommand=scrollbar_x.set)

    scrollbar_y.config(command=tree.yview)
    scrollbar_x.config(command=tree.xview)
    scrollbar_y.pack(side="right", fill="y")
    scrollbar_x.pack(side="bottom", fill="x")
    tree.pack(fill="both", expand=True)

    col_widths = {"Titre": 380, "Employeur": 200, "Localisation": 180, "Catégorie": 150, "Date en ligne": 120}
    for col in cols:
        tree.heading(col, text=col, command=lambda c=col: sort_tree(c))
        tree.column(col, width=col_widths.get(col, 150), anchor="w")

    # Stocker liens par iid
    liens = {}

    def populate(data):
        tree.delete(*tree.get_children())
        liens.clear()
        for i, (_, row) in enumerate(data.iterrows()):
            vals = [str(row.get(c, "")) for c in cols]
            tag = "even" if i % 2 == 0 else "odd"
            iid = tree.insert("", "end", values=vals, tags=(tag,))
            liens[iid] = row.get("Lien", "")
        tree.tag_configure("odd", background="#f0f4ff")
        tree.tag_configure("even", background="#ffffff")

    populate(df)

    # ---- Filtrage en temps réel ----
    def on_search(*args):
        q = search_var.get().lower()
        filtered = df[df.apply(lambda r: q in " ".join(r.astype(str).values).lower(), axis=1)] if q else df
        populate(filtered)

    search_var.trace_add("write", on_search)

    # ---- Tri par colonne ----
    sort_state = {}
    def sort_tree(col):
        ascending = sort_state.get(col, True)
        sorted_df = df.copy()
        if col == "Date en ligne":
            sorted_df["_sort"] = sorted_df[col].apply(parse_fr_date)
            sorted_df = sorted_df.sort_values("_sort", ascending=ascending).drop(columns=["_sort"])
        else:
            sorted_df = sorted_df.sort_values(col, ascending=ascending, key=lambda x: x.str.lower())
        sort_state[col] = not ascending
        q = search_var.get().lower()
        filtered = sorted_df[sorted_df.apply(lambda r: q in " ".join(r.astype(str).values).lower(), axis=1)] if q else sorted_df
        populate(filtered)

    # ---- Clic → ouvrir lien ----
    def on_click(event):
        item = tree.identify_row(event.y)
        col_id = tree.identify_column(event.x)
        if item and col_id == "#1":  # colonne Titre
            url = liens.get(item, "")
            if url:
                webbrowser.open(url)

    def on_hover(event):
        item = tree.identify_row(event.y)
        col_id = tree.identify_column(event.x)
        if item and col_id == "#1":
            tree.config(cursor="hand2")
        else:
            tree.config(cursor="")

    tree.bind("<Button-1>", on_click)
    tree.bind("<Motion>", on_hover)

    # ---- Barre du bas : export + compteur ----
    bottom = tk.Frame(win, bg="#f5f5f5", pady=8)
    bottom.pack(fill="x", padx=15)

    def export_excel():
        q = search_var.get().lower()
        to_export = df[df.apply(lambda r: q in " ".join(r.astype(str).values).lower(), axis=1)] if q else df
        fname = "offres_export.xlsx"
        to_export.to_excel(fname, index=False)
        messagebox.showinfo("Export réussi", f"Fichier créé : {fname}")

    tk.Button(bottom, text="💾 Exporter Excel (vue actuelle)", font=("Arial", 10),
              bg="#34a853", fg="white", relief="flat", padx=10, command=export_excel).pack(side="left")
    tk.Label(bottom, text="💡 Cliquez sur un titre pour ouvrir l'offre", font=("Arial", 9),
             bg="#f5f5f5", fg="#777").pack(side="right")


# ===================== FENÊTRE PRINCIPALE =====================
def lancer_interface():
    root = tk.Tk()
    root.title("🛠 Scraper d'Offres d'Emploi")
    root.geometry("520x320")
    root.resizable(False, False)
    root.configure(bg="#f5f5f5")

    # Header
    header = tk.Frame(root, bg="#1a73e8", pady=12)
    header.pack(fill="x")
    tk.Label(header, text="🔬 Scraper d'Offres d'Emploi", font=("Arial", 14, "bold"),
             bg="#1a73e8", fg="white").pack()

    body = tk.Frame(root, bg="#f5f5f5", padx=25, pady=15)
    body.pack(fill="both", expand=True)

    tk.Label(body, text="Site à scraper :", font=("Arial", 10, "bold"), bg="#f5f5f5").pack(anchor="w")
    SITES = {"Choisir le Service Public": "service_public", "Bachem.ch": "bachem"}
    site_var = tk.StringVar(value=list(SITES.keys())[0])
    combo = ttk.Combobox(body, textvariable=site_var, values=list(SITES.keys()), state="readonly", width=45)
    combo.pack(anchor="w", pady=(3, 12))

    tk.Label(body, text="Mots-clés (Service Public uniquement) :", font=("Arial", 10, "bold"), bg="#f5f5f5").pack(anchor="w")
    keyword_entry = tk.Entry(body, width=48, font=("Arial", 11))
    keyword_entry.insert(0, "biologie")
    keyword_entry.pack(anchor="w", pady=(3, 5))
    tk.Label(body, text="⚠️ Bachem affiche tous les postes disponibles",
             font=("Arial", 9), fg="gray", bg="#f5f5f5").pack(anchor="w")

    status_var = tk.StringVar(value="")
    status_label = tk.Label(body, textvariable=status_var, font=("Arial", 9), fg="#e67e22", bg="#f5f5f5")
    status_label.pack(anchor="w", pady=(8, 0))

    def lancer():
        site = SITES[site_var.get()]
        keyword = keyword_entry.get().strip() or "biologie"
        btn.config(state="disabled", text="⏳ Scraping en cours...")
        status_var.set("Scraping en cours, veuillez patienter...")

        def run():
            if site == "service_public":
                keyword_slug = keyword.lower().replace(" ", "-")
                url = f"https://choisirleservicepublic.gouv.fr/nos-offres/filtres/mot-cles/{keyword_slug}/date-de-publication/7_derniers_jours/"
                jobs = scrape_service_public(url)
                titre_fenetre = f"Offres « {keyword} » — Service Public (7 derniers jours)"
                excel_filename = f"offres_service_public_{keyword_slug}.xlsx"
            else:
                jobs = scrape_bachem()
                titre_fenetre = "Offres Bachem AG"
                excel_filename = "offres_bachem.xlsx"

            if jobs:
                df = pd.DataFrame(jobs).drop_duplicates(subset="Lien")
                df["Date_parsed"] = df["Date en ligne"].apply(parse_fr_date)
                df = df.sort_values("Date_parsed", ascending=False).drop(columns=["Date_parsed"])
                df.to_excel(excel_filename, index=False)

                root.after(0, lambda: [
                    status_var.set(f"✅ {len(df)} offres trouvées — Excel créé : {excel_filename}"),
                    btn.config(state="normal", text="🚀 Lancer le scraping"),
                    afficher_resultats(df, titre_fenetre)
                ])
            else:
                root.after(0, lambda: [
                    status_var.set("❌ Aucune offre trouvée."),
                    btn.config(state="normal", text="🚀 Lancer le scraping")
                ])

        threading.Thread(target=run, daemon=True).start()

    btn = tk.Button(root, text="🚀 Lancer le scraping", font=("Arial", 12, "bold"),
                    bg="#1a73e8", fg="white", relief="flat", padx=15, pady=8, command=lancer)
    btn.pack(pady=(0, 15))

    root.mainloop()

# ===================== MAIN =====================
if __name__ == "__main__":
    lancer_interface()