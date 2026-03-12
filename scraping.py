# ===================== scraping.py =====================
import asyncio
import aiohttp
import requests
from bs4 import BeautifulSoup
import pandas as pd
import re

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/134.0.0.0 Safari/537.36"
}
MAX_PAGES = 30
MAX_CONCURRENT = 5

MONTH_MAP = {
    "janvier": 1, "février": 2, "mars": 3, "avril": 4, "mai": 5, "juin": 6,
    "juillet": 7, "août": 8, "septembre": 9, "octobre": 10,
    "novembre": 11, "décembre": 12
}

CATEGORIES_EXCLUES = {
    "Environnement",
    "Intervention technique et logistique",
    "Prévention, conseil et pilotage en santé",
    "Sécurité",
    "Transports",
    "Bâtiment",
    "Direction et pilotage des politiques publiques",
    "Aménagement et développement durable du territoire",
    "Agriculture"
}


# ── Utilitaires ────────────────────────────────────────────────────────────────

def parse_fr_date(date_str):
    if not date_str:
        return None
    try:
        parts = date_str.strip().split()
        day = int(parts[0])
        month = MONTH_MAP[parts[1].lower()]
        year = int(parts[2])
        return pd.Timestamp(year=year, month=month, day=day)
    except Exception:
        return None


def _extract_li(card, selector: str) -> str:
    """Extrait le texte d'un <li> en supprimant les spans sr-only."""
    el = card.select_one(selector)
    if not el:
        return ""
    for sr in el.select("span.sr-only"):
        sr.decompose()
    return el.get_text(strip=True)


# ── service-public.fr ──────────────────────────────────────────────────────────

def _parse_service_public_page(html: str) -> list[dict]:
    """Parse le HTML d'une page service-public et retourne les offres filtrées."""
    soup = BeautifulSoup(html, "html.parser")
    page_jobs = []

    for card in soup.select("li.item div.fr-card--offer"):
        a_tag = card.select_one("h3.fr-card__title a")
        if not a_tag:
            continue
        title = a_tag.get_text(strip=True)
        link = a_tag.get("href", "")

        tag_el = card.select_one("ul.fr-tags-group p.fr-tag")
        categorie = tag_el.get_text(strip=True) if tag_el else ""
        if categorie in CATEGORIES_EXCLUES:
            continue

        localisation      = _extract_li(card, "li.fr-icon-map-pin-2-line")
        fonction_publique = _extract_li(card, "li.fr-icon-file-line")
        employeur         = _extract_li(card, "li.fr-icon-user-line")

        date_raw = _extract_li(card, "li.fr-icon-calendar-line")
        date_en_ligne = re.sub(
            r"En ligne depuis le\s*", "", date_raw, flags=re.IGNORECASE
        ).strip()

        page_jobs.append({
            "Titre": title,
            "Lien": link,
            "Catégorie": categorie,
            "Localisation": localisation,
            "Fonction publique": fonction_publique,
            "Employeur": employeur,
            "Date en ligne": date_en_ligne,
        })

    return page_jobs


async def _fetch_page(
    session: aiohttp.ClientSession,
    url: str,
    sem: asyncio.Semaphore,
) -> str | None:
    """Récupère le HTML d'une URL avec gestion du sémaphore et des erreurs."""
    async with sem:
        try:
            async with session.get(
                url, timeout=aiohttp.ClientTimeout(total=15)
            ) as resp:
                if resp.status != 200:
                    return None
                return await resp.text()
        except Exception:
            return None


async def _scrape_service_public_async(search_url: str) -> list[dict]:
    base_url = search_url.rstrip("/")
    sem = asyncio.Semaphore(MAX_CONCURRENT)

    async with aiohttp.ClientSession(headers=HEADERS) as session:
        # Page 1 en premier pour valider que le site répond
        first_html = await _fetch_page(session, base_url, sem)
        if not first_html:
            return []
        first_jobs = _parse_service_public_page(first_html)
        if not first_jobs:
            return []

        # Pages 2..MAX_PAGES en parallèle
        urls = [base_url + f"/page/{p}/" for p in range(2, MAX_PAGES + 1)]
        results = await asyncio.gather(
            *[_fetch_page(session, url, sem) for url in urls]
        )

    # Assemblage dans l'ordre
    all_jobs = first_jobs[:]
    for html in results:
        if not html:
            continue
        page_jobs = _parse_service_public_page(html)
        if not page_jobs:
            break  # Fin de pagination
        all_jobs.extend(page_jobs)

    return all_jobs


def scrape_service_public(search_url: str) -> list[dict]:
    """Point d'entrée synchrone — interface identique à l'ancienne version."""
    return asyncio.run(_scrape_service_public_async(search_url))


# ── Bachem ─────────────────────────────────────────────────────────────────────

def scrape_bachem() -> list[dict]:
    URL = "https://careers.bachem.com/search?locale=fr_FR"
    try:
        r = requests.get(URL, headers=HEADERS, timeout=15)
        soup = BeautifulSoup(r.text, "html.parser")
        jobs = []

        for a in soup.find_all("a", href=True):
            href = a.get("href", "")
            if "/job/" not in href:
                continue
            title = a.get_text(strip=True)
            if len(title) < 5:
                continue

            full_link = (
                "https://careers.bachem.com" + href
                if href.startswith("/")
                else href
            )

            tr = a.find_parent("tr")
            if not tr:
                continue
            tds = tr.find_all("td")
            if len(tds) < 6:
                continue

            localisation  = tds[1].get_text(strip=True)
            categorie     = tds[2].get_text(strip=True)
            fonction      = tds[3].get_text(strip=True)
            date_en_ligne = tds[5].get_text(strip=True)

            jobs.append({
                "Titre": title,
                "Lien": full_link,
                "Catégorie": categorie,
                "Localisation": localisation,
                "Fonction publique": fonction,
                "Employeur": "Bachem AG",
                "Date en ligne": date_en_ligne,
            })

        return jobs

    except Exception as e:
        print(f"❌ Erreur Bachem : {e}")
        return []