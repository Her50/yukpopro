"""
YukpoAssurance — Détecteur de fraude sinistres
Score de risque 0-100 + indicateurs détectés + recommandations.
"""
import logging
from datetime import date, timedelta
from typing import Optional

from core.ia_client import ModeIA, ia_client
from core.orchestrateur import ContexteRequete, DomaineMétier, orchestrateur

logger = logging.getLogger("yukpo_assurance.sinistres.fraude")

# Indicateurs de fraude connus (règles métier)
INDICATEURS_FRAUDE = {
    "sinistre_post_souscription_recente": {
        "seuil_jours": 30,
        "poids": 25,
        "description": "Sinistre déclaré moins de 30 jours après la souscription",
    },
    "multi_reclamant": {
        "seuil_sinistres": 3,
        "periode_mois": 24,
        "poids": 20,
        "description": "Plus de 3 sinistres sur 24 mois",
    },
    "montant_anormal": {
        "ratio_alerte": 3.0,
        "poids": 20,
        "description": "Montant déclaré > 3x la valeur vénale estimée",
    },
    "garage_non_reference": {
        "poids": 15,
        "description": "Garage émetteur de la facture non référencé dans ORASS",
    },
    "incoherence_date_heure": {
        "poids": 15,
        "description": "Incohérence entre date/heure du sinistre et les faits déclarés",
    },
    "tiers_identique_sinistres_precedents": {
        "poids": 20,
        "description": "Les mêmes tiers impliqués dans plusieurs sinistres",
    },
    "declaration_tardive_sans_justification": {
        "seuil_jours": 15,
        "poids": 10,
        "description": "Déclaration plus de 15 jours après le sinistre sans justification",
    },
    "photos_metadata_incoherentes": {
        "poids": 20,
        "description": "Métadonnées photos incohérentes avec lieu/date déclarés",
    },
}


class FraudeDetector:
    """
    Détecteur de fraude sinistres à double couche :
    1. Règles métier déterministes (rapides, sans IA)
    2. Analyse IA des incohérences sémantiques et des photos
    """

    async def analyser(
        self,
        declaration,
        historique_police: list,
        pre_rapport: Optional[dict] = None,
    ) -> dict:
        """
        Analyse complète de fraude.
        Retourne un score 0-100 et la liste des indicateurs déclenchés.
        """
        indicateurs_declenches = []
        score_base = 0

        # ── Règles déterministes ──────────────────────────────────

        # 1. Sinistre post-souscription récente (< 30 jours)
        contrat = await self._recuperer_contrat(declaration.numero_police)
        if contrat:
            date_effet = contrat.date_effet
            if isinstance(date_effet, str):
                from datetime import datetime
                date_effet = datetime.fromisoformat(date_effet).date()
            delai = (declaration.date_sinistre - date_effet).days
            seuil = INDICATEURS_FRAUDE["sinistre_post_souscription_recente"]["seuil_jours"]
            if delai < seuil:
                poids = INDICATEURS_FRAUDE["sinistre_post_souscription_recente"]["poids"]
                score_base += poids
                indicateurs_declenches.append({
                    "indicateur": "sinistre_post_souscription_recente",
                    "poids": poids,
                    "detail": f"Sinistre survenu {delai} jours après la souscription (seuil: {seuil}j)",
                })

        # 2. Multi-réclamant
        nb_sinistres_recents = len([
            s for s in historique_police
            if hasattr(s, "date_sinistre")
            and (declaration.date_sinistre - s.date_sinistre).days <= 730
        ])
        seuil_multi = INDICATEURS_FRAUDE["multi_reclamant"]["seuil_sinistres"]
        if nb_sinistres_recents >= seuil_multi:
            poids = INDICATEURS_FRAUDE["multi_reclamant"]["poids"]
            score_base += poids
            indicateurs_declenches.append({
                "indicateur": "multi_reclamant",
                "poids": poids,
                "detail": f"{nb_sinistres_recents} sinistres sur les 24 derniers mois",
            })

        # 3. Déclaration tardive
        delai_declaration = (date.today() - declaration.date_sinistre).days
        seuil_tardif = INDICATEURS_FRAUDE["declaration_tardive_sans_justification"]["seuil_jours"]
        if delai_declaration > seuil_tardif:
            poids = INDICATEURS_FRAUDE["declaration_tardive_sans_justification"]["poids"]
            score_base += poids
            indicateurs_declenches.append({
                "indicateur": "declaration_tardive",
                "poids": poids,
                "detail": f"Déclaration {delai_declaration} jours après le sinistre",
            })

        # 4. Incohérence photo/pré-rapport IA
        if pre_rapport and not pre_rapport.get("coherence_avec_declaration", True):
            anomalies = pre_rapport.get("anomalies_detectees", [])
            if anomalies:
                poids = INDICATEURS_FRAUDE["incoherence_date_heure"]["poids"]
                score_base += poids
                indicateurs_declenches.append({
                    "indicateur": "incoherence_declaration_photos",
                    "poids": poids,
                    "detail": f"Anomalies IA : {', '.join(anomalies)}",
                })

        # ── Analyse IA sémantique ─────────────────────────────────
        analyse_ia = await self._analyse_ia_fraude(declaration, indicateurs_declenches)
        score_ia = analyse_ia.get("score_supplementaire", 0)

        score_final = min(100, score_base + score_ia)

        return {
            "score_fraude": score_final,
            "niveau_risque": self._niveau_risque(score_final),
            "indicateurs_declenches": indicateurs_declenches,
            "analyse_ia": analyse_ia.get("observations", ""),
            "recommandation": self._recommandation(score_final),
            "nb_sinistres_historique": nb_sinistres_recents,
        }

    async def _analyse_ia_fraude(self, declaration, indicateurs_deja_detectes: list) -> dict:
        """Couche IA — détection d'incohérences sémantiques complexes"""
        prompt = f"""
Tu es expert en détection de fraude pour une compagnie d'assurance en zone CIMA.

Analyse cette déclaration de sinistre pour détecter des signaux de fraude :

- Police : {declaration.numero_police}
- Date sinistre : {declaration.date_sinistre}
- Heure : {declaration.heure_sinistre or "non précisée"}
- Lieu : {declaration.lieu}
- Nature : {declaration.nature}
- Description : {declaration.description}
- Blessés : {declaration.blesses}
- Nombre de tiers : {len(declaration.tiers_impliques)}
- Canal de déclaration : {declaration.canal}

Indicateurs déjà détectés par les règles automatiques : {indicateurs_deja_detectes}

Analyse :
1. La description est-elle cohérente et précise ?
2. Y a-t-il des détails suspects ou contradictoires ?
3. Le timing (heure, lieu, circonstances) est-il plausible ?
4. Des éléments suggèrent-ils une mise en scène ?

Retourne UNIQUEMENT ce JSON :
{{
  "score_supplementaire": 0,
  "observations": "analyse détaillée",
  "signaux_semantiques": ["liste des signaux détectés"],
  "points_positifs": ["éléments qui plaident pour l'authenticité"],
  "verdict_ia": "authentique|suspect|frauduleux"
}}
"""
        reponse = await ia_client.appeler(
            prompt=prompt,
            mode=ModeIA.ANALYSE,
            json_attendu=True,
        )
        return reponse.as_json()

    async def _recuperer_contrat(self, numero_police: str):
        try:
            return await __import__(
                "core.orass_connector", fromlist=["orass"]
            ).orass.rechercher_contrat(numero_police=numero_police)
        except Exception:
            return None

    def _calcul_score_deterministe(self, donnees: dict) -> int:
        """
        Calcul rapide du score de fraude à partir d'un dict de données brutes.
        Utilisé pour pré-filtrage sans appel IA.
        """
        score = 0

        # Heure suspecte (minuit → 5h)
        heure = donnees.get("heure_sinistre", "")
        if heure:
            try:
                h = int(heure.split(":")[0])
                if 0 <= h <= 5:
                    score += 15
            except (ValueError, IndexError):
                pass

        # Montant élevé (> 5 000 000 FCFA)
        montant = donnees.get("montant_declare", 0)
        if montant > 5_000_000:
            score += 20

        # Sinistres multiples dans l'historique
        historique = donnees.get("historique_sinistres_client", 0)
        if historique >= 5:
            score += 25
        elif historique >= 3:
            score += 15

        # Nature suspecte (vol, incendie)
        if donnees.get("nature", "") in ("vol", "incendie"):
            score += 10

        # Pièces manquantes
        pieces = donnees.get("pieces_fournies", [])
        if len(pieces) == 0:
            score += 15

        # Déclaration tardive (> 15 jours)
        from datetime import date
        try:
            date_sin = donnees.get("date_sinistre")
            if date_sin:
                if isinstance(date_sin, str):
                    from datetime import datetime
                    date_sin = datetime.fromisoformat(date_sin).date()
                delai = (date.today() - date_sin).days
                if delai > 15:
                    score += 10
        except Exception:
            pass

        return min(100, score)

    def _niveau_risque(self, score: int) -> str:
        if score >= 80:
            return "critique"
        if score >= 60:
            return "élevé"
        if score >= 40:
            return "modéré"
        if score >= 20:
            return "faible"
        return "très faible"

    def _recommandation(self, score: int) -> str:
        if score >= 70:
            return "Bloquer le règlement — escalader au service anti-fraude immédiatement"
        if score >= 40:
            return "Investigation complémentaire requise avant tout règlement"
        if score >= 20:
            return "Traitement normal avec vigilance — vérifier les pièces justificatives"
        return "Dossier sans signal particulier — traitement standard"

    async def analyser_metadonnees_photo(
        self,
        image_b64: str,
        date_sinistre_declaree: "date",
        lieu_sinistre_declare: str,
    ) -> dict:
        """
        Analyse les métadonnées EXIF d'une photo pour détecter des incohérences.
        Retourne les anomalies détectées (date, GPS, logiciel de retouche...).
        """
        import base64
        import io

        anomalies = []
        resultats = {"anomalies": anomalies, "score_supplementaire": 0}

        try:
            from PIL import Image
            from PIL.ExifTags import TAGS, GPSTAGS

            img_bytes = base64.b64decode(image_b64)
            img = Image.open(io.BytesIO(img_bytes))
            exif_data = img._getexif() or {}

            exif_readable = {}
            for tag_id, value in exif_data.items():
                tag = TAGS.get(tag_id, tag_id)
                exif_readable[tag] = value

            # 1. Vérification date EXIF vs date déclarée
            date_exif_str = exif_readable.get("DateTime") or exif_readable.get("DateTimeOriginal")
            if date_exif_str:
                try:
                    from datetime import datetime as _dt
                    date_exif = _dt.strptime(str(date_exif_str)[:10], "%Y:%m:%d").date()
                    ecart_jours = abs((date_exif - date_sinistre_declaree).days)
                    if ecart_jours > 3:
                        anomalies.append(
                            f"Date photo EXIF ({date_exif}) ≠ date sinistre déclarée "
                            f"({date_sinistre_declaree}) — écart {ecart_jours} jours"
                        )
                        resultats["score_supplementaire"] += 25
                except Exception:
                    pass

            # 2. Détection logiciel de retouche (Photoshop, GIMP...)
            software = str(exif_readable.get("Software", "")).lower()
            retouche_logiciels = ["photoshop", "gimp", "lightroom", "pixelmator", "affinity"]
            if any(s in software for s in retouche_logiciels):
                anomalies.append(
                    f"Image potentiellement retouchée (logiciel détecté: {software})"
                )
                resultats["score_supplementaire"] += 30

            # 3. GPS : vérification géographique basique
            gps_info_raw = exif_readable.get("GPSInfo")
            if gps_info_raw:
                gps = {}
                for key, val in gps_info_raw.items():
                    gps[GPSTAGS.get(key, key)] = val
                resultats["gps_detecte"] = True
                resultats["gps_raw"] = {k: str(v) for k, v in list(gps.items())[:6]}
            else:
                # Absence GPS sur smartphone moderne = légèrement suspect
                anomalies.append("Aucune donnée GPS dans la photo (localisation non vérifiable)")
                resultats["score_supplementaire"] += 5

            # 4. Absence totale de métadonnées (image "nettoyée")
            if not exif_data:
                anomalies.append(
                    "Métadonnées EXIF absentes — image possiblement nettoyée avant envoi"
                )
                resultats["score_supplementaire"] += 15

        except ImportError:
            logger.info("[Fraude] PIL non installé — analyse EXIF désactivée")
        except Exception as e:
            logger.warning(f"[Fraude] Analyse EXIF échouée: {e}")

        resultats["nb_anomalies"] = len(anomalies)
        resultats["score_supplementaire"] = min(50, resultats["score_supplementaire"])
        return resultats


# Singleton
fraude_detector = FraudeDetector()
