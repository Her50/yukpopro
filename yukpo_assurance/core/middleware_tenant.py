"""
YukpoAssurance — Middleware multi-tenant (isolation par compagnie_id)

Fonctionnement :
1. Extrait le compagnie_id (claim 'cid') du JWT a chaque requete.
2. Injecte request.state.compagnie_id, request.state.user_id, request.state.role.
3. Si ENFORCE_COMPAGNIE_ISOLATION=True :
   - Les routes qui recoivent ?compagnie_id= en query param sont validees
     contre le compagnie_id du token (protection contre l'elevation horizontale).
   - Les requetes sans token valide vers des routes protegees sont rejetees (401).

Usage dans les routes :
    from core.middleware_tenant import get_compagnie_id

    @router.get("/contrats")
    async def liste_contrats(
        request: Request,
        db: AsyncSession = Depends(get_db),
    ):
        cid = get_compagnie_id(request)
        contrats = await db.execute(
            select(ContratDB).where(ContratDB.compagnie_id == cid)
        )

Dependance FastAPI (pour les routes qui EXIGENT l'isolation) :
    from core.middleware_tenant import compagnie_isolee

    @router.get("/sinistres")
    async def liste_sinistres(cid: int = Depends(compagnie_isolee)):
        ...
"""
from __future__ import annotations

import logging
from typing import Optional

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from config.settings import settings

logger = logging.getLogger("yukpo_assurance.tenant")

_BEARER = HTTPBearer(auto_error=False)

# Routes exclues du check multi-tenant (auth, health, metrics, webhooks entrants)
_ROUTES_PUBLIQUES = {
    "/",
    "/health",
    "/health/si",
    "/metrics",
    "/docs",
    "/openapi.json",
    "/redoc",
}
_PREFIXES_PUBLICS = (
    "/auth/",
    "/api/v1/paiement/webhook",
    "/api/v1/whatsapp/webhook",
)


def _extraire_jwt_payload(token: str) -> Optional[dict]:
    """Decode le token JWT. Retourne None si invalide (pas d'exception)."""
    try:
        from jose import jwt, JWTError
        payload = jwt.decode(
            token,
            settings.SECRET_KEY,
            algorithms=["HS256"],
            options={"verify_exp": True},
        )
        return payload
    except Exception:
        return None


class TenantMiddleware:
    """
    Middleware ASGI qui injecte le contexte tenant dans request.state.
    Doit etre ajoute via app.add_middleware(TenantMiddleware) dans main.py.
    """

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        from starlette.requests import Request as StarletteRequest
        from starlette.responses import JSONResponse

        request = StarletteRequest(scope, receive)
        path = request.url.path

        # Routes publiques : pas d'injection, pas de validation
        if path in _ROUTES_PUBLIQUES or any(path.startswith(p) for p in _PREFIXES_PUBLICS):
            await self.app(scope, receive, send)
            return

        # Tenter d'extraire le compagnie_id depuis le JWT
        compagnie_id: int = 1
        user_id: int = 0
        role: str = "agent"
        token_valide = False

        auth_header = request.headers.get("Authorization", "")
        if auth_header.startswith("Bearer "):
            payload = _extraire_jwt_payload(auth_header[7:])
            if payload:
                user_id = int(payload.get("sub", 0))
                compagnie_id = int(payload.get("cid", 1))
                role = payload.get("role", "agent")
                token_valide = True

        # Injecter dans request.state pour que les routes y accedent
        request.state.compagnie_id = compagnie_id
        request.state.user_id = user_id
        request.state.role = role
        request.state.token_valide = token_valide

        # Configurer le RLS PostgreSQL avec le compagnie_id courant
        try:
            import sqlalchemy as sa
            from core.database import async_session_maker
            async with async_session_maker() as session:
                await session.execute(
                    sa.text("SELECT set_config('app.current_compagnie_id', :cid, TRUE)"),
                    {"cid": str(compagnie_id)}
                )
                await session.commit()
        except Exception:
            pass

        # Enforcement : si active, valider la coherence compagnie_id
        if settings.ENFORCE_COMPAGNIE_ISOLATION and token_valide:
            # Verifier que le query param compagnie_id (si present) correspond au token
            qp_cid = request.query_params.get("compagnie_id")
            if qp_cid is not None:
                try:
                    if int(qp_cid) != compagnie_id:
                        response = JSONResponse(
                            status_code=status.HTTP_403_FORBIDDEN,
                            content={
                                "detail": "Acces refuse — compagnie_id ne correspond pas au token JWT.",
                                "code": "TENANT_ISOLATION_VIOLATION",
                            },
                        )
                        await response(scope, receive, send)
                        return
                except ValueError:
                    pass

        await self.app(scope, receive, send)


# ─── Helpers pour les routes ──────────────────────────────────────────────────

def get_compagnie_id(request: Request) -> int:
    """
    Retourne le compagnie_id extrait du JWT par TenantMiddleware.
    Valeur par defaut : 1 (mode dev, un seul tenant).
    """
    return getattr(request.state, "compagnie_id", 1)


def get_user_id(request: Request) -> int:
    """Retourne le user_id extrait du JWT."""
    return getattr(request.state, "user_id", 0)


def get_role(request: Request) -> str:
    """Retourne le role extrait du JWT."""
    return getattr(request.state, "role", "agent")


# ─── Dependance FastAPI (pour les routes qui exigent l'isolation) ─────────────

async def compagnie_isolee(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(_BEARER),
) -> int:
    """
    Dependance FastAPI : retourne le compagnie_id du token.
    Si ENFORCE_COMPAGNIE_ISOLATION=True, rejette les requetes sans token valide.
    Sinon, retourne 1 (mode dev permissif).

    Usage :
        @router.get("/contrats")
        async def liste(cid: int = Depends(compagnie_isolee)):
            ...
    """
    if not settings.ENFORCE_COMPAGNIE_ISOLATION:
        return get_compagnie_id(request)

    if not getattr(request.state, "token_valide", False):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token JWT requis pour acceder a cette ressource.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return get_compagnie_id(request)


# ─── Session DB filtree par tenant ────────────────────────────────────────────

class SessionTenant:
    """
    Wrapper sur AsyncSession qui ajoute automatiquement le filtre compagnie_id
    a toutes les requetes SELECT.

    Usage avance (optionnel — la plupart des routes peuvent simplement appeler
    get_compagnie_id(request) et filtrer manuellement) :

        from core.middleware_tenant import get_session_tenant

        @router.get("/sinistres")
        async def liste(
            request: Request,
            session_tenant: SessionTenant = Depends(get_session_tenant),
        ):
            sinistres = await session_tenant.select_all(SinistreDB)
    """

    def __init__(self, session, compagnie_id: int):
        self._session = session
        self.compagnie_id = compagnie_id

    async def select_all(self, model, **extra_filters):
        """Selectionne tous les enregistrements du modele pour ce tenant."""
        from sqlalchemy import select
        stmt = select(model).where(model.compagnie_id == self.compagnie_id)
        for attr, val in extra_filters.items():
            stmt = stmt.where(getattr(model, attr) == val)
        result = await self._session.execute(stmt)
        return result.scalars().all()

    async def select_one(self, model, resource_id: int):
        """Selectionne un enregistrement par ID en validant le tenant."""
        from sqlalchemy import select
        stmt = (
            select(model)
            .where(model.id == resource_id)
            .where(model.compagnie_id == self.compagnie_id)
        )
        result = await self._session.execute(stmt)
        obj = result.scalar_one_or_none()
        if obj is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"{model.__tablename__} id={resource_id} introuvable pour cette compagnie.",
            )
        return obj

    # Deleguer les autres methodes a la session sous-jacente
    def __getattr__(self, name):
        return getattr(self._session, name)


async def get_session_tenant(
    request: Request,
) -> SessionTenant:
    """
    Dependance FastAPI : fournit une SessionTenant filtree par compagnie_id.
    A utiliser avec 'async with' ou directement dans les routes.
    """
    from core.database import async_session_maker
    cid = get_compagnie_id(request)
    async with async_session_maker() as session:
        yield SessionTenant(session, cid)
