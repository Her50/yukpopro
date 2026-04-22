"""
Community Manager IA — YukpoAssurance
Inspiré du Social AI Engine de yukpomnang2, adapté pour les compagnies d'assurance.

Fonctionnalités :
- Génération IA de posts sectoriels (assurance, banque, santé, etc.)
- A/B testing automatique de légendes
- Scheduler de publications
- Analytics et tracking engagement
- Auto-drafts depuis les tendances de marché
- Configuration voix de marque par compagnie
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional


# ─────────────────────────────────────────────────────────────
# Contexte de génération
# ─────────────────────────────────────────────────────────────

@dataclass
class ContexteContenu:
    """Contexte métier pour générer un post pertinent."""
    type_contenu: str           # produit | promo | actualite | conseil | sinistre | campagne
    sujet: str                  # ex: "Assurance Auto RC — offre spéciale ramadan"
    plateforme: str             # facebook | instagram | linkedin | twitter | whatsapp | tiktok
    ton: str = "professionnel"  # professionnel | decontracte | promotionnel | urgent
    langue: str = "fr"
    inject_trend: Optional[str] = None   # tendance à injecter dans le post
    inclure_cta: bool = True             # Call To Action
    max_caracteres: Optional[int] = None
    hashtags_supplementaires: List[str] = field(default_factory=list)


@dataclass
class PostGenere:
    """Résultat d'une génération de post."""
    legende: str
    legende_variante_b: Optional[str]
    hashtags: List[str]
    ton: str
    plateforme: str
    type_contenu: str
    modele_utilise: str
    prompt_utilise: str


# ─────────────────────────────────────────────────────────────
# Prompts sectoriels
# ─────────────────────────────────────────────────────────────

PROMPTS_SECTEURS: Dict[str, str] = {
    "assurance": (
        "Tu es le Community Manager d'une compagnie d'assurance en Afrique (zone CIMA). "
        "Tu crées du contenu engageant, éducatif et professionnel sur l'assurance. "
        "Tu respectes la réglementation CIMA et ne fais pas de promesses non conformes."
    ),
    "banque": (
        "Tu es le Community Manager d'une banque en Afrique centrale et de l'ouest. "
        "Tu crées du contenu sur les services bancaires, l'épargne, les crédits et l'inclusion financière. "
        "Tu respectes les règles COBAC et les bonnes pratiques bancaires."
    ),
    "microfinance": (
        "Tu es le Community Manager d'une institution de microfinance en Afrique. "
        "Tu crées du contenu accessible sur l'épargne, le crédit, et l'entrepreneuriat. "
        "Ton audience est composée de petits entrepreneurs et de ménages à revenus modestes."
    ),
    "sante": (
        "Tu es le Community Manager d'un établissement de santé en Afrique. "
        "Tu crées du contenu de sensibilisation, de prévention et d'information médicale. "
        "Tu adoptes un ton bienveillant et rassurant."
    ),
    "ecole": (
        "Tu es le Community Manager d'un établissement scolaire ou universitaire en Afrique. "
        "Tu crées du contenu sur la pédagogie, les résultats, les événements et l'orientation."
    ),
    "immobilier": (
        "Tu es le Community Manager d'une agence immobilière en Afrique. "
        "Tu crées du contenu sur les biens disponibles, les conseils d'investissement immobilier "
        "et les tendances du marché."
    ),
    "transport": (
        "Tu es le Community Manager d'une entreprise de transport en Afrique. "
        "Tu crées du contenu sur les services, les tarifs, la sécurité et les nouveaux itinéraires."
    ),
    "cabinet_comptable": (
        "Tu es le Community Manager d'un cabinet d'expertise comptable en Afrique. "
        "Tu crées du contenu sur la fiscalité, la comptabilité OHADA, et les conseils aux entreprises."
    ),
    "industrie": (
        "Tu es le Community Manager d'une entreprise industrielle en Afrique. "
        "Tu crées du contenu sur les produits, l'innovation, la qualité et le développement local."
    ),
    "commerce": (
        "Tu es le Community Manager d'une entreprise commerciale. "
        "Tu crées du contenu attrayant sur les produits, les promotions et les offres spéciales."
    ),
}

LIMITES_CARACTERES: Dict[str, int] = {
    "twitter": 280,
    "instagram": 2200,
    "facebook": 63206,
    "linkedin": 3000,
    "whatsapp": 1000,
    "tiktok": 2200,
}

HASHTAGS_PAR_SECTEUR: Dict[str, List[str]] = {
    "assurance": ["#Assurance", "#CIMA", "#Protection", "#Assurances", "#AfriqueAssurance"],
    "banque": ["#Banque", "#Finance", "#Épargne", "#Credit", "#BanqueAfrique"],
    "microfinance": ["#Microfinance", "#Entrepreneuriat", "#Inclusion", "#PME", "#Afrique"],
    "sante": ["#Santé", "#Prévention", "#Médecine", "#Santé", "#Afrique"],
    "ecole": ["#Éducation", "#École", "#Université", "#Formation", "#Avenir"],
    "immobilier": ["#Immobilier", "#Logement", "#Investissement", "#Propriété"],
    "transport": ["#Transport", "#Mobilité", "#Logistique", "#Voyage"],
    "cabinet_comptable": ["#Comptabilité", "#OHADA", "#Fiscalité", "#Conseil"],
    "industrie": ["#Industrie", "#Innovation", "#MadeInAfrica", "#Qualité"],
    "commerce": ["#Commerce", "#Promo", "#Shopping", "#BonPlan"],
}


# ─────────────────────────────────────────────────────────────
# Moteur de génération
# ─────────────────────────────────────────────────────────────

class MoteurCommunityManager:

    def __init__(
        self,
        claude_api_key: str = "",
        openai_api_key: str = "",
        secteur: str = "assurance",
    ):
        self.claude_api_key = claude_api_key
        self.openai_api_key = openai_api_key
        self.secteur = secteur

    def _system_prompt(self, prefs: Optional[dict] = None) -> str:
        base = PROMPTS_SECTEURS.get(self.secteur, PROMPTS_SECTEURS["assurance"])
        if prefs and prefs.get("voix_marque"):
            base += f"\n\nVoix de marque : {prefs['voix_marque']}"
        if prefs and prefs.get("toujours_inclure"):
            base += f"\nInclure toujours : {', '.join(prefs['toujours_inclure'])}"
        if prefs and prefs.get("mots_interdits"):
            base += f"\nMots interdits (à ne jamais utiliser) : {', '.join(prefs['mots_interdits'])}"
        return base

    def _construire_prompt(self, ctx: ContexteContenu) -> str:
        limites = LIMITES_CARACTERES.get(ctx.plateforme, 1000)
        if ctx.max_caracteres:
            limites = min(limites, ctx.max_caracteres)

        prompt = (
            f"Génère un post {ctx.ton} pour {ctx.plateforme.capitalize()} "
            f"sur le sujet : « {ctx.sujet} ».\n"
            f"Type de contenu : {ctx.type_contenu}.\n"
            f"Langue : {ctx.langue}.\n"
            f"Limite : {limites} caractères maximum.\n"
        )

        if ctx.inject_trend:
            prompt += f"Intègre subtilement la tendance actuelle : « {ctx.inject_trend} ».\n"

        if ctx.inclure_cta:
            prompt += "Inclus un appel à l'action clair à la fin.\n"

        prompt += (
            "\nRetourne un JSON avec :\n"
            "{\n"
            '  "legende": "texte principal du post",\n'
            '  "legende_b": "variante alternative A/B légèrement différente",\n'
            '  "hashtags": ["#tag1", "#tag2", "#tag3"],\n'
            '  "explication": "pourquoi ce contenu est pertinent"\n'
            "}"
        )
        return prompt

    async def generer_post(
        self,
        ctx: ContexteContenu,
        prefs: Optional[dict] = None,
    ) -> PostGenere:
        """Génère un post avec Claude (ou fallback sur template)."""
        system = self._system_prompt(prefs)
        user_prompt = self._construire_prompt(ctx)
        modele = "claude-opus-4-6"

        contenu_json = None

        # Tentative Claude
        if self.claude_api_key:
            try:
                import anthropic
                client = anthropic.AsyncAnthropic(api_key=self.claude_api_key)
                response = await client.messages.create(
                    model=modele,
                    max_tokens=800,
                    temperature=0.7,
                    system=system,
                    messages=[{"role": "user", "content": user_prompt}],
                )
                raw = response.content[0].text
                contenu_json = self._extraire_json(raw)
            except Exception as e:
                print(f"[CM] Claude erreur : {e}")

        # Fallback GPT-4o
        if not contenu_json and self.openai_api_key:
            try:
                from openai import AsyncOpenAI
                oai = AsyncOpenAI(api_key=self.openai_api_key)
                modele = "gpt-4o"
                resp = await oai.chat.completions.create(
                    model=modele,
                    temperature=0.7,
                    max_tokens=800,
                    messages=[
                        {"role": "system", "content": system},
                        {"role": "user", "content": user_prompt},
                    ],
                )
                raw = resp.choices[0].message.content or ""
                contenu_json = self._extraire_json(raw)
            except Exception as e:
                print(f"[CM] GPT-4o erreur : {e}")

        # Fallback template
        if not contenu_json:
            contenu_json = self._template_fallback(ctx)
            modele = "template"

        # Enrichir avec hashtags sectoriels
        hashtags = contenu_json.get("hashtags", [])
        hashtags_base = HASHTAGS_PAR_SECTEUR.get(self.secteur, [])
        for h in hashtags_base[:3]:
            if h not in hashtags:
                hashtags.append(h)
        for h in ctx.hashtags_supplementaires:
            if h not in hashtags:
                hashtags.append(h)

        if prefs and prefs.get("hashtags_defaut"):
            for h in prefs["hashtags_defaut"][:3]:
                if h not in hashtags:
                    hashtags.append(h)

        return PostGenere(
            legende=contenu_json.get("legende", ""),
            legende_variante_b=contenu_json.get("legende_b"),
            hashtags=hashtags[:15],
            ton=ctx.ton,
            plateforme=ctx.plateforme,
            type_contenu=ctx.type_contenu,
            modele_utilise=modele,
            prompt_utilise=user_prompt,
        )

    def _extraire_json(self, texte: str) -> Optional[dict]:
        """Extrait le JSON de la réponse IA."""
        texte = texte.strip()
        # Chercher un bloc JSON
        match = re.search(r"\{.*\}", texte, re.DOTALL)
        if match:
            try:
                return json.loads(match.group())
            except json.JSONDecodeError:
                pass
        # Essai direct
        try:
            return json.loads(texte)
        except json.JSONDecodeError:
            return None

    def _template_fallback(self, ctx: ContexteContenu) -> dict:
        """Template de fallback si l'IA n'est pas disponible."""
        templates = {
            "produit": f"Découvrez {ctx.sujet} ! 🛡️\nNous vous proposons une couverture adaptée à vos besoins. Contactez-nous dès aujourd'hui pour un devis gratuit.",
            "conseil": f"💡 Conseil {ctx.sujet}\nProtégez votre avenir avec la bonne couverture. Nos experts sont à votre disposition.",
            "promo": f"🎉 Offre spéciale — {ctx.sujet}\nProfitez de notre offre limitée ! Contactez-nous maintenant.",
            "actualite": f"📢 Actualité : {ctx.sujet}\nRestez informé des dernières nouvelles. Suivez notre page.",
            "campagne": f"📣 {ctx.sujet}\nEnsemble, protégeons ce qui compte le plus. Rejoignez-nous !",
        }
        legende = templates.get(ctx.type_contenu, templates["produit"])
        return {
            "legende": legende,
            "legende_b": legende.replace("Contactez-nous", "Appelez-nous"),
            "hashtags": HASHTAGS_PAR_SECTEUR.get(self.secteur, [])[:5],
        }

    async def generer_brouillon_depuis_trend(
        self,
        sujet_trend: str,
        score_opportunite: float,
        region: str,
        prefs: Optional[dict] = None,
    ) -> Dict[str, str]:
        """
        Génère des brouillons de posts sur toutes les plateformes
        à partir d'une tendance de marché détectée.
        """
        brouillons = {}
        plateformes = ["facebook", "instagram", "linkedin", "whatsapp"]

        for plateforme in plateformes:
            ctx = ContexteContenu(
                type_contenu="actualite",
                sujet=f"Tendance {region} : {sujet_trend}",
                plateforme=plateforme,
                ton="professionnel",
                inject_trend=sujet_trend,
            )
            try:
                post = await self.generer_post(ctx, prefs)
                brouillons[f"brouillon_{plateforme}"] = post.legende
            except Exception:
                brouillons[f"brouillon_{plateforme}"] = None

        return brouillons

    def calculer_meilleure_heure(
        self,
        plateforme: str,
        preferences: Optional[dict] = None,
    ) -> int:
        """Retourne l'heure optimale de publication (0-23) pour une plateforme."""
        heures_defaut = {
            "facebook": 12,
            "instagram": 18,
            "linkedin": 8,
            "twitter": 9,
            "whatsapp": 10,
            "tiktok": 19,
        }
        if preferences and preferences.get("heures_publication"):
            heures = preferences["heures_publication"]
            if heures:
                # Priorité selon plateforme
                if plateforme in ("linkedin",) and 8 in heures:
                    return 8
                if plateforme in ("instagram", "tiktok") and 18 in heures:
                    return 18
                return heures[0]
        return heures_defaut.get(plateforme, 12)
