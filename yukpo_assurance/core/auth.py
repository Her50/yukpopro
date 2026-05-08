"""
YukpoAssurance — Authentification JWT + RBAC
Roles : agent | manager | daf | dg | actuaire | courtier | admin
"""
import hashlib
import logging
import secrets
from datetime import datetime, timedelta
from typing import Optional

from fastapi import Cookie, Depends, HTTPException, Request, Response, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer, OAuth2PasswordRequestForm
from pydantic import BaseModel

logger = logging.getLogger("yukpo_assurance.auth")

_security = HTTPBearer(auto_error=False)


# ─── Modèles ──────────────────────────────────────────────────────────────────

class TokenData(BaseModel):
    user_id: int
    user_nom: str
    role: str           # agent | manager | daf | dg | actuaire | courtier | admin
    compagnie_id: int = 1


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int     # secondes


# ─── Hiérarchie des rôles ─────────────────────────────────────────────────────

ROLE_PERMISSIONS: dict[str, set[str]] = {
    "agent": {
        "chat", "sinistres:read", "sinistres:declare",
        "copilote", "documents:read",
    },
    "manager": {
        "chat", "sinistres:read", "sinistres:declare", "sinistres:update",
        "sinistres:approve_under_1M", "copilote", "documents",
        "souscription", "courtiers:read", "analytics:read",
        "rh:read", "rh:approve",
        "commercial:read", "commercial:write",
        "collaboration:read", "collaboration:write",
        "community_manager", "trends", "agenda", "enquetes",
    },
    "actuaire": {
        "chat", "cima", "analytics", "documents",
        "sinistres:read", "copilote",
        "commercial:read",
        "collaboration:read",
        "trends", "enquetes",
    },
    "daf": {
        "chat", "cima", "analytics", "documents",
        "comptabilite", "sinistres:read", "sinistres:approve",
        "copilote", "courtiers",
        "rh:read", "rh:paie",
        "commercial:read", "commercial:write",
        "collaboration:read", "collaboration:write",
        "trends", "agenda",
    },
    "dg": {
        "chat", "cima", "analytics", "documents",
        "comptabilite", "sinistres", "sinistres:approve",
        "copilote", "courtiers", "souscription",
        "reunions", "audit", "enquetes",
        "rh:read", "rh:write", "rh:approve", "rh:paie",
        "commercial:read", "commercial:write",
        "collaboration:read", "collaboration:write",
        "community_manager", "trends", "agenda",
    },
    # ── Nouveaux rôles — Direction Commerciale & Marketing ──────────────
    "commercial": {
        "chat", "copilote",
        "commercial:read", "commercial:write",
        "souscription", "courtiers:read",
        "analytics:read",
        "collaboration:read", "collaboration:write",
        "community_manager", "trends", "agenda",
        "documents:read",
    },
    "marketing": {
        "chat", "copilote",
        "community_manager", "trends", "agenda",
        "commercial:read",
        "analytics:read",
        "collaboration:read", "collaboration:write",
        "documents:read",
    },
    # ────────────────────────────────────────────────────────────────────
    "courtier": {
        "chat", "souscription:submit", "courtiers:own_portal",
        "documents:read",
    },
    "admin": {"*"},       # Tous droits compagnie
    # ── Rôles Yukpo plateforme — accès exclusif aux agents systèmes ──────────
    "super_admin": {"*", "agents:systeme", "schema_si:full", "meta_factory:full", "yukpo:owner"},
    "yukpo_owner": {"*", "agents:systeme", "schema_si:full", "meta_factory:full", "yukpo:owner"},
}


def _a_permission(role: str, permission: str) -> bool:
    perms = ROLE_PERMISSIONS.get(role, set())
    if "*" in perms:
        return True
    if permission in perms:
        return True
    # Vérification préfixe (sinistres:read couvre sinistres:read)
    base = permission.split(":")[0]
    return base in perms


# ─── Création / Vérification de token ─────────────────────────────────────────

def creer_token(user_id: int, user_nom: str, role: str, compagnie_id: int = 1) -> str:
    """Crée un JWT signé. À appeler lors de la connexion."""
    try:
        from jose import jwt
        from config.settings import settings

        expire = datetime.utcnow() + timedelta(
            minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES
        )
        payload = {
            "sub": str(user_id),
            "nom": user_nom,
            "role": role,
            "cid": compagnie_id,
            "exp": expire,
        }
        return jwt.encode(payload, settings.SECRET_KEY, algorithm="HS256")
    except Exception as e:
        logger.error(f"[Auth] Erreur création token: {e}")
        raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, "Erreur création token")


def _blacklister_token(token: str) -> None:
    """Blackliste un token JWT dans Redis (durée = expiration du token)."""
    try:
        from jose import jwt as _jwt
        from config.settings import settings
        payload = _jwt.decode(token, settings.SECRET_KEY, algorithms=["HS256"], options={"verify_exp": False})
        exp = payload.get("exp", 0)
        ttl = max(0, int(exp - datetime.utcnow().timestamp()))
        if ttl > 0:
            import redis as redis_lib
            r = redis_lib.from_url(settings.REDIS_URL, socket_connect_timeout=1)
            r.setex(f"jwt:blacklist:{token[:64]}", ttl, "1")
    except Exception:
        pass

def _est_token_blackliste(token: str) -> bool:
    """Vérifie si un token est blacklisté."""
    try:
        from config.settings import settings
        import redis as redis_lib
        r = redis_lib.from_url(settings.REDIS_URL, socket_connect_timeout=1)
        return bool(r.exists(f"jwt:blacklist:{token[:64]}"))
    except Exception:
        return False


def _decoder_token(token: str) -> TokenData:
    from jose import jwt, JWTError
    from config.settings import settings

    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Token invalide ou expiré",
        headers={"WWW-Authenticate": "Bearer"},
    )
    if _est_token_blackliste(token):
        raise credentials_exception
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=["HS256"])
        user_id = int(payload.get("sub", 0))
        if user_id == 0:
            raise credentials_exception
        return TokenData(
            user_id=user_id,
            user_nom=payload.get("nom", "Inconnu"),
            role=payload.get("role", "agent"),
            compagnie_id=payload.get("cid", 1),
        )
    except JWTError:
        raise credentials_exception


# ─── Dépendances FastAPI ──────────────────────────────────────────────────────

async def get_current_user(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(_security),
) -> TokenData:
    """
    Dépendance : extrait et valide le token JWT.
    Stratégie triple :
      1. Cookie httpOnly (frontend web)
      2. Authorization Bearer header (API clients, mobile)
      3. Query param ?token= (EventSource/SSE — ne supporte pas les headers)
    """
    token: Optional[str] = None

    # 1. Cookie httpOnly (frontend web — protection XSS)
    cookie_val = request.cookies.get("access_token", "")
    if cookie_val.startswith("Bearer "):
        token = cookie_val[7:]

    # 2. Authorization Bearer header (API clients, mobile)
    if not token and credentials is not None:
        token = credentials.credentials

    # 3. Query param ?token= (EventSource SSE — ne peut pas envoyer de headers)
    if not token:
        token = request.query_params.get("token") or None

    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentification requise",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return _decoder_token(token)


async def get_current_user_optional(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(_security),
) -> Optional[TokenData]:
    """Dépendance : token optionnel (pour les routes en mode développement)."""
    if credentials is None:
        return None
    try:
        return _decoder_token(credentials.credentials)
    except HTTPException:
        return None


def require_role(*roles: str):
    """Dépendance factory : vérifie que l'utilisateur a l'un des rôles requis."""
    async def _check(current_user: TokenData = Depends(get_current_user)) -> TokenData:
        # Admin bypass uniquement si "admin" est explicitement dans la liste des rôles autorisés
        # OU si l'utilisateur est admin (super-utilisateur global)
        if current_user.role != "admin" and current_user.role not in roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Rôle requis : {', '.join(roles)}.",
            )
        return current_user
    return _check


def require_permission(permission: str):
    """Dépendance factory : vérifie une permission spécifique."""
    async def _check(current_user: TokenData = Depends(get_current_user)) -> TokenData:
        if not _a_permission(current_user.role, permission):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Permission '{permission}' requise",
            )
        return current_user
    return _check


# ─── Route d'authentification ────────────────────────────────────────────────

from fastapi import APIRouter

auth_router = APIRouter()


class LoginRequest(BaseModel):
    username: str
    password: str
    compagnie_id: int = 1


def _poser_cookies_auth(response: Response, token: str, expire_minutes: int) -> None:
    """
    Pose le JWT en cookie httpOnly (protection XSS) + un cookie CSRF lisible par JS.
    Stratégie double-cookie : JWT httpOnly + CSRF token SameSite=Strict.
    """
    from config.settings import settings
    is_https = not settings.DEBUG  # En prod on suppose HTTPS
    expire_sec = expire_minutes * 60

    # Cookie httpOnly — JWT principal (inaccessible depuis JS → protection XSS)
    response.set_cookie(
        key="access_token",
        value=f"Bearer {token}",
        httponly=True,
        secure=is_https,
        samesite="strict",
        max_age=expire_sec,
        path="/",
    )
    # Cookie CSRF — lu par JS, envoyé en header X-CSRF-Token (protection CSRF)
    csrf_token = hashlib.sha256(f"{token}:{secrets.token_hex(8)}".encode()).hexdigest()[:32]
    response.set_cookie(
        key="csrf_token",
        value=csrf_token,
        httponly=False,    # Lisible par JS pour l'envoyer en header
        secure=is_https,
        samesite="strict",
        max_age=expire_sec,
        path="/",
    )


async def _executer_login(username: str, password: str, compagnie_id: int, response: Response) -> TokenResponse:
    """Logique commune de login (JSON ou FormData)."""
    from config.settings import settings

    # Simulation mode : vérification basique
    if settings.ORASS_MODE == "simulation":
        if password not in ("yukpo2025", "Admin123!"):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Identifiants incorrects",
            )
        # Accepter les emails complets ou les usernames courts
        username_key = username.lower().split("@")[0]  # admin@yukpo.cm → admin
        roles_demo = {
            "dg": "dg", "daf": "daf", "actuaire": "actuaire",
            "manager": "manager", "admin": "admin",
            "commercial": "commercial", "marketing": "marketing",
            # Propriétaires Yukpo — accès agents système
            "super_admin": "super_admin",
            "yukpo": "yukpo_owner",
            "yukpo_owner": "yukpo_owner",
        }
        role = roles_demo.get(username_key, "agent")
        user_id = hash(username) % 10000 + 1
        token = creer_token(
            user_id=user_id,
            user_nom=username.capitalize(),
            role=role,
            compagnie_id=compagnie_id,
        )
        # Poser les cookies httpOnly pour le frontend web
        _poser_cookies_auth(response, token, settings.ACCESS_TOKEN_EXPIRE_MINUTES)
        return TokenResponse(
            access_token=token,  # Retourné aussi pour les clients API/mobile
            expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        )

    # ── Production : authentification DB ──────────────────────────────────────
    req = LoginRequest(username=username, password=password, compagnie_id=compagnie_id)
    return await _login_db(req, response)


@auth_router.post("/login", response_model=TokenResponse)
async def login(req: LoginRequest, response: Response):
    """
    Authentification JSON — pour les clients API classiques.
    Body : { "username": "...", "password": "...", "compagnie_id": 1 }
    """
    return await _executer_login(req.username, req.password, req.compagnie_id, response)


@auth_router.post("/token", response_model=TokenResponse)
async def token_oauth2(
    response: Response,
    form_data: OAuth2PasswordRequestForm = Depends(),
):
    """
    Authentification OAuth2 FormData — pour le frontend web, mobile et Swagger UI.
    Content-Type: multipart/form-data ou application/x-www-form-urlencoded
    Fields: username, password
    """
    return await _executer_login(form_data.username, form_data.password, 1, response)


@auth_router.post("/logout")
async def logout(
    request: Request,
    response: Response,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(_security),
):
    """Déconnexion — suppression des cookies + blacklist du token JWT."""
    # Blacklister le token actif
    token: Optional[str] = None
    cookie_val = request.cookies.get("access_token", "")
    if cookie_val.startswith("Bearer "):
        token = cookie_val[7:]
    elif credentials is not None:
        token = credentials.credentials
    if token:
        _blacklister_token(token)
    response.delete_cookie("access_token", path="/")
    response.delete_cookie("csrf_token", path="/")
    return {"message": "Déconnecté"}


async def _login_db(req: "LoginRequest", response: "Response") -> "TokenResponse":
    """
    Authentification production via table UtilisateurDB.
    - Vérifie le hash bcrypt
    - Détecte les comptes bloqués (brute force)
    - Met à jour la dernière connexion
    - Rate limiting : 5 tentatives max en 15 min (via security_service)
    """
    from datetime import datetime as _dt
    from sqlalchemy import select
    from core.database import async_session_maker, UtilisateurDB
    from core.security import security_service
    from config.settings import settings as _settings

    # Vérification brute force AVANT la requête DB (évite l'énumération)
    bloque, nb_tentatives = security_service.detecter_tentatives_brute_force(
        req.username, action="login"
    )
    if bloque:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Compte temporairement bloqué après {nb_tentatives} tentatives. "
                   f"Réessayez dans 15 minutes.",
            headers={"Retry-After": "900"},
        )

    async with async_session_maker() as session:
        # Recherche par username OU email
        result = await session.execute(
            select(UtilisateurDB).where(
                (UtilisateurDB.username == req.username)
                | (UtilisateurDB.email == req.username)
            ).where(UtilisateurDB.compagnie_id == req.compagnie_id)
        )
        user = result.scalar_one_or_none()

        # Vérification générique (timing constant — pas d'énumération utilisateur)
        if user is None:
            # Simuler un hash check pour éviter le timing attack
            from passlib.context import CryptContext
            _CryptContext = CryptContext(schemes=["bcrypt"], deprecated="auto")
            _CryptContext.verify(req.password, "$2b$12$dummy.hash.to.prevent.timing.attack.xx")
            security_service.detecter_tentatives_brute_force(req.username, "login")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Identifiants incorrects",
                headers={"WWW-Authenticate": "Bearer"},
            )

        # Compte désactivé
        if not user.actif:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Compte désactivé. Contacter l'administrateur.",
            )

        # Vérification compte bloqué manuellement (champ BD)
        if user.bloque_jusqu_au and user.bloque_jusqu_au > _dt.utcnow():
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Compte bloqué jusqu'au {user.bloque_jusqu_au.strftime('%d/%m/%Y %H:%M')}.",
            )

        # Vérification du mot de passe
        from passlib.context import CryptContext
        pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
        if not pwd_context.verify(req.password, user.hashed_password):
            # Incrémenter les échecs DB
            user.tentatives_echec = (user.tentatives_echec or 0) + 1
            # Auto-verrouilage après 10 tentatives échouées (DB-level)
            if user.tentatives_echec >= 10:
                from datetime import timedelta
                user.bloque_jusqu_au = _dt.utcnow() + timedelta(minutes=30)
                logger.warning(f"[Auth] Compte verrouillé 30min après 10 échecs DB: {req.username}")
            await session.commit()
            # Ne pas ré-incrémenter le compteur Redis — déjà fait en début de fonction
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Identifiants incorrects",
                headers={"WWW-Authenticate": "Bearer"},
            )

        # Succès — reset tentatives et mettre à jour
        user.tentatives_echec = 0
        user.nb_connexions = (user.nb_connexions or 0) + 1
        user.derniere_connexion = _dt.utcnow()
        await session.commit()

        # Reset brute force Redis
        security_service.reinitialiser_tentatives(req.username, "login")

        nom_complet = f"{user.prenoms or ''} {user.nom}".strip() or user.username
        token = creer_token(
            user_id=user.id,
            user_nom=nom_complet,
            role=user.role,
            compagnie_id=user.compagnie_id,
        )
        logger.info(
            f"[Auth] Connexion réussie: user_id={user.id} username={user.username} "
            f"role={user.role} compagnie={user.compagnie_id}"
        )
        # Poser les cookies httpOnly pour le frontend web
        _poser_cookies_auth(response, token, _settings.ACCESS_TOKEN_EXPIRE_MINUTES)
        return TokenResponse(
            access_token=token,
            expires_in=_settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        )


@auth_router.post("/register")
async def register(
    req: "LoginRequest",
    current_admin: TokenData = Depends(require_role("admin")),
):
    """
    Crée un nouvel utilisateur (admin uniquement).
    Le mot de passe est haché avec bcrypt avant stockage.
    """
    from sqlalchemy import select
    from passlib.context import CryptContext
    from core.database import async_session_maker, UtilisateurDB
    from datetime import datetime as _dt

    pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
    hashed = pwd_context.hash(req.password)

    async with async_session_maker() as session:
        # Vérifier si username existe déjà
        existing = await session.execute(
            select(UtilisateurDB).where(UtilisateurDB.username == req.username)
        )
        if existing.scalar_one_or_none():
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Nom d'utilisateur '{req.username}' déjà utilisé.",
            )

        user = UtilisateurDB(
            username=req.username,
            email=req.username if "@" in req.username else f"{req.username}@yukpo.local",
            nom=req.username.capitalize(),
            hashed_password=hashed,
            role="agent",
            compagnie_id=req.compagnie_id,
            actif=True,
            cree_le=_dt.utcnow(),
            cree_par=current_admin.user_id,
        )
        session.add(user)
        await session.commit()
        await session.refresh(user)

    logger.info(f"[Auth] Utilisateur créé: id={user.id} username={user.username} par admin={current_admin.user_id}")
    return {"succes": True, "user_id": user.id, "username": user.username, "role": user.role}


class RegisterProRequest(BaseModel):
    email: str
    password: str
    nom: str


@auth_router.post("/register/pro", summary="Auto-inscription YukpoPro (mobile/web)")
async def register_pro(req: RegisterProRequest):
    """
    Auto-inscription publique pour les professionnels YukpoPro.
    Crée un compte avec le rôle 'agent' et le plan gratuit.
    En mode simulation : accepte toujours (utile pour le développement).
    """
    from config.settings import settings

    # Mode simulation : pas de DB, retourner succès
    if settings.ORASS_MODE == "simulation":
        logger.info(f"[Auth] Inscription simulation: email={req.email}")
        return {"succes": True, "message": "Compte créé. Connectez-vous avec vos identifiants."}

    # Mode production : créer en base
    from sqlalchemy import select
    from passlib.context import CryptContext
    from core.database import async_session_maker, UtilisateurDB
    from datetime import datetime as _dt

    if len(req.password) < 6:
        raise HTTPException(status_code=400, detail="Mot de passe trop court (minimum 6 caractères).")

    pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
    hashed = pwd_context.hash(req.password)
    username = req.email.split("@")[0]

    async with async_session_maker() as session:
        existing = await session.execute(
            select(UtilisateurDB).where(UtilisateurDB.email == req.email)
        )
        if existing.scalar_one_or_none():
            raise HTTPException(status_code=409, detail="Cette adresse email est déjà utilisée.")

        user = UtilisateurDB(
            username=username,
            email=req.email,
            nom=req.nom,
            hashed_password=hashed,
            role="agent",
            compagnie_id=1,
            actif=True,
            cree_le=_dt.utcnow(),
            cree_par=0,
        )
        session.add(user)
        await session.commit()
        await session.refresh(user)

    logger.info(f"[Auth] Auto-inscription: id={user.id} email={req.email}")
    return {"succes": True, "message": "Compte créé. Connectez-vous avec vos identifiants.", "user_id": user.id}


@auth_router.post("/change-password")
async def change_password(
    ancien_mdp: str,
    nouveau_mdp: str,
    current_user: TokenData = Depends(get_current_user),
):
    """Change le mot de passe de l'utilisateur connecté."""
    from sqlalchemy import select
    from passlib.context import CryptContext
    from core.database import async_session_maker, UtilisateurDB
    from datetime import datetime as _dt

    import re as _re
    if len(nouveau_mdp) < 8:
        raise HTTPException(status_code=400, detail="Minimum 8 caractères.")
    if not _re.search(r'[A-Z]', nouveau_mdp):
        raise HTTPException(status_code=400, detail="Le mot de passe doit contenir au moins une majuscule.")
    if not _re.search(r'[0-9]', nouveau_mdp):
        raise HTTPException(status_code=400, detail="Le mot de passe doit contenir au moins un chiffre.")

    pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
    async with async_session_maker() as session:
        result = await session.execute(
            select(UtilisateurDB).where(UtilisateurDB.id == current_user.user_id)
        )
        user = result.scalar_one_or_none()
        if not user:
            raise HTTPException(status_code=404, detail="Utilisateur introuvable")
        if not pwd_context.verify(ancien_mdp, user.hashed_password):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Ancien mot de passe incorrect",
            )
        user.hashed_password = pwd_context.hash(nouveau_mdp)
        user.modifie_le = _dt.utcnow()
        await session.commit()

    return {"succes": True, "message": "Mot de passe modifié avec succès."}


@auth_router.get("/me")
async def me(current_user: TokenData = Depends(get_current_user)):
    """Retourne les informations de l'utilisateur connecté."""
    nom_clean: str | None = None
    prenoms_clean: str | None = None
    email_clean: str | None = None
    try:
        from sqlalchemy import select
        from core.database import async_session_maker, UtilisateurDB
        async with async_session_maker() as session:
            r = await session.execute(
                select(UtilisateurDB).where(UtilisateurDB.id == current_user.user_id)
            )
            u = r.scalar_one_or_none()
            if u:
                nom_clean     = (u.nom or "").strip() or None
                prenoms_clean = (u.prenoms or "").strip() or None
                email_clean   = u.email
    except Exception as e:
        logger.debug(f"[Auth/me] lookup nom DB échoué: {e}")

    # Si `nom` est juste l'email (cas de comptes créés sans nom propre),
    # on l'ignore pour que le frontend puisse fallback proprement.
    nom_propre = nom_clean
    if nom_propre and "@" in nom_propre:
        nom_propre = None

    # Calcul d'un nom d'affichage pour fallback systématique.
    affichage_nom = (
        prenoms_clean or
        nom_propre or
        (current_user.user_nom if current_user.user_nom and "@" not in current_user.user_nom else None) or
        ""
    )
    # Dernier recours : extraire un nom lisible depuis l'email
    if not affichage_nom and email_clean and "@" in email_clean:
        local = email_clean.split("@")[0]
        affichage_nom = local.replace(".", " ").replace("_", " ").replace("-", " ").title()

    return {
        "user_id": current_user.user_id,
        "user_nom": affichage_nom or "Utilisateur",
        "user_nom_brut": current_user.user_nom,
        "nom": nom_propre,            # null si c'est l'email
        "prenoms": prenoms_clean,
        "email": email_clean,
        "role": current_user.role,
        "compagnie_id": current_user.compagnie_id,
        "permissions": list(ROLE_PERMISSIONS.get(current_user.role, set())),
    }


class UpdateProfileRequest(BaseModel):
    nom: Optional[str] = Field(None, min_length=1, max_length=100)
    prenoms: Optional[str] = Field(None, min_length=1, max_length=150)
    telephone: Optional[str] = Field(None, max_length=30)


@auth_router.patch("/profile", summary="Modifier mon profil (nom, prénoms, téléphone)")
async def update_profile(
    req: UpdateProfileRequest,
    current_user: TokenData = Depends(get_current_user),
):
    """Permet à l'utilisateur de mettre à jour son nom/prénoms/téléphone."""
    from sqlalchemy import select, update as sa_update
    from core.database import async_session_maker, UtilisateurDB
    from datetime import datetime as _dt

    data = req.model_dump(exclude_none=True)
    if not data:
        raise HTTPException(400, "Aucun champ à mettre à jour")
    # Validation : nom et prenoms ne doivent pas contenir @
    for k in ("nom", "prenoms"):
        if k in data and "@" in data[k]:
            raise HTTPException(400, f"Le champ {k} ne doit pas contenir d'email")

    async with async_session_maker() as session:
        r = await session.execute(
            select(UtilisateurDB).where(UtilisateurDB.id == current_user.user_id)
        )
        u = r.scalar_one_or_none()
        if not u:
            raise HTTPException(404, "Utilisateur introuvable")
        for k, v in data.items():
            setattr(u, k, v.strip() if isinstance(v, str) else v)
        u.modifie_le = _dt.utcnow()
        await session.commit()

    logger.info(f"[Auth/Profile] user_id={current_user.user_id} profil mis à jour : {list(data.keys())}")
    return {"succes": True, "message": "Profil mis à jour", "champs_modifies": list(data.keys())}


# ─── 2FA TOTP ────────────────────────────────────────────────────────────────

class TOTPSetupResponse(BaseModel):
    secret: str
    provisioning_uri: str
    qr_code_b64: Optional[str] = None

class TOTPVerifyRequest(BaseModel):
    totp_code: str
    user_id: int
    compagnie_id: int = 1

@auth_router.post("/2fa/setup", response_model=TOTPSetupResponse)
async def setup_2fa(current_user: TokenData = Depends(get_current_user)):
    """Génère un secret TOTP et l'URI de provisionnement pour l'authentificateur."""
    try:
        import pyotp
        import qrcode
        import qrcode.image.svg
        import io
        import base64
        from config.settings import settings
        secret = pyotp.random_base32()
        uri = pyotp.totp.TOTP(secret).provisioning_uri(
            name=current_user.user_nom,
            issuer_name="YukpoAssurance"
        )
        # Stocker le secret en Redis temporairement (15 min pour confirmer)
        import redis as redis_lib
        r = redis_lib.from_url(settings.REDIS_URL, socket_connect_timeout=2)
        r.setex(f"2fa:pending:{current_user.user_id}", 900, secret)
        # QR Code
        qr_b64 = None
        try:
            img = qrcode.make(uri)
            buf = io.BytesIO()
            img.save(buf, format="PNG")
            qr_b64 = base64.b64encode(buf.getvalue()).decode()
        except Exception:
            pass
        return TOTPSetupResponse(secret=secret, provisioning_uri=uri, qr_code_b64=qr_b64)
    except ImportError:
        raise HTTPException(500, "Module pyotp non installé — pip install pyotp qrcode")

@auth_router.post("/2fa/verify-setup")
async def verify_setup_2fa(
    code: str,
    current_user: TokenData = Depends(get_current_user),
):
    """Confirme le setup 2FA en vérifiant le premier code TOTP."""
    try:
        import pyotp
        import redis as redis_lib
        from config.settings import settings
        r = redis_lib.from_url(settings.REDIS_URL, socket_connect_timeout=2)
        secret = r.get(f"2fa:pending:{current_user.user_id}")
        if not secret:
            raise HTTPException(400, "Session 2FA expirée. Recommencez /2fa/setup.")
        secret = secret.decode() if isinstance(secret, bytes) else secret
        totp = pyotp.TOTP(secret)
        if not totp.verify(code, valid_window=1):
            raise HTTPException(400, "Code TOTP invalide.")
        # Activer 2FA — sauvegarder le secret en DB
        from sqlalchemy import select
        from core.database import async_session_maker, UtilisateurDB
        async with async_session_maker() as session:
            result = await session.execute(
                select(UtilisateurDB).where(UtilisateurDB.id == current_user.user_id)
            )
            user = result.scalar_one_or_none()
            if user:
                user.totp_secret = secret
                user.totp_active = True
                await session.commit()
        r.delete(f"2fa:pending:{current_user.user_id}")
        return {"succes": True, "message": "2FA activé avec succès."}
    except ImportError:
        raise HTTPException(500, "Module pyotp non installé")

@auth_router.post("/2fa/validate")
async def validate_2fa(req: TOTPVerifyRequest):
    """Valide un code TOTP lors de la connexion (appelé après /login si 2FA actif)."""
    try:
        import pyotp
        from sqlalchemy import select
        from core.database import async_session_maker, UtilisateurDB
        async with async_session_maker() as session:
            result = await session.execute(
                select(UtilisateurDB).where(
                    UtilisateurDB.id == req.user_id,
                    UtilisateurDB.compagnie_id == req.compagnie_id,
                )
            )
            user = result.scalar_one_or_none()
            if not user or not getattr(user, 'totp_active', False):
                raise HTTPException(400, "2FA non activé pour cet utilisateur.")
            totp = pyotp.TOTP(user.totp_secret)
            if not totp.verify(req.totp_code, valid_window=1):
                raise HTTPException(401, "Code TOTP invalide ou expiré.")
        return {"valide": True}
    except ImportError:
        raise HTTPException(500, "Module pyotp non installé")

@auth_router.post("/2fa/disable")
async def disable_2fa(
    totp_code: str,
    current_user: TokenData = Depends(require_role("admin", "dg", "daf", "manager")),
):
    """Désactive le 2FA (nécessite de valider un code TOTP en premier)."""
    try:
        import pyotp
        from sqlalchemy import select
        from core.database import async_session_maker, UtilisateurDB
        async with async_session_maker() as session:
            result = await session.execute(
                select(UtilisateurDB).where(UtilisateurDB.id == current_user.user_id)
            )
            user = result.scalar_one_or_none()
            if not user or not getattr(user, 'totp_active', False):
                raise HTTPException(400, "2FA non activé.")
            totp = pyotp.TOTP(user.totp_secret)
            if not totp.verify(totp_code, valid_window=1):
                raise HTTPException(401, "Code TOTP invalide.")
            user.totp_secret = None
            user.totp_active = False
            await session.commit()
        return {"succes": True, "message": "2FA désactivé."}
    except ImportError:
        raise HTTPException(500, "Module pyotp non installé")


# ─── Setup initial Yukpo (une seule utilisation) ──────────────────────────────

class _SetupYukpoRequest(BaseModel):
    setup_secret: str          # Doit correspondre à SETUP_YUKPO_SECRET dans .env
    email: str
    password: str
    nom: str = "Yukpo Admin"


class _UnlockRequest(BaseModel):
    setup_secret: str
    username: str   # email ou username à débloquer


@auth_router.post("/unlock-account", include_in_schema=False)
async def unlock_account(body: "_UnlockRequest"):
    """
    Débloque un compte bloqué par brute-force (Redis + DB).
    Protégé par SETUP_YUKPO_SECRET. Usage maintenance uniquement.
    """
    import os
    expected = os.environ.get("SETUP_YUKPO_SECRET", "")
    if not expected or body.setup_secret != expected:
        raise HTTPException(status_code=404, detail="Not found")

    # Reset Redis brute-force
    from core.security import security_service
    security_service.reinitialiser_tentatives(body.username, "login")

    # Reset DB lock
    from sqlalchemy import select, update
    from core.database import async_session_maker, UtilisateurDB
    from datetime import datetime as _dt

    async with async_session_maker() as session:
        await session.execute(
            update(UtilisateurDB)
            .where(
                (UtilisateurDB.username == body.username)
                | (UtilisateurDB.email == body.username)
            )
            .values(bloque_jusqu_au=None, tentatives_echec=0)
        )
        await session.commit()

    logger.info(f"[Auth] Compte débloqué par admin: {body.username}")
    return {"succes": True, "message": f"Compte {body.username} débloqué."}


@auth_router.post("/setup-yukpo", include_in_schema=False)
async def setup_yukpo_owner(body: "_SetupYukpoRequest"):
    """
    Endpoint de bootstrap : crée le premier compte super_admin Yukpo.

    Protégé par SETUP_YUKPO_SECRET (variable d'environnement).
    Une fois le compte créé, cet endpoint renvoie 409 si un super_admin existe déjà.
    À désactiver (SETUP_YUKPO_SECRET="") après la première utilisation en production.

    Usage :
        curl -X POST http://localhost:8000/api/v1/auth/setup-yukpo \\
             -H 'Content-Type: application/json' \\
             -d '{"setup_secret":"MON_SECRET","email":"dg@yukpo.cm","password":"MotDePasse!"}'
    """
    import os
    from sqlalchemy import select
    from passlib.context import CryptContext
    from datetime import datetime as _dt
    from core.database import async_session_maker, UtilisateurDB

    # 1. Vérifier le secret de setup
    expected_secret = os.environ.get("SETUP_YUKPO_SECRET", "")
    if not expected_secret or body.setup_secret != expected_secret:
        # Réponse identique à une 404 pour ne pas révéler l'existence de l'endpoint
        raise HTTPException(status_code=404, detail="Not found")

    # 2. Vérifier qu'aucun super_admin n'existe déjà
    async with async_session_maker() as session:
        existing = await session.execute(
            select(UtilisateurDB).where(
                UtilisateurDB.role.in_(["super_admin", "yukpo_owner"])
            )
        )
        if existing.scalars().first():
            raise HTTPException(
                status_code=409,
                detail="Un compte super_admin existe déjà. Endpoint désactivé."
            )

        # 3. Créer le compte
        pwd_ctx = CryptContext(schemes=["bcrypt"], deprecated="auto")
        user = UtilisateurDB(
            username=body.email.split("@")[0],
            email=body.email,
            nom=body.nom,
            hashed_password=pwd_ctx.hash(body.password),
            role="super_admin",
            compagnie_id=None,
            actif=True,
            cree_le=_dt.utcnow(),
            cree_par=0,
        )
        session.add(user)
        await session.commit()
        await session.refresh(user)

    logger.info(f"[Auth] Super admin Yukpo créé : id={user.id} email={body.email}")
    return {
        "succes": True,
        "message": "Compte super_admin créé. Désactivez SETUP_YUKPO_SECRET maintenant.",
        "user_id": user.id,
        "email": body.email,
        "role": "super_admin",
    }
