"""
SchedulerMarches — Veille marchés publics par secteur d'activité.

Sources actives (ordre de priorité) :
  1. SerpAPI Google Search  — "appel d'offres {secteur} {pays}" + plateformes ARMP locales
     → Variable : SERPAPI_KEY (déjà dans .env)
  2. dgMarket RSS           — World Bank / UN procurement, couvre Afrique + international
     → Gratuit, aucune clé
  3. UNGM                   — UN Global Marketplace, secteurs ONU/ONG
     → Gratuit, aucune clé
  4. Plateformes ARMP locales ciblées via SerpAPI (ARMP-CM, ARMP-CI, DGMP-SN…)

Cycle : toutes les 6 heures par défaut (marchés publics = données qui changent vite).
Stockage : ProfilProfessionnelDB.marches_publics_recents (JSON, max 15 avis).
"""
from __future__ import annotations

import asyncio
import logging
import os
import re
import urllib.parse
from datetime import datetime, timezone, timedelta

logger = logging.getLogger("yukpo_assurance.pro.scheduler_marches")

_CYCLE_VERIFICATION = 2 * 60 * 60   # vérifier toutes les 2h
_FREQUENCE_DEFAUT   = 6              # heures entre deux recherches par user
_MAX_MARCHES        = 15

_running = False

# ── Plateformes d'appel d'offres par pays ─────────────────────────────────────

_PLATEFORMES_PAYS: dict[str, list[str]] = {
    "CM": ["armp.cm", "minmap.cm", "marchespublics.cm", "spm.cm"],
    "CI": ["marchespublics.ci", "armp-ci.org"],
    "SN": ["marchespublics.sn", "dgcmp.sn", "onas.sn"],
    "GA": ["anrmp.ga", "marchespublics.ga"],
    "BF": ["arcop.bf", "marchespublics.bf"],
    "ML": ["armds.ml", "marchespublics.gov.ml"],
    "TG": ["armp.tg", "marchespublics.tg"],
    "BJ": ["armp.bj", "marchespublics.bj"],
    "CD": ["armp.cd", "marchespublics.gouv.cd"],
    "MG": ["armp.mg"],
    "MA": ["marchespublics.gov.ma", "mtpnet.gov.ma"],
    "TN": ["marchespublics.gov.tn"],
    "DZ": ["mfdgi.gov.dz"],
    "FR": ["boamp.fr", "marches-publics.info"],
    "BE": ["publicprocurement.be"],
    "CA": ["canadabuys.canada.ca", "seao.ca"],
}

# ── Mots-clés sectoriels pour les appels d'offres ─────────────────────────────

_SECTEURS_MARCHES: dict[str, list[str]] = {
    # Métiers financiers
    "comptable":          ["audit", "expertise comptable", "commissariat aux comptes", "contrôle financier"],
    "auditeur":           ["audit externe", "audit interne", "commissariat", "contrôle"],
    "financier":          ["services financiers", "trésorerie", "gestion budgétaire"],
    "fiscaliste":         ["conseil fiscal", "optimisation fiscale"],
    "actuaire":           ["actuariat", "assurance", "prévoyance"],
    # Juridique
    "juriste":            ["conseil juridique", "assistance juridique", "contentieux", "notariat"],
    "avocat":             ["représentation juridique", "conseil légal"],
    # BTP / Ingénierie
    "ingenieur":          ["génie civil", "travaux", "construction", "infrastructure", "bâtiment"],
    "architecte":         ["architecture", "maîtrise d'œuvre", "conception"],
    "topographe":         ["topographie", "géomètre", "cadastre"],
    "electrique":         ["électricité", "énergie", "installation électrique"],
    # Informatique / Numérique
    "informaticien":      ["systèmes d'information", "développement logiciel", "infogérance", "cybersécurité"],
    "developpeur":        ["développement web", "application mobile", "ERP", "CRM"],
    "data":               ["data science", "analyse de données", "intelligence artificielle"],
    "telecom":            ["télécommunications", "réseaux", "fibre optique"],
    # Santé
    "medecin":            ["équipements médicaux", "santé publique", "médicaments", "hôpital"],
    "pharmacien":         ["médicaments", "produits pharmaceutiques"],
    "infirmier":          ["soins infirmiers", "services de santé"],
    # Éducation / Formation
    "enseignant":         ["formation professionnelle", "e-learning", "édition scolaire"],
    "formateur":          ["formation", "renforcement de capacités", "séminaires"],
    # Logistique / Transport
    "logisticien":        ["logistique", "transport", "fret", "supply chain"],
    "transporteur":       ["transport", "fret routier", "livraison"],
    # Agro / Environnement
    "agronome":           ["agriculture", "semences", "irrigation", "équipements agricoles"],
    "environnement":      ["études environnementales", "impact environnemental", "eau"],
    # Communication / Marketing
    "communicant":        ["communication institutionnelle", "relations publiques", "événementiel"],
    "graphiste":          ["conception graphique", "identité visuelle", "imprimerie"],
    # RH
    "drh":                ["recrutement", "conseil RH", "gestion des ressources humaines"],
    # Gestion de projet
    "projectmanager":     ["gestion de projet", "maîtrise d'ouvrage", "AMO"],
    # Default
    "professionnel":      ["services", "conseil", "études"],
}

def _mots_cles_marches(profil) -> list[str]:
    """Retourne 2-3 termes de recherche pour les marchés publics selon le profil."""
    metier = (getattr(profil, "metier", "") or "professionnel").lower().replace("_", " ")
    secteur_activite = (getattr(profil, "secteur_activite", "") or "").lower()

    # Chercher la correspondance la plus proche dans le dictionnaire
    termes: list[str] = []
    for cle, mots in _SECTEURS_MARCHES.items():
        if cle in metier or metier in cle:
            termes = mots[:2]
            break

    if not termes:
        termes = [secteur_activite or metier, "services"]

    return termes


# ── Point d'entrée public ──────────────────────────────────────────────────────

async def demarrer_scheduler_marches():
    global _running
    if _running:
        return
    _running = True
    logger.info("[SchedulerMarches] Démarrage veille marchés publics")
    asyncio.create_task(_boucle_veille_marches(), name="scheduler_marches")


async def arreter_scheduler_marches():
    global _running
    _running = False


# ── Boucle principale ─────────────────────────────────────────────────────────

async def _boucle_veille_marches():
    await asyncio.sleep(90)   # délai initial décalé du scheduler emploi
    while _running:
        try:
            await _cycle_marches_tous_users()
        except Exception as e:
            logger.error(f"[SchedulerMarches] Erreur cycle: {e}")
        await asyncio.sleep(_CYCLE_VERIFICATION)


async def _cycle_marches_tous_users():
    try:
        from core.database import async_session_maker
        from modules.pro.profil_pro import ProfilProfessionnelDB
        from sqlalchemy import select

        async with async_session_maker() as db:
            result = await db.execute(select(ProfilProfessionnelDB).where(ProfilProfessionnelDB.actif == True))
            profils = result.scalars().all()

        if not profils:
            return

        now = datetime.now(timezone.utc)
        for profil in profils:
            try:
                derniere = getattr(profil, "derniere_recherche_marches", None)
                if derniere and derniere.tzinfo is None:
                    derniere = derniere.replace(tzinfo=timezone.utc)
                if derniere and (now - derniere) < timedelta(hours=_FREQUENCE_DEFAUT):
                    continue
                await rechercher_marches_pour_user(user_id=profil.user_id, profil=profil)
            except Exception as e:
                logger.error(f"[SchedulerMarches] Erreur user {profil.user_id}: {e}")

    except Exception as e:
        logger.error(f"[SchedulerMarches] Erreur cycle global: {e}")


# ── Recherche principale ───────────────────────────────────────────────────────

async def rechercher_marches_pour_user(user_id: int, profil=None) -> int:
    pays = (getattr(profil, "pays", None) or "CM").upper()
    from modules.pro.scheduler_emploi import _info_pays
    info = _info_pays(pays)

    termes = _mots_cles_marches(profil)
    logger.info(f"[SchedulerMarches] user {user_id} · {info['nom']} · {termes}")

    resultats = await asyncio.gather(
        _fetch_serpapi_marches(termes, pays, info),
        _fetch_dgmarket(pays),
        _fetch_ungm(termes),
        return_exceptions=True,
    )

    marches_bruts: list[dict] = []
    noms = ["SerpAPI", "dgMarket", "UNGM"]
    for nom, res in zip(noms, resultats):
        if isinstance(res, list):
            logger.info(f"[SchedulerMarches] {nom}: {len(res)} avis")
            marches_bruts.extend(res)
        elif isinstance(res, Exception):
            logger.debug(f"[SchedulerMarches] {nom} erreur: {res}")

    # Dédoublonnage
    seen: set[str] = set()
    uniques: list[dict] = []
    for m in marches_bruts:
        key = (m.get("url") or m.get("titre", "")).strip().lower()[:120]
        if key and key not in seen:
            seen.add(key)
            uniques.append(m)

    if not uniques:
        logger.info(f"[SchedulerMarches] 0 avis trouvés pour user {user_id}")
        await _sauvegarder_marches(user_id, [])
        return 0

    # Trier par date desc (les plus récents en premier), limiter
    uniques = uniques[:_MAX_MARCHES]
    await _sauvegarder_marches(user_id, uniques)
    return len(uniques)


# ── Source 1 : SerpAPI ────────────────────────────────────────────────────────

async def _fetch_serpapi_marches(termes: list[str], pays: str, info: dict) -> list[dict]:
    api_key = os.getenv("SERPAPI_KEY", "")
    if not api_key or api_key.startswith("VOTRE"):
        return []

    try:
        import httpx
        marches: list[dict] = []
        plateformes = _PLATEFORMES_PAYS.get(pays, [])

        # Requête 1 : appels d'offres généraux du secteur dans le pays
        q1 = f"appel d'offres {' '.join(termes[:1])} {info['nom']}"
        # Requête 2 : ciblée sur les plateformes officielles
        if plateformes:
            site_q = " OR ".join(f"site:{s}" for s in plateformes[:4])
            q2 = f"appel d'offres {termes[0]} ({site_q})"
        else:
            q2 = None

        queries = [q for q in [q1, q2] if q]

        async with httpx.AsyncClient(timeout=20) as client:
            for q in queries:
                resp = await client.get("https://serpapi.com/search", params={
                    "engine": "google",
                    "q":      q,
                    "gl":     info["gl"],
                    "hl":     info["hl"],
                    "num":    10,
                    "tbs":    "qdr:m",   # résultats du dernier mois
                    "api_key": api_key,
                })
                if resp.status_code != 200:
                    continue
                data = resp.json()
                for r in data.get("organic_results", []):
                    url = r.get("link", "")
                    titre = r.get("title", "").strip()
                    if not titre or len(titre) < 8:
                        continue
                    # Identifier la plateforme officielle
                    source = next(
                        (p for p in plateformes if p in url),
                        "Appel d'offres"
                    )
                    marches.append({
                        "titre":       titre[:200],
                        "organisme":   _extraire_organisme(r.get("displayed_link", ""), r.get("snippet", "")),
                        "lieu":        info["nom"],
                        "resume":      (r.get("snippet", "") or "")[:500],
                        "url":         url,
                        "source":      source,
                        "date_pub":    r.get("date", "Récent"),
                        "secteur":     termes[0] if termes else "",
                    })
        return marches

    except Exception as e:
        logger.debug(f"[SchedulerMarches] SerpAPI erreur: {e}")
        return []


# ── Source 2 : dgMarket RSS ───────────────────────────────────────────────────
# World Bank / Banque africaine de développement procurement aggregator.
# URL RSS : https://www.dgmarket.com/rss-{ISO3}.xml

_ISO2_TO_ISO3 = {
    "CM": "CMR", "CI": "CIV", "SN": "SEN", "GA": "GAB", "BF": "BFA",
    "ML": "MLI", "TG": "TGO", "BJ": "BEN", "CD": "COD", "MG": "MDG",
    "RW": "RWA", "KE": "KEN", "NG": "NGA", "GH": "GHA", "ZA": "ZAF",
    "MA": "MAR", "TN": "TUN", "DZ": "DZA", "NE": "NER", "TD": "TCD",
    "FR": "FRA", "BE": "BEL", "CA": "CAN", "CH": "CHE",
}

async def _fetch_dgmarket(pays: str) -> list[dict]:
    iso3 = _ISO2_TO_ISO3.get(pays.upper(), "")
    if not iso3:
        return []
    try:
        import httpx
        import xml.etree.ElementTree as ET

        url = f"https://www.dgmarket.com/rss-{iso3}.xml"
        async with httpx.AsyncClient(timeout=15, follow_redirects=True) as client:
            resp = await client.get(url, headers={"User-Agent": "YukpoBot/2.0"})
        if resp.status_code != 200:
            return []

        root = ET.fromstring(resp.text)
        items = root.findall(".//item")
        marches = []
        for item in items[:10]:
            def g(tag):
                el = item.find(tag)
                return (el.text or "").strip() if el is not None else ""

            titre = g("title")
            if not titre:
                continue
            marches.append({
                "titre":     titre[:200],
                "organisme": g("author") or "Procurement notice",
                "lieu":      pays,
                "resume":    re.sub(r"<[^>]+>", " ", g("description"))[:500],
                "url":       g("link"),
                "source":    "dgMarket (Banque Mondiale)",
                "date_pub":  g("pubDate")[:20],
                "secteur":   "",
            })
        return marches
    except Exception as e:
        logger.debug(f"[SchedulerMarches] dgMarket erreur: {e}")
        return []


# ── Source 3 : UNGM ───────────────────────────────────────────────────────────
# UN Global Marketplace — appels d'offres ONU/agences onusiennes.

async def _fetch_ungm(termes: list[str]) -> list[dict]:
    try:
        import httpx
        q = urllib.parse.quote(" ".join(termes[:2]))
        url = f"https://www.ungm.org/Public/Notice?filter=%7B%22Keywords%22%3A%22{q}%22%7D"
        # UNGM expose une API JSON pour les notices
        api_url = f"https://www.ungm.org/Public/Notice/Search?keywords={q}&pageSize=10&pageIndex=0"
        async with httpx.AsyncClient(timeout=15, follow_redirects=True) as client:
            resp = await client.get(api_url, headers={
                "Accept": "application/json",
                "User-Agent": "YukpoBot/2.0",
            })
        if resp.status_code != 200:
            return []

        data = resp.json()
        notices = data.get("noticeList", data if isinstance(data, list) else [])
        marches = []
        for n in notices[:8]:
            titre = n.get("Title", n.get("title", "")).strip()
            if not titre:
                continue
            notice_id = n.get("NoticeId", n.get("id", ""))
            marches.append({
                "titre":     titre[:200],
                "organisme": n.get("AgencyName", n.get("agency", "Agence ONU")),
                "lieu":      n.get("CountryName", "International"),
                "resume":    (n.get("Description", n.get("description", "")) or "")[:500],
                "url":       f"https://www.ungm.org/Public/Notice/{notice_id}" if notice_id else "",
                "source":    "UNGM (Nations Unies)",
                "date_pub":  str(n.get("DeadlineDate", n.get("deadline", "Récent")))[:20],
                "secteur":   n.get("UNSPSCDescription", ""),
            })
        return marches
    except Exception as e:
        logger.debug(f"[SchedulerMarches] UNGM erreur: {e}")
        return []


# ── Sauvegarde DB ─────────────────────────────────────────────────────────────

async def _sauvegarder_marches(user_id: int, marches: list[dict]):
    try:
        from core.database import async_session_maker
        from modules.pro.profil_pro import ProfilProfessionnelDB
        from sqlalchemy import update

        now = datetime.now(timezone.utc)
        async with async_session_maker() as db:
            await db.execute(
                update(ProfilProfessionnelDB)
                .where(ProfilProfessionnelDB.user_id == user_id)
                .values(
                    marches_publics_recents=marches,
                    derniere_recherche_marches=now,
                )
            )
            await db.commit()
        logger.info(f"[SchedulerMarches] {len(marches)} avis sauvegardés pour user {user_id}")
    except Exception as e:
        logger.error(f"[SchedulerMarches] Erreur sauvegarde: {e}")


# ── Helpers ───────────────────────────────────────────────────────────────────

def _extraire_organisme(displayed_link: str, snippet: str) -> str:
    """Tente d'extraire le nom de l'organisme depuis les résultats Google."""
    # Souvent dans le snippet : "Le ministère de X lance un appel..."
    m = re.search(r"(minist[eè]re|direction|agence|office|commune|région|mairie)\s+[^\.,]{3,40}", snippet, re.IGNORECASE)
    if m:
        return m.group(0).strip()[:80]
    # Fallback : domaine
    m2 = re.search(r"([a-z0-9\-]+\.[a-z]{2,4})", displayed_link)
    return m2.group(1) if m2 else "Organisme public"
