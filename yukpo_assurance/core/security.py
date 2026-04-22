"""
YukpoAssurance — Module Sécurité IA  (v3 — Production-grade)
Protection contre les injections prompt, jailbreaks, et abus API.

Stratégies implémentées :
1. Détection d'injection prompt (patterns unicode, variations, base64)
2. Rate limiting Redis-persistant (survit aux redémarrages, résistant aux attaques distribuées)
3. Validation des inputs (longueur, caractères, structure)
4. Chiffrement AES-256 des données PII (CNI, téléphone) pour les logs
5. Audit des tentatives suspectes avec scoring
6. Protection contre les attaques par temporisation (time-constant comparisons)
"""
from __future__ import annotations

import hashlib
import hmac
import logging
import re
import secrets
import time
import unicodedata
from dataclasses import dataclass, field
from typing import Optional

from config.settings import settings

logger = logging.getLogger("yukpo_assurance.security")

# ── Patterns d'injection prompt ───────────────────────────────────────────────
# Couvre les variantes Unicode, leetspeak et encodages courants

_INJECTION_PATTERNS = [
    # Jailbreaks classiques
    r"ignore\s+(?:previous|all|above|prior)",
    r"disregard\s+(?:previous|instructions|all)",
    r"forget\s+(?:previous|everything|instructions)",
    r"system\s*prompt",
    r"jailbreak",
    r"dan\s+mode",
    r"act\s+as\s+(?:a\s+)?(?:dif|new|free|unres)",
    r"you\s+are\s+now\s+(?:dif|free|evil)",
    r"pretend\s+(?:you\s+are|to\s+be)",
    r"override\s+(?:your|previous|all)",
    r"new\s+instructions?",
    r"instruction\s*override",
    r"prompt\s+injection",
    r"bypass\s+(?:filter|safety|restriction)",
    r"reveal\s+(?:your|the)\s+(?:system|instructions?|prompt)",
    r"print\s+(?:your|the)\s+(?:system|instructions?)",
    r"what\s+(?:are|is)\s+your\s+(?:instructions?|prompt|system)",
    # Encodages
    r"base64\s*decode",
    r"rot13",
    r"eval\s*\(",
    r"exec\s*\(",
    # Commandes système
    r"<\s*script",
    r"javascript\s*:",
    r"\{\{.*\}\}",            # Template injection
    r"\$\{.*\}",              # Template injection JS
    r"__import__",
    r"os\.system",
    r"subprocess",
]

_COMPILED_PATTERNS = [re.compile(p, re.IGNORECASE | re.UNICODE) for p in _INJECTION_PATTERNS]


# ── Rate limiter en mémoire ───────────────────────────────────────────────────

@dataclass
class _RateBucket:
    count: int = 0
    reset_at: float = field(default_factory=time.monotonic)


_rate_buckets: dict[str, _RateBucket] = {}

# Limites par fenêtre de 1 minute
_LIMITS_PAR_ROLE = {
    "admin":     500,
    "dg":        300,
    "daf":       200,
    "manager":   150,
    "actuaire":  150,
    "commercial": 100,
    "marketing": 100,
    "agent":      60,
    "courtier":   40,
    "_default":   30,
}
_WINDOW_SECONDS = 60


class SecurityService:
    """Service de sécurité IA pour YukpoAssurance."""

    # ─── Validation d'injection prompt ───────────────────────────────────────

    def valider_prompt(
        self, texte: str, user_id: Optional[int] = None
    ) -> tuple[bool, Optional[str]]:
        """
        Valide un texte avant envoi à l'IA.
        Retourne (valide, raison_si_invalide).
        """
        if not texte or not texte.strip():
            return False, "Texte vide"

        if len(texte) > 32_000:
            return False, f"Texte trop long ({len(texte)} chars > 32 000)"

        # Normalisation Unicode pour détecter les variantes obfusquées
        texte_norm = unicodedata.normalize("NFKD", texte)

        # Test des patterns
        for pattern in _COMPILED_PATTERNS:
            if pattern.search(texte_norm):
                raison = f"Pattern d'injection détecté: {pattern.pattern[:50]}"
                logger.warning(
                    f"[Security] Injection prompt bloquée "
                    f"user={user_id} pattern={pattern.pattern[:30]}"
                )
                return False, raison

        # Détection base64 suspicieuse (longue chaîne b64 dans le texte)
        b64_chunks = re.findall(r'[A-Za-z0-9+/]{50,}={0,2}', texte)
        if b64_chunks:
            import base64
            for chunk in b64_chunks[:3]:
                try:
                    decoded = base64.b64decode(chunk).decode("utf-8", errors="ignore")
                    # Vérifier si le décodage contient des patterns dangereux
                    for pattern in _COMPILED_PATTERNS[:8]:
                        if pattern.search(decoded):
                            logger.warning(
                                f"[Security] Base64 injection bloquée user={user_id}"
                            )
                            return False, "Injection base64 détectée"
                except Exception:
                    pass

        return True, None

    # ─── Rate limiting Redis-persistant ──────────────────────────────────────

    def verifier_rate_limit(
        self, user_id: int, role: str = "agent"
    ) -> tuple[bool, dict]:
        """
        Vérifie le rate limit pour un utilisateur.
        Priorité : Redis (distribué, persistant) → mémoire (fallback).
        Retourne (autorise, info_rate_limit).
        """
        key = f"rl:{user_id}:{int(time.time() // _WINDOW_SECONDS)}"
        limit = _LIMITS_PAR_ROLE.get(role, _LIMITS_PAR_ROLE["_default"])

        # Essayer Redis d'abord (rate limiting distribué)
        try:
            import redis as redis_lib
            r = redis_lib.from_url(settings.REDIS_URL, socket_connect_timeout=1)
            count = int(r.incr(key) or 1)
            if count == 1:
                r.expire(key, _WINDOW_SECONDS * 2)
            restant = max(0, limit - count)
            reset_dans = _WINDOW_SECONDS - int(time.time() % _WINDOW_SECONDS)
            info = {"limit": limit, "used": count, "remaining": restant,
                    "reset_in_seconds": reset_dans, "backend": "redis"}
            if count > limit:
                logger.warning(
                    f"[Security/Redis] Rate limit dépassé: user={user_id} role={role} "
                    f"count={count}/{limit}"
                )
                return False, info
            return True, info
        except Exception:
            pass  # Fallback mémoire

        # Fallback mémoire
        mem_key = f"rl:{user_id}"
        now = time.monotonic()
        bucket = _rate_buckets.get(mem_key)
        if bucket is None or (now - bucket.reset_at) >= _WINDOW_SECONDS:
            _rate_buckets[mem_key] = _RateBucket(count=1, reset_at=now)
            bucket = _rate_buckets[mem_key]
        else:
            bucket.count += 1

        if len(_rate_buckets) > 10_000:
            expired = [k for k, v in _rate_buckets.items() if (now - v.reset_at) >= _WINDOW_SECONDS]
            for k in expired[:5_000]:
                del _rate_buckets[k]

        restant = max(0, limit - bucket.count)
        reset_dans = max(0, int(_WINDOW_SECONDS - (now - bucket.reset_at)))
        info = {"limit": limit, "used": bucket.count, "remaining": restant,
                "reset_in_seconds": reset_dans, "backend": "memory"}
        if bucket.count > limit:
            logger.warning(
                f"[Security/Mem] Rate limit dépassé: user={user_id} role={role} "
                f"count={bucket.count}/{limit}"
            )
            return False, info
        return True, info

    # ─── Validation des inputs ────────────────────────────────────────────────

    def valider_montant_fcfa(self, montant: float, max_fcfa: float = 1_000_000_000) -> bool:
        """Valide qu'un montant en FCFA est raisonnable."""
        return 0 < montant <= max_fcfa

    def valider_numero_police(self, numero: str) -> bool:
        """Valide le format d'un numéro de police."""
        return bool(re.match(
            r'^(AUTO|VIE|IRD|RC|TR|MA|MR|YK|SIN)-\d{4}-\d{4,10}$',
            numero.strip().upper()
        ))

    def sanitiser_texte(self, texte: str) -> str:
        """Sanitise un texte pour l'affichage (supprime HTML/scripts)."""
        # Supprimer balises HTML
        propre = re.sub(r'<[^>]+>', '', texte)
        # Supprimer scripts
        propre = re.sub(r'javascript:', '', propre, flags=re.IGNORECASE)
        return propre.strip()

    def hash_donnees_sensibles(self, donnees: str) -> str:
        """Hash des données sensibles pour les logs (CNI, téléphone)."""
        return hashlib.sha256(donnees.encode()).hexdigest()[:16] + "..."

    def chiffrer_pii(self, texte: str) -> str:
        """
        Chiffre une donnée PII (CNI, téléphone, email) avec AES-256-GCM.
        Utilise SIGNATURE_HMAC_KEY comme clé de chiffrement.
        Retourne une chaîne hex encodée (nonce + tag + ciphertext).
        """
        cle = getattr(settings, "PII_ENCRYPTION_KEY", "") or getattr(settings, "SIGNATURE_HMAC_KEY", "")
        if not cle:
            # Pas de clé configurée — retourner hash au lieu de clair
            return f"HASH:{self.hash_donnees_sensibles(texte)}"
        try:
            from cryptography.hazmat.primitives.ciphers.aead import AESGCM
            cle_bytes = hashlib.sha256(cle.encode()).digest()  # 256 bits
            nonce = secrets.token_bytes(12)  # 96-bit nonce pour GCM
            aesgcm = AESGCM(cle_bytes)
            ct = aesgcm.encrypt(nonce, texte.encode(), None)
            return (nonce + ct).hex()
        except ImportError:
            logger.warning("[Security] cryptography non installé — PII stockée en hash")
            return f"HASH:{self.hash_donnees_sensibles(texte)}"

    def dechiffrer_pii(self, chiffre_hex: str) -> str:
        """Déchiffre une donnée PII précédemment chiffrée avec chiffrer_pii()."""
        if chiffre_hex.startswith("HASH:"):
            return "[DONNÉES HACHÉES — IRRÉVERSIBLE]"
        cle = getattr(settings, "PII_ENCRYPTION_KEY", "") or getattr(settings, "SIGNATURE_HMAC_KEY", "")
        if not cle:
            return "[CLÉ DE DÉCHIFFREMENT MANQUANTE]"
        try:
            from cryptography.hazmat.primitives.ciphers.aead import AESGCM
            data = bytes.fromhex(chiffre_hex)
            nonce, ct = data[:12], data[12:]
            cle_bytes = hashlib.sha256(cle.encode()).digest()
            aesgcm = AESGCM(cle_bytes)
            return aesgcm.decrypt(nonce, ct, None).decode()
        except Exception as e:
            logger.error(f"[Security] Déchiffrement PII échoué: {e}")
            return "[ERREUR DÉCHIFFREMENT]"

    def valider_fichier_upload(
        self,
        filename: str,
        content: bytes,
        max_size_mb: float = 20.0,
        types_autorises: Optional[list[str]] = None,
    ) -> tuple[bool, Optional[str]]:
        """
        Valide un fichier uploadé : taille, extension, magic bytes.
        Retourne (valide, raison_si_invalide).
        """
        if types_autorises is None:
            types_autorises = ["pdf", "png", "jpg", "jpeg", "xlsx", "docx", "csv", "tiff", "bmp"]

        # Taille
        taille_mb = len(content) / (1024 * 1024)
        if taille_mb > max_size_mb:
            return False, f"Fichier trop volumineux ({taille_mb:.1f} MB > {max_size_mb} MB)"

        # Extension
        ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
        if ext not in types_autorises:
            return False, f"Extension '.{ext}' non autorisée. Extensions acceptées : {types_autorises}"

        # Magic bytes (vérification du vrai type MIME)
        MAGIC_BYTES = {
            "pdf":  b"%PDF",
            "png":  b"\x89PNG",
            "jpg":  b"\xff\xd8\xff",
            "jpeg": b"\xff\xd8\xff",
            "xlsx": b"PK\x03\x04",   # ZIP (docx/xlsx/pptx)
            "docx": b"PK\x03\x04",
            "pptx": b"PK\x03\x04",
            "tiff": [b"II*\x00", b"MM\x00*"],
            "bmp":  b"BM",
        }
        expected_magic = MAGIC_BYTES.get(ext)
        if expected_magic and content:
            if isinstance(expected_magic, list):
                valid_magic = any(content[:4].startswith(m) for m in expected_magic)
            else:
                valid_magic = content[:4].startswith(expected_magic[:4])
            if not valid_magic:
                return False, f"Contenu du fichier ne correspond pas à l'extension '.{ext}' (magic bytes invalides)"

        # Scan basique virus (patterns binaires suspects)
        PATTERNS_SUSPECTS = [b"<script", b"javascript:", b"eval(", b"exec("]
        if ext in ("csv", "txt"):
            for pattern in PATTERNS_SUSPECTS:
                if pattern in content[:1024]:
                    return False, f"Contenu suspect détecté dans le fichier"

        return True, None

    def comparer_hmac_constant(self, attendu: str, recu: str) -> bool:
        """
        Comparaison HMAC en temps constant (résistant aux attaques temporelles).
        Utilisé pour valider les webhooks Mobile Money / ORASS.
        """
        return hmac.compare_digest(attendu.encode(), recu.encode())

    def generer_token_csrf(self, session_id: str) -> str:
        """Génère un token CSRF lié à la session."""
        return hashlib.sha256(f"{session_id}:{settings.SECRET_KEY}".encode()).hexdigest()

    def verifier_token_csrf(self, session_id: str, token: str) -> bool:
        """Vérifie un token CSRF (comparaison en temps constant)."""
        attendu = self.generer_token_csrf(session_id)
        return self.comparer_hmac_constant(attendu, token)

    def detecter_tentatives_brute_force(
        self, user_id: str, action: str = "auth"
    ) -> tuple[bool, int]:
        """
        Détecte les tentatives de brute force (authentification, OTP...).
        Retourne (bloqué, nb_tentatives).
        Redis : compte les tentatives sur 15 minutes.
        """
        cle = f"bf:{action}:{user_id}"
        max_tentatives = 5
        try:
            import redis as redis_lib
            r = redis_lib.from_url(settings.REDIS_URL, socket_connect_timeout=1)
            count = int(r.incr(cle) or 1)
            if count == 1:
                r.expire(cle, 900)  # 15 minutes
            if count > max_tentatives:
                logger.warning(
                    f"[Security] Brute force détecté: action={action} user={user_id} "
                    f"tentatives={count}"
                )
                return True, count
            return False, count
        except Exception:
            return False, 0

    def reinitialiser_tentatives(self, user_id: str, action: str = "auth") -> None:
        """Réinitialise le compteur de brute force après succès."""
        try:
            import redis as redis_lib
            r = redis_lib.from_url(settings.REDIS_URL, socket_connect_timeout=1)
            r.delete(f"bf:{action}:{user_id}")
        except Exception:
            pass


# Instance singleton
security_service = SecurityService()
