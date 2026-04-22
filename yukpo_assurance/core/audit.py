"""
YukpoAssurance — Audit Trail
Enregistre chaque action : qui a fait quoi, quand, sur quel dossier.
Deux mécanismes complémentaires :
1. AuditMiddleware : intercepte toutes les requêtes HTTP API
2. AuditService : enregistrements métier fins (appelé depuis les modules)
"""
import logging
import time
from datetime import datetime
from typing import Optional

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response
from fastapi import Request

logger = logging.getLogger("yukpo_assurance.audit")

# Routes à ne pas auditer (santé, docs swagger)
_ROUTES_EXCLUES = {"/", "/health", "/docs", "/openapi.json", "/redoc", "/favicon.ico"}


class AuditMiddleware(BaseHTTPMiddleware):
    """
    Middleware FastAPI qui logue automatiquement chaque appel API.
    Lit les en-têtes X-User-ID et X-User-Nom envoyés par le frontend.
    """

    async def dispatch(self, request: Request, call_next) -> Response:
        if request.url.path in _ROUTES_EXCLUES or request.url.path.startswith("/static"):
            return await call_next(request)

        debut = time.monotonic()
        response = None
        erreur = None

        try:
            response = await call_next(request)
            return response
        except Exception as exc:
            erreur = str(exc)
            raise
        finally:
            duree = (time.monotonic() - debut) * 1000
            # Fire-and-forget — ne bloque pas la réponse
            try:
                await _enregistrer_requete(request, response, round(duree, 1), erreur)
            except Exception as e:
                logger.debug(f"[Audit] Log non critique échoué: {e}")


async def _enregistrer_requete(
    request: Request,
    response: Optional[Response],
    duree_ms: float,
    erreur: Optional[str],
) -> None:
    try:
        from core.database import async_session_maker, AuditLogDB

        module, action = _extraire_module_action(request.url.path, request.method)
        user_id_str = request.headers.get("X-User-ID")
        user_nom = request.headers.get("X-User-Nom", "Inconnu")
        resource_id = _extraire_resource_id(request.url.path)

        statut = response.status_code if response else 0
        succes = erreur is None and statut < 400

        async with async_session_maker() as db:
            log = AuditLogDB(
                user_id=int(user_id_str) if user_id_str and user_id_str.isdigit() else None,
                user_nom=user_nom,
                action=action,
                module=module,
                resource_type=_detecter_resource_type(request.url.path),
                resource_id=resource_id,
                ip_address=request.client.host if request.client else None,
                duree_ms=duree_ms,
                succes=succes,
                erreur=erreur,
                details={
                    "method": request.method,
                    "path": str(request.url.path),
                    "status": statut,
                },
            )
            db.add(log)
            await db.commit()
    except Exception as e:
        logger.debug(f"[Audit/middleware] {e}")


def _extraire_module_action(path: str, method: str) -> tuple[str, str]:
    """Ex: /api/v1/sinistres/declarer → ("sinistres", "declarer")"""
    parts = [p for p in path.split("/") if p]
    if len(parts) >= 3:
        module = parts[2]
        action_part = parts[3] if len(parts) > 3 else method.lower()
        return module, action_part
    return "system", method.lower()


def _extraire_resource_id(path: str) -> Optional[str]:
    """Extrait l'ID de ressource si présent dans le path"""
    parts = [p for p in path.split("/") if p]
    # /api/v1/sinistres/{id}/analyser → l'id est en position 3
    if len(parts) >= 4:
        candidate = parts[3]
        # Exclure les mots qui sont des sous-routes (pas des IDs)
        if candidate not in {"sessions", "actions", "tableau", "formats", "dashboard"}:
            return candidate
    return None


def _detecter_resource_type(path: str) -> Optional[str]:
    mapping = {
        "chat": "session",
        "sinistres": "sinistre",
        "reunions": "reunion",
        "documents": "document",
        "comptabilite": "piece_comptable",
        "analytics": "rapport",
        "cima": "etat_reglementaire",
    }
    parts = [p for p in path.split("/") if p]
    if len(parts) >= 3:
        return mapping.get(parts[2])
    return None


# ─── SERVICE D'AUDIT MÉTIER ───────────────────────────────────────────────────

class AuditService:
    """
    Service pour enregistrer des actions métier spécifiques depuis le code.
    Plus fin que le middleware : permet de lier une action à un dossier précis.
    """

    async def log(
        self,
        action: str,
        module: str,
        user_id: Optional[int] = None,
        user_nom: Optional[str] = None,
        resource_type: Optional[str] = None,
        resource_id: Optional[str] = None,
        details: Optional[dict] = None,
        succes: bool = True,
        erreur: Optional[str] = None,
    ) -> None:
        try:
            from core.database import async_session_maker, AuditLogDB
            async with async_session_maker() as db:
                log = AuditLogDB(
                    user_id=user_id,
                    user_nom=user_nom or "Système",
                    action=action,
                    module=module,
                    resource_type=resource_type,
                    resource_id=resource_id,
                    details=details,
                    succes=succes,
                    erreur=erreur,
                )
                db.add(log)
                await db.commit()
        except Exception as e:
            logger.warning(f"[Audit/service] log échoué: {e}")

    async def historique_dossier(self, resource_id: str, limite: int = 50) -> list[dict]:
        """Retourne toutes les actions sur un dossier (sinistre, session, réunion...)"""
        return await self._query(resource_id=resource_id, limite=limite)

    async def historique_utilisateur(self, user_id: int, limite: int = 100) -> list[dict]:
        """Retourne toutes les actions d'un utilisateur"""
        return await self._query(user_id=user_id, limite=limite)

    async def historique_module(self, module: str, limite: int = 200) -> list[dict]:
        """Retourne toutes les actions sur un module"""
        return await self._query(module=module, limite=limite)

    async def _query(
        self,
        resource_id: Optional[str] = None,
        user_id: Optional[int] = None,
        module: Optional[str] = None,
        limite: int = 50,
    ) -> list[dict]:
        try:
            from core.database import async_session_maker, AuditLogDB
            from sqlalchemy import select, desc

            async with async_session_maker() as db:
                q = select(AuditLogDB).order_by(desc(AuditLogDB.timestamp)).limit(limite)
                if resource_id:
                    q = q.where(AuditLogDB.resource_id == resource_id)
                if user_id:
                    q = q.where(AuditLogDB.user_id == user_id)
                if module:
                    q = q.where(AuditLogDB.module == module)

                result = await db.execute(q)
                return [
                    {
                        "id": log.id,
                        "timestamp": log.timestamp.isoformat(),
                        "user_id": log.user_id,
                        "user_nom": log.user_nom or "Système",
                        "action": log.action,
                        "module": log.module,
                        "resource_type": log.resource_type,
                        "resource_id": log.resource_id,
                        "details": log.details,
                        "duree_ms": log.duree_ms,
                        "succes": log.succes,
                        "erreur": log.erreur,
                    }
                    for log in result.scalars().all()
                ]
        except Exception as e:
            logger.warning(f"[Audit/query] Erreur: {e}")
            return []


# Singleton
audit_service = AuditService()
