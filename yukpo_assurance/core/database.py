"""
YukpoAssurance — Base de données persistante
SQLite en développement, PostgreSQL en production.
Stockage : utilisateurs, sessions chat, messages, réunions, actions, audit trail, dossiers,
           RH (employés, congés, évaluations, recrutement),
           Commercial (prospects, objectifs, campagnes),
           Collaboration (documents, versions, workflows, commentaires, notifications).
"""
import logging
from datetime import datetime
from typing import AsyncGenerator

from sqlalchemy import (
    BigInteger, Boolean, Column, DateTime, Float, ForeignKey,
    Integer, JSON, Numeric, String, Text, text,
)
from sqlalchemy.ext.asyncio import (
    AsyncSession, async_sessionmaker, create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase, relationship

from config.settings import settings

logger = logging.getLogger("yukpo_assurance.database")


# ─── Engine (SQLite dev / PostgreSQL prod) ────────────────────────────────────

def _build_engine():
    url = settings.DATABASE_URL
    if url.startswith("postgresql"):
        # Pool serré pour rester sous le quota Postgres Fly (≈ 25-100 slots
        # selon le plan, dont une part réservée SUPERUSER). 5+10 par worker
        # × 2 workers (Dockerfile WORKERS=2) = 30 connexions max.
        # pool_recycle : recycle les connexions > 1h (évite zombies).
        # pool_pre_ping : invalide les connexions cassées avant emprunt.
        # pool_timeout : ne bloque pas une requête > 30s en attente de slot.
        return create_async_engine(
            url,
            pool_size=5,
            max_overflow=10,
            pool_recycle=3600,
            pool_pre_ping=True,
            pool_timeout=30,
            echo=False,
        )
    # Dev local / test : SQLite async (ne nécessite pas de serveur)
    sqlite_url = url if url.startswith("sqlite") else "sqlite+aiosqlite:///./yukpo_assurance.db"
    return create_async_engine(
        sqlite_url,
        echo=False,
        connect_args={"check_same_thread": False},
    )


engine = _build_engine()
async_session_maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


# ─── UTILISATEURS ────────────────────────────────────────────────────────────

class UtilisateurDB(Base):
    """
    Table des utilisateurs — authentification production.
    Rôles RBAC : agent | manager | daf | dg | actuaire | commercial | marketing | courtier | admin
    """
    __tablename__ = "utilisateurs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    username = Column(String(100), unique=True, nullable=False, index=True)
    email = Column(String(255), unique=True, nullable=False, index=True)
    nom = Column(String(100), nullable=False)
    prenoms = Column(String(150), nullable=True)
    # Mot de passe haché avec bcrypt (passlib)
    hashed_password = Column(String(255), nullable=False)
    role = Column(String(50), nullable=False, default="agent")
    compagnie_id = Column(Integer, nullable=False, default=1)
    actif = Column(Boolean, default=True, nullable=False)
    # Infos complémentaires
    telephone = Column(String(30), nullable=True)
    code_agent = Column(String(30), nullable=True, index=True)
    # Sécurité
    nb_connexions = Column(Integer, default=0, nullable=False)
    derniere_connexion = Column(DateTime, nullable=True)
    tentatives_echec = Column(Integer, default=0, nullable=False)
    bloque_jusqu_au = Column(DateTime, nullable=True)
    # 2FA TOTP (Google Authenticator)
    totp_secret = Column(String(100), nullable=True)
    totp_active = Column(Boolean, default=False, nullable=False)
    # Audit
    cree_le = Column(DateTime, default=datetime.utcnow, nullable=False)
    modifie_le = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    cree_par = Column(Integer, nullable=True)    # user_id du créateur

    def __repr__(self) -> str:
        return f"<UtilisateurDB id={self.id} username={self.username} role={self.role}>"


# ─── SESSIONS CHAT ────────────────────────────────────────────────────────────

class SessionChatDB(Base):
    __tablename__ = "sessions_chat"

    id = Column(String, primary_key=True)
    user_id = Column(Integer, index=True, nullable=False)
    user_nom = Column(String, nullable=True)
    role_utilisateur = Column(String, default="agent")
    titre = Column(String, nullable=True)
    ecran_contexte = Column(String, nullable=True)
    resume = Column(Text, nullable=True)
    memoire_utilisateur = Column(JSON, default=dict)
    nb_messages = Column(Integer, default=0)
    tokens_total = Column(Integer, default=0)
    creee_le = Column(DateTime, default=datetime.utcnow)
    mise_a_jour = Column(DateTime, default=datetime.utcnow)

    messages = relationship(
        "MessageChatDB", back_populates="session",
        cascade="all, delete-orphan", order_by="MessageChatDB.timestamp",
    )


class MessageChatDB(Base):
    __tablename__ = "messages_chat"

    id = Column(Integer, primary_key=True, autoincrement=True)
    session_id = Column(String, ForeignKey("sessions_chat.id", ondelete="CASCADE"), index=True)
    role = Column(String, nullable=False)         # "user" | "assistant"
    contenu = Column(Text, nullable=False)
    attachments_meta = Column(JSON, default=list)  # métadonnées (sans le base64 lourd)
    generated_files = Column(JSON, default=list)
    modele_utilise = Column(String, nullable=True)
    tokens = Column(Integer, default=0)
    domaine = Column(String, nullable=True)
    dossier_reference = Column(String, nullable=True, index=True)  # SIN/police liée
    timestamp = Column(DateTime, default=datetime.utcnow)

    session = relationship("SessionChatDB", back_populates="messages")


# ─── RÉUNIONS ─────────────────────────────────────────────────────────────────

class ReunionDB(Base):
    __tablename__ = "reunions"

    id = Column(String, primary_key=True)
    titre = Column(String, nullable=False)
    type_reunion = Column(String, default="ordinaire")
    lieu = Column(String, nullable=True)
    president_seance = Column(String, nullable=True)
    statut = Column(String, default="en_cours")
    ordre_du_jour = Column(JSON, default=list)
    participants = Column(JSON, default=list)
    transcription = Column(Text, nullable=True)
    notes_manuelles = Column(Text, nullable=True)
    synthese = Column(Text, nullable=True)
    decisions = Column(JSON, default=list)
    points_reportes = Column(JSON, default=list)
    date_reunion = Column(DateTime, default=datetime.utcnow)
    creee_par_user_id = Column(Integer, nullable=True)
    creee_par_nom = Column(String, nullable=True)
    creee_le = Column(DateTime, default=datetime.utcnow)
    mise_a_jour = Column(DateTime, default=datetime.utcnow)

    actions = relationship(
        "ActionReunionDB", back_populates="reunion",
        cascade="all, delete-orphan", order_by="ActionReunionDB.id",
    )


class ActionReunionDB(Base):
    __tablename__ = "actions_reunions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    reunion_id = Column(String, ForeignKey("reunions.id", ondelete="CASCADE"), index=True)
    responsable = Column(String, nullable=False)
    description = Column(Text, nullable=False)
    echeance = Column(DateTime, nullable=True)
    statut = Column(String, default="en_attente")
    priorite = Column(String, default="normale")

    reunion = relationship("ReunionDB", back_populates="actions")


# ─── AUDIT TRAIL ──────────────────────────────────────────────────────────────

class AuditLogDB(Base):
    __tablename__ = "audit_logs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    timestamp = Column(DateTime, default=datetime.utcnow, index=True)
    compagnie_id = Column(Integer, default=1, index=True)     # multitenancy
    user_id = Column(Integer, nullable=True, index=True)
    user_nom = Column(String, nullable=True)
    action = Column(String, index=True)           # "chat_message" | "generation_doc" | ...
    module = Column(String, index=True)           # "chat" | "sinistres" | "documents" | ...
    resource_type = Column(String, nullable=True) # "session" | "sinistre" | "reunion" | ...
    resource_id = Column(String, nullable=True, index=True)
    details = Column(JSON, nullable=True)
    ip_address = Column(String, nullable=True)
    duree_ms = Column(Float, nullable=True)
    succes = Column(Boolean, default=True)
    erreur = Column(Text, nullable=True)


# ─── COÛTS IA (tracking tokens / coûts API) ───────────────────────────────────

class CoutIADB(Base):
    """Suivi des coûts d'utilisation des APIs IA par utilisateur et modèle."""
    __tablename__ = "couts_ia"

    id = Column(Integer, primary_key=True, autoincrement=True)
    timestamp = Column(DateTime, default=datetime.utcnow, index=True)
    compagnie_id = Column(Integer, default=1, index=True)
    user_id = Column(Integer, nullable=True, index=True)
    modele = Column(String, nullable=False, index=True)   # "claude-opus-4-6" | "gpt-4o" | ...
    module = Column(String, nullable=True, index=True)    # "chat" | "sinistres" | ...
    tokens_input = Column(Integer, default=0)
    tokens_output = Column(Integer, default=0)
    cout_estime_usd = Column(Float, default=0.0)          # Coût estimé en USD
    session_id = Column(String, nullable=True, index=True)


# ─── DOSSIERS (index des pièces de l'entreprise) ─────────────────────────────

class DossierIndexDB(Base):
    """
    Index des dossiers de l'entreprise pour la recherche contextuelle du chat.
    Stocke les références et un résumé textuel pour la recherche sémantique.
    """
    __tablename__ = "dossiers_index"

    id = Column(Integer, primary_key=True, autoincrement=True)
    type_dossier = Column(String, index=True)        # "sinistre" | "contrat" | "courrier" | "reunion"
    reference = Column(String, index=True, unique=True)
    titre = Column(String, nullable=False)
    contenu_indexe = Column(Text, nullable=True)     # Texte extrait pour la recherche
    meta_donnees = Column(JSON, default=dict)
    cree_par_user_id = Column(Integer, nullable=True)
    cree_par_nom = Column(String, nullable=True)
    cree_le = Column(DateTime, default=datetime.utcnow, index=True)
    mise_a_jour = Column(DateTime, default=datetime.utcnow)


# ─── PROFIL COMPAGNIE (multi-tenant / multi-secteur) ─────────────────────────

class CompagnieDB(Base):
    """
    Profil complet d'une compagnie cliente.
    Porte le secteur d'activité, les informations légales, et la config WhatsApp/paiement.
    """
    __tablename__ = "compagnies"

    id = Column(Integer, primary_key=True, autoincrement=True)
    # Identité légale
    nom = Column(String, nullable=False)
    sigle = Column(String, nullable=True)
    secteur = Column(String, default="assurance", index=True)  # assurance | banque | ecole | ...
    pays = Column(String, default="CM")           # Code ISO pays
    ville = Column(String, nullable=True)
    adresse = Column(String, nullable=True)
    telephone = Column(String, nullable=True)
    email = Column(String, nullable=True)
    site_web = Column(String, nullable=True)
    # Documents légaux
    numero_rccm = Column(String, nullable=True)
    numero_contribuable = Column(String, nullable=True)
    numero_agrement = Column(String, nullable=True)  # Pour assurances : numéro agrément CRCA
    capital_social = Column(Float, default=0)
    # Logo (URL ou chemin relatif)
    logo_url = Column(String, nullable=True)
    # Textes légaux pour contrats
    mentions_legales = Column(Text, nullable=True)
    # Config WhatsApp Business
    whatsapp_phone_id = Column(String, nullable=True)
    whatsapp_token = Column(String, nullable=True)
    whatsapp_verify_token = Column(String, nullable=True)
    # Config paiement
    mtn_momo_api_key = Column(String, nullable=True)
    orange_money_api_key = Column(String, nullable=True)
    cinetpay_api_key = Column(String, nullable=True)
    cinetpay_site_id = Column(String, nullable=True)
    webhook_secret = Column(String, nullable=True)   # HMAC-SHA256 pour vérification webhooks paiement
    # SMTP pour envoi emails
    smtp_host = Column(String, nullable=True)
    smtp_port = Column(Integer, default=587)
    smtp_user = Column(String, nullable=True)
    smtp_password = Column(String, nullable=True)
    smtp_from = Column(String, nullable=True)
    # Méta
    actif = Column(Boolean, default=True)
    plan_abonnement = Column(String, default="starter")  # starter | pro | enterprise
    cree_le = Column(DateTime, default=datetime.utcnow)
    mise_a_jour = Column(DateTime, default=datetime.utcnow)


# ─── SESSIONS WHATSAPP ────────────────────────────────────────────────────────

class SessionWhatsAppDB(Base):
    """
    Session de conversation WhatsApp par numéro de téléphone client.
    Stocke l'état de la machine à états pour reprendre la conversation.
    """
    __tablename__ = "sessions_whatsapp"

    id = Column(Integer, primary_key=True, autoincrement=True)
    compagnie_id = Column(Integer, index=True, nullable=False)
    numero_client = Column(String, nullable=False, index=True)  # +237600000000
    nom_client = Column(String, nullable=True)
    etat = Column(String, default="accueil")      # accueil | devis | sinistre | suivi | paiement
    sous_etat = Column(String, nullable=True)
    contexte = Column(JSON, default=dict)          # données collectées au fil de la conv
    langue = Column(String, default="fr")
    dernier_message = Column(DateTime, nullable=True)
    cree_le = Column(DateTime, default=datetime.utcnow)
    mise_a_jour = Column(DateTime, default=datetime.utcnow)


# ─── TRANSACTIONS PAIEMENT ────────────────────────────────────────────────────

class TransactionPaiementDB(Base):
    __tablename__ = "transactions_paiement"

    id = Column(Integer, primary_key=True, autoincrement=True)
    compagnie_id = Column(Integer, index=True, nullable=False)
    reference = Column(String, unique=True, index=True, nullable=False)
    type_paiement = Column(String, nullable=False)   # "prime" | "acompte" | "solde" | "scolarite"
    operateur = Column(String, nullable=True)          # "mtn_momo" | "orange_money" | "cinetpay" | "wave"
    montant = Column(Float, nullable=False)
    devise = Column(String, default="XAF")
    numero_payeur = Column(String, nullable=True)      # Numéro mobile du payeur
    nom_payeur = Column(String, nullable=True)
    reference_externe = Column(String, nullable=True)  # ID transaction opérateur
    reference_police = Column(String, nullable=True)   # Numéro de police concernée
    statut = Column(String, default="en_attente", index=True)
    # en_attente | initie | en_cours | reussi | echoue | annule | rembourse
    message_retour = Column(Text, nullable=True)
    metadata_operateur = Column(JSON, default=dict)
    cree_le = Column(DateTime, default=datetime.utcnow, index=True)
    mise_a_jour = Column(DateTime, default=datetime.utcnow)
    paye_le = Column(DateTime, nullable=True)


# ─── RESSOURCES HUMAINES ──────────────────────────────────────────────────────

class EmployeDB(Base):
    __tablename__ = "employes"

    id = Column(Integer, primary_key=True, autoincrement=True)
    compagnie_id = Column(Integer, index=True, nullable=False)
    # Identité
    nom = Column(String, nullable=False)
    prenom = Column(String, nullable=True)
    email = Column(String, nullable=True)
    telephone = Column(String, nullable=True)
    # Poste
    departement = Column(String, nullable=True, index=True)
    poste = Column(String, nullable=True)
    statut = Column(String, default="actif", index=True)  # actif | conge | demissionnaire | licencie
    # Paie
    salaire_brut = Column(Float, default=0)
    date_embauche = Column(DateTime, nullable=True)
    # Méta
    cree_le = Column(DateTime, default=datetime.utcnow)
    mise_a_jour = Column(DateTime, default=datetime.utcnow)

    conges = relationship("CongeDB", back_populates="employe", cascade="all, delete-orphan")
    evaluations = relationship("EvaluationDB", back_populates="employe", cascade="all, delete-orphan")


class CongeDB(Base):
    __tablename__ = "conges"

    id = Column(Integer, primary_key=True, autoincrement=True)
    compagnie_id = Column(Integer, index=True, nullable=False)
    employe_id = Column(Integer, ForeignKey("employes.id", ondelete="CASCADE"), index=True)
    type_conge = Column(String, default="annuel")   # annuel | maladie | maternite | paternite | sans_solde
    date_debut = Column(DateTime, nullable=False)
    date_fin = Column(DateTime, nullable=False)
    nb_jours = Column(Float, default=0)
    motif = Column(Text, nullable=True)
    statut = Column(String, default="en_attente", index=True)  # en_attente | approuve | refuse
    approuve_par_id = Column(Integer, nullable=True)
    approuve_par_nom = Column(String, nullable=True)
    commentaire_rh = Column(Text, nullable=True)
    cree_le = Column(DateTime, default=datetime.utcnow)
    mise_a_jour = Column(DateTime, default=datetime.utcnow)

    employe = relationship("EmployeDB", back_populates="conges")


class EvaluationDB(Base):
    __tablename__ = "evaluations"

    id = Column(Integer, primary_key=True, autoincrement=True)
    compagnie_id = Column(Integer, index=True, nullable=False)
    employe_id = Column(Integer, ForeignKey("employes.id", ondelete="CASCADE"), index=True)
    evaluateur_id = Column(Integer, nullable=True)
    evaluateur_nom = Column(String, nullable=True)
    periode = Column(String, nullable=True)        # "2024-T1" | "2024-annuel"
    notes = Column(JSON, default=dict)             # {critere: note/5}
    score_global = Column(Float, default=0)
    mention = Column(String, nullable=True)
    commentaire = Column(Text, nullable=True)
    cree_le = Column(DateTime, default=datetime.utcnow)

    employe = relationship("EmployeDB", back_populates="evaluations")


class RecrutementDB(Base):
    __tablename__ = "recrutements"

    id = Column(Integer, primary_key=True, autoincrement=True)
    compagnie_id = Column(Integer, index=True, nullable=False)
    poste = Column(String, nullable=False)
    departement = Column(String, nullable=True)
    description = Column(Text, nullable=True)
    salaire_min = Column(Float, default=0)
    salaire_max = Column(Float, default=0)
    statut = Column(String, default="ouvert", index=True)   # ouvert | en_cours | cloture | annule
    nb_candidats = Column(Integer, default=0)
    date_limite = Column(DateTime, nullable=True)
    cree_par_id = Column(Integer, nullable=True)
    cree_le = Column(DateTime, default=datetime.utcnow)
    mise_a_jour = Column(DateTime, default=datetime.utcnow)


# ─── COMMERCIAL ───────────────────────────────────────────────────────────────

class ProspectDB(Base):
    __tablename__ = "prospects"

    id = Column(Integer, primary_key=True, autoincrement=True)
    compagnie_id = Column(Integer, index=True, nullable=False)
    agent_id = Column(Integer, nullable=True, index=True)
    agent_nom = Column(String, nullable=True)
    # Identité
    nom = Column(String, nullable=False)
    prenom = Column(String, nullable=True)
    telephone = Column(String, nullable=True)
    email = Column(String, nullable=True)
    # Pipeline
    source = Column(String, default="appel_entrant")
    branche_interesse = Column(String, nullable=True, index=True)
    statut = Column(String, default="nouveau", index=True)
    score = Column(Float, default=0)
    niveau_qualification = Column(String, default="froid")   # froid | tiède | chaud
    # Données commerciales
    deja_assure = Column(Boolean, default=False)
    budget_fcfa = Column(Float, default=0)
    delai_decision_jours = Column(Integer, default=30)
    notes = Column(Text, nullable=True)
    dernier_contact = Column(DateTime, nullable=True)
    # Méta
    cree_le = Column(DateTime, default=datetime.utcnow)
    mise_a_jour = Column(DateTime, default=datetime.utcnow)


class ObjectifCommercialDB(Base):
    __tablename__ = "objectifs_commerciaux"

    id = Column(Integer, primary_key=True, autoincrement=True)
    compagnie_id = Column(Integer, index=True, nullable=False)
    agent_id = Column(Integer, nullable=True, index=True)
    annee = Column(Integer, nullable=False, index=True)
    mois = Column(Integer, nullable=False)
    type_objectif = Column(String, nullable=False)    # primes | contrats | prospects
    valeur_cible = Column(Float, nullable=False)
    valeur_atteinte = Column(Float, default=0)
    description = Column(Text, nullable=True)
    cree_par_id = Column(Integer, nullable=True)
    cree_le = Column(DateTime, default=datetime.utcnow)
    mise_a_jour = Column(DateTime, default=datetime.utcnow)


class CampagneDB(Base):
    __tablename__ = "campagnes"

    id = Column(Integer, primary_key=True, autoincrement=True)
    compagnie_id = Column(Integer, index=True, nullable=False)
    nom = Column(String, nullable=False)
    type_campagne = Column(String, nullable=False)   # renouvellement | fidelisation | acquisition | cross_selling
    description = Column(Text, nullable=True)
    date_debut = Column(DateTime, nullable=False)
    date_fin = Column(DateTime, nullable=False)
    cibles = Column(JSON, default=list)
    budget_fcfa = Column(Float, default=0)
    statut = Column(String, default="planifiee", index=True)   # planifiee | active | terminee | annulee
    nb_contacts = Column(Integer, default=0)
    nb_conversions = Column(Integer, default=0)
    cree_par_id = Column(Integer, nullable=True)
    cree_le = Column(DateTime, default=datetime.utcnow)
    mise_a_jour = Column(DateTime, default=datetime.utcnow)


# ─── COLLABORATION DOCUMENTAIRE ───────────────────────────────────────────────

class DocumentCollabDB(Base):
    __tablename__ = "documents_collab"

    id = Column(Integer, primary_key=True, autoincrement=True)
    compagnie_id = Column(Integer, index=True, nullable=False)
    reference = Column(String, unique=True, index=True, nullable=False)
    titre = Column(String, nullable=False)
    type_document = Column(String, nullable=False, index=True)
    description = Column(Text, nullable=True)
    # Contenu (stockage référence fichier ou texte)
    contenu_url = Column(String, nullable=True)
    contenu_texte = Column(Text, nullable=True)
    montant_concerne = Column(Float, default=0)
    # Workflow
    statut = Column(String, default="brouillon", index=True)
    # brouillon | en_review | approuve | rejete | archive
    type_workflow = Column(String, default="simple")
    etapes_workflow = Column(JSON, default=list)
    etape_courante = Column(Integer, default=0)
    # Auteur
    auteur_id = Column(Integer, nullable=False, index=True)
    auteur_nom = Column(String, nullable=False)
    # Version courante
    version_courante = Column(Integer, default=1)
    historique = Column(JSON, default=list)
    # Méta
    cree_le = Column(DateTime, default=datetime.utcnow)
    mise_a_jour = Column(DateTime, default=datetime.utcnow)

    versions = relationship("VersionDocDB", back_populates="document", cascade="all, delete-orphan")
    commentaires = relationship("CommentaireDocDB", back_populates="document", cascade="all, delete-orphan")


class VersionDocDB(Base):
    __tablename__ = "versions_docs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    document_id = Column(Integer, ForeignKey("documents_collab.id", ondelete="CASCADE"), index=True)
    numero_version = Column(Integer, nullable=False)
    contenu_url = Column(String, nullable=True)
    contenu_texte = Column(Text, nullable=True)
    modifie_par_id = Column(Integer, nullable=False)
    modifie_par_nom = Column(String, nullable=False)
    commentaire = Column(Text, nullable=True)
    cree_le = Column(DateTime, default=datetime.utcnow)

    document = relationship("DocumentCollabDB", back_populates="versions")


class WorkflowApprovalDB(Base):
    __tablename__ = "workflow_approvals"

    id = Column(Integer, primary_key=True, autoincrement=True)
    document_id = Column(Integer, ForeignKey("documents_collab.id", ondelete="CASCADE"), index=True)
    etape = Column(Integer, nullable=False)
    approbateur_id = Column(Integer, nullable=False, index=True)
    approbateur_nom = Column(String, nullable=False)
    approbateur_role = Column(String, nullable=True)
    statut = Column(String, default="en_attente")   # en_attente | bloquee | approuve | rejete
    commentaire = Column(Text, nullable=True)
    date_action = Column(DateTime, nullable=True)


class CommentaireDocDB(Base):
    __tablename__ = "commentaires_docs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    document_id = Column(Integer, ForeignKey("documents_collab.id", ondelete="CASCADE"), index=True)
    auteur_id = Column(Integer, nullable=False)
    auteur_nom = Column(String, nullable=False)
    contenu = Column(Text, nullable=False)
    cree_le = Column(DateTime, default=datetime.utcnow)

    document = relationship("DocumentCollabDB", back_populates="commentaires")


class NotificationDB(Base):
    __tablename__ = "notifications"

    id = Column(Integer, primary_key=True, autoincrement=True)
    compagnie_id = Column(Integer, index=True, nullable=False)
    user_id = Column(Integer, nullable=False, index=True)
    type_notif = Column(String, nullable=False)      # "approbation_requise" | "document_approuve" | "commentaire" | ...
    titre = Column(String, nullable=False)
    message = Column(Text, nullable=True)
    lien = Column(String, nullable=True)             # ex: "/collaboration/documents/42"
    lu = Column(Boolean, default=False, index=True)
    cree_le = Column(DateTime, default=datetime.utcnow, index=True)


# ─── COMMUNITY MANAGER ───────────────────────────────────────────────────────

class PostSocialDB(Base):
    """Post généré par l'IA pour les réseaux sociaux."""
    __tablename__ = "posts_social"

    id = Column(Integer, primary_key=True, autoincrement=True)
    compagnie_id = Column(Integer, ForeignKey("compagnies.id"), nullable=False, index=True)
    plateforme = Column(String, nullable=False, index=True)   # facebook | instagram | linkedin | twitter | whatsapp | tiktok
    type_contenu = Column(String, default="produit")           # produit | promo | actualite | sinistre | conseil | campagne
    sujet = Column(String, nullable=True)                      # contexte métier (ex: "Assurance Auto")
    legende = Column(Text, nullable=False)                     # texte principal
    legende_variante_b = Column(Text, nullable=True)           # variante A/B test
    hashtags = Column(JSON, default=list)
    image_url = Column(String, nullable=True)
    lien_url = Column(String, nullable=True)
    ton = Column(String, default="professionnel")              # professionnel | decontracte | promotionnel | urgent
    langue = Column(String, default="fr")
    statut = Column(String, default="brouillon", index=True)  # brouillon | planifie | publie | echoue | annule
    planifie_le = Column(DateTime, nullable=True, index=True)
    publie_le = Column(DateTime, nullable=True)
    id_post_externe = Column(String, nullable=True)            # ID Meta/LinkedIn
    modele_ia = Column(String, default="claude-opus-4-6")
    prompt_generation = Column(Text, nullable=True)
    # A/B analytics
    engagement_a = Column(Integer, default=0)
    engagement_b = Column(Integer, default=0)
    ab_gagnant = Column(String, nullable=True)                 # 'A' | 'B'
    # Publication
    retry_count = Column(Integer, default=0)
    external_post_id = Column(String, nullable=True)           # alias exposé (id_post_externe = legacy)
    # Meta
    cree_par = Column(String, nullable=True)
    cree_le = Column(DateTime, default=datetime.utcnow, index=True)
    message_erreur = Column(Text, nullable=True)
    error_message = Column(Text, nullable=True)                # alias anglais pour compat scheduler


class PreferencesCMDB(Base):
    """Préférences Community Manager par compagnie."""
    __tablename__ = "preferences_cm"

    id = Column(Integer, primary_key=True, autoincrement=True)
    compagnie_id = Column(Integer, ForeignKey("compagnies.id"), nullable=False, unique=True)
    voix_marque = Column(Text, nullable=True)                   # description du ton/identité
    mots_interdits = Column(JSON, default=list)
    toujours_inclure = Column(JSON, default=list)               # ex: numéro de tél, site web
    hashtags_defaut = Column(JSON, default=list)
    heures_publication = Column(JSON, default=lambda: [8, 12, 18])  # heures optimales
    plateformes_actives = Column(JSON, default=dict)
    max_posts_par_jour = Column(Integer, default=3)
    ab_test_auto = Column(Boolean, default=True)
    secteur_contenu = Column(String, default="assurance")
    modele_ia_prefere = Column(String, default="claude-opus-4-6")
    mise_a_jour_le = Column(DateTime, default=datetime.utcnow)


class AnalyticsPostDB(Base):
    """Analytics d'un post publié."""
    __tablename__ = "analytics_posts"

    id = Column(Integer, primary_key=True, autoincrement=True)
    post_id = Column(Integer, ForeignKey("posts_social.id", ondelete="CASCADE"), nullable=True)
    compagnie_id = Column(Integer, ForeignKey("compagnies.id"), nullable=False, index=True)
    plateforme = Column(String, nullable=False, index=True)
    impressions = Column(Integer, default=0)
    portee = Column(Integer, default=0)
    likes = Column(Integer, default=0)
    commentaires = Column(Integer, default=0)
    partages = Column(Integer, default=0)
    clics = Column(Integer, default=0)
    conversions = Column(Integer, default=0)           # devis/contacts générés
    # Engagement calculé
    taux_engagement = Column(Float, nullable=True)
    effectiveness_score = Column(Float, nullable=True)
    # ROAS
    commandes_attribuees = Column(Integer, default=0)
    revenus_attribues_fcfa = Column(Integer, default=0)
    # Date de publication (copie dénormalisée depuis PostSocialDB pour les agrégats)
    publie_le = Column(DateTime, nullable=True, index=True)
    recupere_le = Column(DateTime, default=datetime.utcnow)


class SocialConnectorDB(Base):
    """Connexion OAuth d'un compte social par compagnie (Facebook Page, Instagram Business…)."""
    __tablename__ = "social_connectors"

    id = Column(Integer, primary_key=True, autoincrement=True)
    compagnie_id = Column(Integer, ForeignKey("compagnies.id"), nullable=False, index=True)
    plateforme = Column(String, nullable=False, index=True)    # facebook | instagram | linkedin | twitter | tiktok
    account_id = Column(String, nullable=True)                 # page_id ou user_id externe
    account_nom = Column(String, nullable=True)                # nom de la page/compte
    metadata_json = Column(JSON, default=dict)                 # page_access_token, page_id, ig_user_id, …
    est_actif = Column(Boolean, default=True, index=True)
    connecte_le = Column(DateTime, default=datetime.utcnow)
    expire_le = Column(DateTime, nullable=True)                # expiration du token si connue
    cree_par = Column(String, nullable=True)


# ─── TRENDS / VEILLE MARCHÉ ──────────────────────────────────────────────────

class TrendSnapshotDB(Base):
    """Snapshot historique d'une tendance de marché."""
    __tablename__ = "trend_snapshots"

    id = Column(Integer, primary_key=True, autoincrement=True)
    compagnie_id = Column(Integer, ForeignKey("compagnies.id"), nullable=True, index=True)  # null = global
    region = Column(String, nullable=False, index=True)         # CM | SN | CI | NG | ALL
    periode = Column(String, default="24h")                     # 24h | 7d | 30d
    sujet = Column(Text, nullable=False, index=True)
    score_social = Column(Float, default=0.0)
    score_commerce = Column(Float, default=0.0)
    score_opportunite = Column(Float, default=0.0)
    momentum_pct = Column(Float, default=0.0)                   # évolution en %
    categories = Column(JSON, default=list)                     # ["assurance", "automobile", ...]
    sources = Column(JSON, default=list)                        # ["google", "twitter", ...]
    snapshot_le = Column(DateTime, default=datetime.utcnow, index=True)


class AlerteTrendDB(Base):
    """Alerte envoyée sur une tendance (évite doublons 24h)."""
    __tablename__ = "alertes_trends"

    id = Column(Integer, primary_key=True, autoincrement=True)
    compagnie_id = Column(Integer, ForeignKey("compagnies.id"), nullable=False)
    sujet = Column(Text, nullable=False)
    region = Column(String, nullable=False)
    score_opportunite = Column(Float, nullable=False)
    envoyee_le = Column(DateTime, default=datetime.utcnow, index=True)


class BrouillonTrendDB(Base):
    """Brouillon de post généré automatiquement depuis une tendance."""
    __tablename__ = "brouillons_trends"

    id = Column(Integer, primary_key=True, autoincrement=True)
    compagnie_id = Column(Integer, ForeignKey("compagnies.id"), nullable=False, index=True)
    region = Column(String, nullable=False)
    sujet = Column(String, nullable=False)
    score_opportunite = Column(Float, nullable=False)
    brouillon_facebook = Column(Text, nullable=True)
    brouillon_instagram = Column(Text, nullable=True)
    brouillon_linkedin = Column(Text, nullable=True)
    brouillon_whatsapp = Column(Text, nullable=True)
    statut = Column(String, default="brouillon")               # brouillon | publie | rejete
    post_id = Column(Integer, ForeignKey("posts_social.id"), nullable=True)
    genere_le = Column(DateTime, default=datetime.utcnow, index=True)


# ─── AGENDA & RAPPELS EMPLOYÉS ───────────────────────────────────────────────

class EvenementAgendaDB(Base):
    """Événement / rendez-vous dans l'agenda d'un employé."""
    __tablename__ = "evenements_agenda"

    id = Column(Integer, primary_key=True, autoincrement=True)
    compagnie_id = Column(Integer, ForeignKey("compagnies.id"), nullable=False, index=True)
    employe_id = Column(Integer, nullable=False, index=True)    # référence EmployeDB
    titre = Column(String, nullable=False)
    description = Column(Text, nullable=True)
    type_evenement = Column(String, default="rendez_vous")      # rendez_vous | reunion | echeance | tache | rappel | conge
    date_debut = Column(DateTime, nullable=False, index=True)
    date_fin = Column(DateTime, nullable=True)
    toute_la_journee = Column(Boolean, default=False)
    lieu = Column(String, nullable=True)
    lien_visio = Column(String, nullable=True)
    recurrence = Column(String, nullable=True)                  # null | quotidien | hebdomadaire | mensuel
    couleur = Column(String, default="#003366")
    # Participants (autres employés)
    participants = Column(JSON, default=list)                   # liste d'employe_id
    # Rappels
    rappels = Column(JSON, default=lambda: [30])               # délais en minutes avant l'événement
    # Liaison avec d'autres modules
    lien_sinistre = Column(Integer, nullable=True)
    lien_contrat = Column(Integer, nullable=True)
    lien_reunion = Column(String, nullable=True)
    # Statut
    statut = Column(String, default="planifie")                # planifie | termine | annule | reporte
    cree_par = Column(String, nullable=True)
    cree_le = Column(DateTime, default=datetime.utcnow)
    mis_a_jour_le = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class TacheDB(Base):
    """Tâche assignée à un employé avec suivi et rappels."""
    __tablename__ = "taches"

    id = Column(Integer, primary_key=True, autoincrement=True)
    compagnie_id = Column(Integer, ForeignKey("compagnies.id"), nullable=False, index=True)
    titre = Column(String, nullable=False)
    description = Column(Text, nullable=True)
    assigne_a = Column(Integer, nullable=False, index=True)    # employe_id
    assigne_par = Column(String, nullable=True)
    priorite = Column(String, default="normale")               # basse | normale | haute | urgente
    statut = Column(String, default="a_faire", index=True)    # a_faire | en_cours | bloquee | terminee | annulee
    date_echeance = Column(DateTime, nullable=True, index=True)
    date_debut_prevue = Column(DateTime, nullable=True)
    date_completion = Column(DateTime, nullable=True)
    avancement_pct = Column(Integer, default=0)               # 0-100
    # Rappels automatiques
    rappel_j_moins = Column(Integer, default=1)               # rappel X jours avant échéance
    rappel_envoye = Column(Boolean, default=False)
    # Liaisons modules
    lien_sinistre = Column(Integer, nullable=True)
    lien_contrat = Column(Integer, nullable=True)
    lien_police = Column(String, nullable=True)
    # Tags
    tags = Column(JSON, default=list)
    pieces_jointes = Column(JSON, default=list)               # URLs fichiers liés
    commentaires = Column(JSON, default=list)                 # [{auteur, texte, date}]
    cree_le = Column(DateTime, default=datetime.utcnow, index=True)
    mis_a_jour_le = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class RappelDB(Base):
    """Rappel envoyé (email/WhatsApp/notification push) — évite doublons."""
    __tablename__ = "rappels_envoyes"

    id = Column(Integer, primary_key=True, autoincrement=True)
    compagnie_id = Column(Integer, ForeignKey("compagnies.id"), nullable=False)
    employe_id = Column(Integer, nullable=False, index=True)
    type_source = Column(String, nullable=False)              # tache | evenement | echeance_contrat | sinistre
    source_id = Column(Integer, nullable=False)               # ID de l'entité source
    canal = Column(String, nullable=False)                    # email | whatsapp | push | sms
    message = Column(Text, nullable=False)
    envoye_le = Column(DateTime, default=datetime.utcnow, index=True)
    statut = Column(String, default="envoye")                 # envoye | echoue | lu


# ─── SIGNATURES ÉLECTRONIQUES ────────────────────────────────────────────────

class SignatureDB(Base):
    """Audit trail des signatures électroniques de documents."""
    __tablename__ = "signatures_electroniques"

    id = Column(Integer, primary_key=True, autoincrement=True)
    signature_id = Column(String, unique=True, nullable=False, index=True)
    hash_sha256 = Column(String(64), nullable=False)
    timestamp_utc = Column(String, nullable=False)
    user_id = Column(Integer, nullable=False, index=True)
    signataire_nom = Column(String, nullable=False)
    signataire_role = Column(String, nullable=True)
    compagnie_id = Column(Integer, ForeignKey("compagnies.id"), nullable=True)
    manifest_json = Column(Text, nullable=False)
    cree_le = Column(DateTime, default=datetime.utcnow)


# ─── DOCUMENTS GÉNÉRÉS (historique YukpoPro + YukpoAssurance) ────────────────

class DocumentGenereDB(Base):
    """
    Historique des documents générés par l'IA (rapports, slides, traductions).
    Partagé entre YukpoPro et YukpoAssurance pour l'amélioration itérative via chat.
    """
    __tablename__ = "documents_generes"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, nullable=False, index=True)
    compagnie_id = Column(Integer, nullable=True, index=True)
    titre = Column(String(300), nullable=False)
    type_doc = Column(String(50), nullable=False, index=True)  # rapport | slides | traduction | autre
    fichier = Column(String(300), nullable=True)               # nom du fichier généré (DOCX/PPTX/PDF)
    contenu_source = Column(Text, nullable=True)               # prompt / demande initiale
    contenu_genere = Column(Text, nullable=True)               # aperçu markdown / texte traduit
    session_id = Column(String(100), nullable=True, index=True) # session chat liée
    meta = Column(JSON, default=dict)                          # langue_source, langue_cible, type_rapport…
    cree_le = Column(DateTime, default=datetime.utcnow, index=True)
    modifie_le = Column(DateTime, default=datetime.utcnow)


# ─── TOKENS IA / CRÉDITS YUKPOPRO ─────────────────────────────────────────────

class CreditIAUserDB(Base):
    """
    Solde de crédits IA par utilisateur YukpoPro.
    1 crédit Yukpo = 200× le coût réel en token converti en FCFA.
    Se renouvelle chaque mois selon le plan d'abonnement.
    """
    __tablename__ = "credits_ia_users"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, nullable=False, unique=True, index=True)
    plan = Column(String(50), nullable=False, default="gratuit")
    credits_alloues = Column(Integer, default=500)      # crédits mensuels selon plan
    credits_utilises = Column(Integer, default=0)       # consommés ce mois
    periode_debut = Column(DateTime, default=datetime.utcnow)
    periode_fin = Column(DateTime, nullable=True)
    mise_a_jour = Column(DateTime, default=datetime.utcnow)


class ConsommationTokenDB(Base):
    """
    Log détaillé de chaque consommation de tokens par appel IA.
    Permet le calcul exact des crédits débités en FCFA×200.
    """
    __tablename__ = "consommations_tokens"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, nullable=False, index=True)
    modele = Column(String(100), nullable=False)            # claude-sonnet-4-6 | gpt-4o | …
    tokens_input = Column(Integer, default=0)
    tokens_output = Column(Integer, default=0)
    cout_usd = Column(Float, default=0.0)                   # coût réel USD
    cout_fcfa = Column(Float, default=0.0)                  # coût réel FCFA (1 USD = 600 FCFA)
    credits_debites = Column(Float, default=0.0)            # crédits Yukpo déduits (200× cout_fcfa)
    module = Column(String(100), nullable=True)             # chat | traduction | rapport | slides
    session_id = Column(String(100), nullable=True)
    app_origine = Column(String(10), nullable=False, default="pro", index=True)  # pro | sec
    cree_le = Column(DateTime, default=datetime.utcnow, index=True)


# ─── BUREAU SECRÉTARIAT ───────────────────────────────────────────────────────

class BureauBonTravailDB(Base):
    """Bon de travail Kanban pour le secrétariat."""
    __tablename__ = "bureau_bons_travail"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, nullable=False, index=True)
    client_nom = Column(String(200), nullable=False)
    client_whatsapp = Column(String(30), nullable=True, index=True)  # +237xxx — obligatoire pour notif fin
    description = Column(Text, nullable=False)
    type_travail = Column(String(50), default="redaction_doc")
    # redaction_doc | scan | infographie | impression | saisie | traduction | autre
    statut = Column(String(30), default="en_attente", index=True)  # en_attente|en_cours|en_revision|livre|paye|annule
    montant_fcfa = Column(Integer, default=0)
    acompte_fcfa = Column(Integer, default=0)
    echeance = Column(DateTime, nullable=True)
    notes = Column(Text, default="")
    notif_fin_envoyee = Column(Boolean, default=False)  # WA envoyé à la fin
    notif_fin_horodatage = Column(DateTime, nullable=True)
    cree_le = Column(DateTime, default=datetime.utcnow, index=True)
    modifie_le = Column(DateTime, default=datetime.utcnow)


class BureauTransactionDB(Base):
    """Transaction de caisse journalière du secrétariat."""
    __tablename__ = "bureau_transactions_caisse"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, nullable=False, index=True)
    type = Column(String(10), nullable=False)               # entree | sortie
    montant_fcfa = Column(Integer, nullable=False)
    libelle = Column(String(300), nullable=False)
    mode_paiement = Column(String(30), default="especes")   # especes|orange_money|mtn_momo|virement|cheque
    reference = Column(String(100), nullable=True)
    horodatage = Column(DateTime, default=datetime.utcnow, index=True)


class BureauClientDB(Base):
    """Fiche client du mini-CRM secrétariat."""
    __tablename__ = "bureau_clients"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, nullable=False, index=True)
    nom = Column(String(200), nullable=False, index=True)
    telephone = Column(String(30), nullable=False)
    email = Column(String(150), nullable=True)
    adresse = Column(String(300), nullable=True)
    notes = Column(Text, default="")
    nb_commandes = Column(Integer, default=0)
    total_paye_fcfa = Column(Integer, default=0)
    derniere_visite = Column(DateTime, nullable=True)
    cree_le = Column(DateTime, default=datetime.utcnow, index=True)


# ─── CRÉDITS BUREAU SECRÉTARIAT ──────────────────────────────────────────────

class CreditBureauDB(Base):
    """
    Solde de crédits Bureau par utilisateur YukpoSecrétariat.
    Plans : gratuit (1 000) / secretariat (20 000) / infographie (20 000) / complet (50 000).
    Séparé de CreditIAUserDB pour ne pas interférer avec les plans YukpoPro.
    """
    __tablename__ = "credits_bureau"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, nullable=False, unique=True, index=True)
    plan = Column(String(50), nullable=False, default="gratuit")
    credits_alloues = Column(Integer, default=1000)
    credits_utilises = Column(Float, default=0.0)
    periode_debut = Column(DateTime, default=datetime.utcnow)
    periode_fin = Column(DateTime, nullable=True)
    mise_a_jour = Column(DateTime, default=datetime.utcnow)


class ConsommationBureauDB(Base):
    """Log de consommation par appel bureau (LLM + forfaits non-LLM)."""
    __tablename__ = "consommations_bureau"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, nullable=False, index=True)
    modele = Column(String(100), nullable=False, default="forfait")
    tokens_input = Column(Integer, default=0)
    tokens_output = Column(Integer, default=0)
    cout_usd = Column(Float, default=0.0)
    cout_fcfa = Column(Float, default=0.0)
    credits_debites = Column(Float, default=0.0)
    module = Column(String(100), nullable=True)   # redaction|ocr|audio|traduction|infographie|gestion
    app_origine = Column(String(10), nullable=False, default="sec", index=True)  # pro | sec
    cree_le = Column(DateTime, default=datetime.utcnow, index=True)


class CommandePaiementDB(Base):
    """
    Commande de paiement MoMo (abonnement ou recharge de crédits).
    Activation provisoire immédiate, validée manuellement ou via auto-match
    de relevé uploadé par l'admin dans les 3h.
    """
    __tablename__ = "commandes_paiement"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, nullable=False, index=True)
    reference = Column(String(40), nullable=False, unique=True, index=True)
    type = Column(String(20), nullable=False)          # abonnement | recharge
    plan_ou_pack = Column(String(50), nullable=False)   # starter|pro|business|pack_500|...
    montant_fcfa = Column(Integer, nullable=False)
    operateur = Column(String(40), nullable=True)
    numero_destinataire = Column(String(30), nullable=True)  # n° marchand YukpoPro
    numero_expediteur = Column(String(30), nullable=True)    # n° payeur (requis à la confirmation)
    tx_id = Column(String(80), nullable=True)
    statut = Column(String(20), nullable=False, default="attente", index=True)
    # attente | provisoire | valide | rejete | annule
    motif_rejet = Column(String(300), nullable=True)
    valide_par = Column(Integer, nullable=True)         # user_id admin
    valide_le = Column(DateTime, nullable=True)
    match_source = Column(String(30), nullable=True)    # manuel | releve_ia | cron
    cree_le = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)
    deadline = Column(DateTime, nullable=False)


# ─── PAIEMENT v2 — multi-provider unifié ──────────────────────────────────────

class WalletYukpoProDB(Base):
    """Portefeuille interne YukpoPro (crédits IA + cash optionnel)."""
    __tablename__ = "wallet_yukpopro"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    compagnie_id = Column(BigInteger, nullable=False, index=True)
    user_id = Column(BigInteger, nullable=True, index=True)
    solde_credits_yukpo = Column(BigInteger, nullable=False, default=0)
    solde_cash_fcfa = Column(BigInteger, nullable=False, default=0)
    devise = Column(String(8), nullable=False, default="XAF")
    kyc_verifie = Column(Boolean, nullable=False, default=False)
    statut = Column(String(16), nullable=False, default="actif")
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow)


class PaymentTransactionV2DB(Base):
    """Transaction multi-provider unifiée (succède à TransactionPaiementDB+CommandePaiementDB)."""
    __tablename__ = "payment_transactions_v2"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    reference = Column(String(64), nullable=False, unique=True, index=True)
    compagnie_id = Column(BigInteger, nullable=False, index=True)
    user_id = Column(BigInteger, nullable=True, index=True)
    type = Column(String(24), nullable=False)  # abonnement | recharge | service
    plan_ou_pack = Column(String(32), nullable=True)
    amount = Column(Numeric(14, 2), nullable=False)
    currency = Column(String(8), nullable=False, default="XAF")
    country_code = Column(String(2), nullable=True)
    customer_phone = Column(String(24), nullable=True, index=True)
    customer_email = Column(String(120), nullable=True)
    provider = Column(String(24), nullable=True, index=True)
    provider_reference = Column(String(120), nullable=True, index=True)
    payment_method = Column(String(24), nullable=True)
    status = Column(String(16), nullable=False, default="pending", index=True)
    payment_url = Column(Text, nullable=True)
    ussd_instructions = Column(Text, nullable=True)
    error_message = Column(Text, nullable=True)
    metadata_json = Column(JSON, nullable=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow, index=True)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    completed_at = Column(DateTime, nullable=True)


class PaymentAttemptDB(Base):
    """Tentative individuelle (cascade : un transaction_id → N attempts)."""
    __tablename__ = "payment_attempts"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    transaction_id = Column(BigInteger, ForeignKey("payment_transactions_v2.id", ondelete="CASCADE"), nullable=False, index=True)
    provider = Column(String(24), nullable=False)
    provider_reference = Column(String(120), nullable=True)
    status = Column(String(16), nullable=False)
    error_message = Column(Text, nullable=True)
    response_payload = Column(JSON, nullable=True)
    attempted_at = Column(DateTime, nullable=False, default=datetime.utcnow)


class PaymentWebhookEventDB(Base):
    """Audit log de tous les webhooks reçus (pour debug + replay)."""
    __tablename__ = "payment_webhook_events"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    provider = Column(String(24), nullable=False, index=True)
    provider_reference = Column(String(120), nullable=True, index=True)
    transaction_id = Column(BigInteger, ForeignKey("payment_transactions_v2.id", ondelete="SET NULL"), nullable=True, index=True)
    status_received = Column(String(16), nullable=True)
    signature_valid = Column(Boolean, nullable=False, default=True)
    raw_payload = Column(JSON, nullable=True)
    received_at = Column(DateTime, nullable=False, default=datetime.utcnow, index=True)


# ─── ENQUÊTES — persistance JSON blob ────────────────────────────────────────

class SessionCopiloteDB(Base):
    """Session conversationnelle du copilote assistant — historique + contexte actif."""
    __tablename__ = "copilote_sessions"

    user_id        = Column(Integer, primary_key=True, index=True)
    role           = Column(String(50), nullable=False, default="agent")
    historique     = Column(JSON, nullable=False, default=list)   # list[dict] — 100 derniers échanges
    contexte_actif = Column(String(200), nullable=True)
    modifie_le     = Column(DateTime, default=datetime.utcnow)


class EtudeDB(Base):
    """
    Persistance complète d'une étude + formulaire + transcriptions + analyses.
    Sérialisée en JSON pour éviter ~20 tables relationnelles et rester simple.
    """
    __tablename__ = "enquetes_etudes"

    etude_id    = Column(String(36), primary_key=True, index=True)
    user_id     = Column(Integer, nullable=False, index=True)
    titre       = Column(String(300), nullable=False, index=True)
    statut      = Column(String(50), nullable=False, default="brouillon", index=True)
    data        = Column(JSON, nullable=False)  # Dump complet du dataclass Etude
    cree_le     = Column(DateTime, default=datetime.utcnow, nullable=False)
    modifie_le  = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)


# ─── Phase 4.1 — Bulk async jobs (CSV/XLSX > 50 lignes) ─────────────────────


class BulkJobDB(Base):
    """
    Job de génération bulk asynchrone (CSV/XLSX) pour grands volumes
    (>50 lignes, jusqu'à 1000). Sprint UX3 reste synchrone pour ≤50.

    Workflow :
      1. POST /bulk/lancer-async → crée row 'pending' + lance task background
      2. GET /bulk/status/{job_id} → polling pour progression (nb_done, nb_failed)
      3. GET /bulk/download/{job_id} → ZIP de tous les PDFs générés (statut='done')
    """
    __tablename__ = "bulk_jobs"

    job_id            = Column(String(36), primary_key=True, index=True)
    user_id           = Column(Integer, nullable=False, index=True)
    compagnie_id      = Column(Integer, nullable=False, index=True)
    cle_projet        = Column(String(80), nullable=False)
    template_brief    = Column(Text, nullable=False)
    mapping           = Column(JSON, nullable=False, default=dict)
    rows_data         = Column(JSON, nullable=False, default=list)
    mode_visuel       = Column(String(20), default="standard")
    pays              = Column(String(3), default="CM")
    langue            = Column(String(8), default="fr")
    total             = Column(Integer, nullable=False)
    nb_done           = Column(Integer, default=0)
    nb_failed         = Column(Integer, default=0)
    statut            = Column(String(20), default="pending", index=True)
    # pending | running | done | failed | cancelled
    results           = Column(JSON, default=list)   # [{index, statut, download_url, brief, erreur}]
    zip_path          = Column(String(500), nullable=True)   # chemin ZIP final
    cree_le           = Column(DateTime, default=datetime.utcnow, nullable=False)
    demarre_le        = Column(DateTime, nullable=True)
    fini_le           = Column(DateTime, nullable=True)
    erreur            = Column(Text, nullable=True)


# ─── Sprint C1 — Chat conversationnel Designer Pro (sessions actives) ───────


class DesignerProSessionDB(Base):
    """
    Session de chat Designer Pro : permet à l'utilisateur de continuer un
    projet en mode conversationnel ("ajoute une page", "change la couleur",
    "translate to English") sans repartir de zéro à chaque message.

    TTL 30 min après dernière interaction (au-delà, considéré comme nouveau projet).
    """
    __tablename__ = "designerpro_sessions"

    session_id           = Column(String(36), primary_key=True, index=True)
    user_id              = Column(Integer, nullable=False, index=True)
    compagnie_id         = Column(Integer, nullable=False, index=True)
    projet_actif_id      = Column(String(120), nullable=True,
        comment="ID du projet JSON courant (peut changer si user demande nouveau projet)")
    historique           = Column(JSON, default=list,
        comment="[{role:user|yukpo, ts, content, intent?, projet_id?}] — last 50 msgs")
    derniere_interaction = Column(DateTime, default=datetime.utcnow,
                                   onupdate=datetime.utcnow, nullable=False, index=True)
    cree_le              = Column(DateTime, default=datetime.utcnow, nullable=False)


# ─── Sprint 2.5 — White-label (revendeurs / cabinets / agences) ──────────────


class WhiteLabelDB(Base):
    """
    Configuration white-label d'une organisation revendeur. Permet aux
    cabinets / agences / partenaires de proposer YukpoPro sous leur propre
    marque (custom domain + logo + emails transactionnels brandés).

    Le custom domain est rattaché au frontend Vercel via API si
    VERCEL_API_TOKEN est configuré, sinon le domaine est juste enregistré
    et l'admin doit le configurer manuellement dans Vercel.
    """
    __tablename__ = "white_labels"

    wl_id            = Column(String(36), primary_key=True, index=True)
    compagnie_id     = Column(Integer, nullable=False, unique=True, index=True)
    actif            = Column(Boolean, default=True, index=True)

    # Custom domain (ex: "design.acmebank.cm")
    custom_domain    = Column(String(255), nullable=True, unique=True, index=True)
    domain_verified  = Column(Boolean, default=False)
    domain_target    = Column(String(255), nullable=True,
                              default="cname.vercel-dns.com")
    vercel_project_id = Column(String(120), nullable=True)
    vercel_added_le  = Column(DateTime, nullable=True)

    # Branding visuel
    logo_url         = Column(String(500), nullable=True)         # logo header (PNG/SVG public)
    favicon_url      = Column(String(500), nullable=True)
    couleur_primaire_hex = Column(String(8), nullable=True)
    nom_marque       = Column(String(120), nullable=True)         # "ACME Studio Design"
    tagline          = Column(String(300), nullable=True)

    # Emails transactionnels
    sender_email     = Column(String(200), nullable=True)         # "design@acmebank.cm"
    sender_name      = Column(String(120), nullable=True)         # "ACME Studio"
    reply_to_email   = Column(String(200), nullable=True)
    smtp_dkim_actif  = Column(Boolean, default=False)             # validation SPF/DKIM faite

    # Footer custom (mentions légales revendeur, RC, etc.)
    footer_html      = Column(Text, nullable=True)

    # Hide Yukpo branding (option premium)
    hide_yukpo_brand = Column(Boolean, default=False)

    cree_le          = Column(DateTime, default=datetime.utcnow, nullable=False)
    modifie_le       = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)


# ─── Sprint 2.4 — Brand Kit verrouillé par organisation ──────────────────────


class BrandKitDB(Base):
    """
    Charte visuelle officielle d'une organisation, héritée AUTOMATIQUEMENT
    par toutes les générations Designer Pro de l'org. Le LLM (Opus art director
    + Haiku spec) reçoit ces contraintes en prompt obligatoire.

    Brand compliance checker (Sonnet vision) peut être appelé après génération
    pour vérifier le respect (palette dominante, logo présent, ToV cohérent).
    """
    __tablename__ = "brand_kits"

    kit_id            = Column(String(36), primary_key=True, index=True)
    compagnie_id      = Column(Integer, nullable=False, unique=True, index=True)
    label             = Column(String(120), nullable=False, default="Charte officielle")
    actif             = Column(Boolean, default=True, index=True)

    # Palette
    couleur_primaire_hex   = Column(String(8), nullable=True)
    couleur_secondaire_hex = Column(String(8), nullable=True)
    couleur_accent_hex     = Column(String(8), nullable=True)
    couleurs_extras_hex    = Column(JSON, default=list)         # ["#aabbcc", ...]

    # Polices (familles Google Fonts ou ReportLab core)
    font_titre        = Column(String(80), default="Inter")
    font_corps        = Column(String(80), default="Inter")
    font_accent       = Column(String(80), nullable=True)

    # Identité
    logo_media_ref    = Column(String(120), nullable=True)        # 'compte:abc' média catégorie 'logo'
    nom_organisation  = Column(String(200), nullable=True)
    baseline          = Column(String(300), nullable=True)        # ex: "L'assurance qui rassure"

    # Tone of voice + lexique
    tone_of_voice     = Column(Text, nullable=True)               # 1-3 phrases, ex: "professionnel rassurant, vouvoiement, vocabulaire métier"
    lexique_prefere   = Column(JSON, default=list)                # ["client", "partenaire", ...]
    mots_interdits    = Column(JSON, default=list)                # ["lol", "easy", ...]

    # Brand LoRA par défaut (auto-injecté en mode premium)
    brand_lora_id_defaut = Column(String(36), nullable=True)

    # Niveau de strictness 0=permissif, 100=verrouillage strict
    strictness        = Column(Integer, default=70)

    cree_le           = Column(DateTime, default=datetime.utcnow, nullable=False)
    modifie_le        = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)


# ─── Sprint 2.3 — Approval workflows (Designer Pro) ──────────────────────────


class ProjetApprovalDB(Base):
    """
    Workflow d'approbation pour un projet Designer Pro généré.
    États : draft → submitted → approved | rejected → published

    Le projet en lui-même est tracé via DocumentGenereDB (existant). Cette
    table ajoute la couche workflow pour que les directions marketing puissent
    valider avant publication client final.
    """
    __tablename__ = "projet_approvals"

    approval_id      = Column(String(36), primary_key=True, index=True)
    compagnie_id     = Column(Integer, nullable=False, index=True)
    document_id      = Column(Integer, nullable=True, index=True)   # FK soft DocumentGenereDB.id
    projet_json_id   = Column(String(120), nullable=True, index=True)
    titre            = Column(String(300), nullable=False)
    cle_projet       = Column(String(80), nullable=False)
    user_id_createur = Column(Integer, nullable=False)
    user_id_approver = Column(Integer, nullable=True)               # qui a approuvé/rejeté
    statut           = Column(String(30), nullable=False, default="draft", index=True)
    # draft | submitted | approved | rejected | published | archived
    note_submission  = Column(Text, nullable=True)                  # message du créateur
    note_decision    = Column(Text, nullable=True)                  # raison approbation/rejet
    cree_le          = Column(DateTime, default=datetime.utcnow, nullable=False)
    soumis_le        = Column(DateTime, nullable=True)
    decide_le        = Column(DateTime, nullable=True)
    publie_le        = Column(DateTime, nullable=True)
    meta             = Column(JSON, nullable=True, default=dict)    # mode_visuel, nb_pages, etc.


# ─── Sprint 2.2 — SAML SSO (Identity Provider config par organisation) ───────


class SamlConfigDB(Base):
    """
    Configuration SAML SSO d'une organisation. 1 row par compagnie active.

    L'admin de l'org colle le metadata XML de son IdP (Okta/Azure AD/Google
    Workspace) et configure le mapping des attributs SAML → champs user
    YukpoPro (email, nom, role).
    """
    __tablename__ = "saml_configs"

    config_id           = Column(String(36), primary_key=True, index=True)
    compagnie_id        = Column(Integer, nullable=False, unique=True, index=True)
    actif               = Column(Boolean, default=True, index=True)
    idp_metadata_xml    = Column(Text, nullable=False)            # IdP metadata XML (collé par admin)
    idp_entity_id       = Column(String(500), nullable=False)
    idp_sso_url         = Column(String(500), nullable=False)
    idp_x509_cert       = Column(Text, nullable=False)             # Certificat IdP pour vérif signature
    sp_entity_id        = Column(String(500), nullable=False)     # Notre entity ID (URL canonique)
    sp_acs_url          = Column(String(500), nullable=False)     # Notre Assertion Consumer Service
    # Mapping attributs SAML → user YukpoPro
    attr_email          = Column(String(120), default="email")
    attr_nom            = Column(String(120), default="displayName")
    attr_role           = Column(String(120), default="role")
    role_par_defaut     = Column(String(50), default="agent")     # si attr_role absent dans assertion
    auto_provision      = Column(Boolean, default=True)            # créer user à la 1ère connexion
    cree_le             = Column(DateTime, default=datetime.utcnow, nullable=False)
    modifie_le          = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)


# ─── Sprint 2.1 — Clés API publiques (B2B / intégrations clients) ────────────


class ApiKeyDB(Base):
    """
    Clés API pour intégration B2B au YukpoPro public API.
    Chaque clé appartient à une organisation (compagnie_id) et a des scopes
    + un rate-limit configurable.

    Format clé exposée : `ypro_live_<32 hex chars>` (préfixe identifie env :
    `live` = prod, `test` = sandbox). On stocke uniquement le HASH SHA-256
    pour qu'une compromise DB ne révèle aucune clé en clair.
    """
    __tablename__ = "api_keys"

    key_id              = Column(String(36), primary_key=True, index=True)
    compagnie_id        = Column(Integer, nullable=False, index=True)
    user_id_createur    = Column(Integer, nullable=False)
    label               = Column(String(120), nullable=False)            # "Site marketing", "ERP integration", ...
    key_prefix          = Column(String(20), nullable=False, index=True) # "ypro_live_" ou "ypro_test_"
    key_hash            = Column(String(64), nullable=False, unique=True, index=True)
    scopes              = Column(JSON, nullable=False, default=list)     # ["designerpro:generate", "designerpro:read", ...]
    rate_limit_per_hour = Column(Integer, nullable=False, default=100)
    rate_limit_per_day  = Column(Integer, nullable=False, default=1000)
    actif               = Column(Boolean, default=True, index=True)
    cree_le             = Column(DateTime, default=datetime.utcnow, nullable=False)
    derniere_utilisation = Column(DateTime, nullable=True)
    revoquee_le         = Column(DateTime, nullable=True)
    note                = Column(String(500), nullable=True)


# ─── Sprint 1.6 — Brand LoRA (Designer Pro) ──────────────────────────────────


class BrandLoraDB(Base):
    """
    Brand LoRA entraîné pour une organisation : permet d'injecter le style
    visuel d'une marque dans toutes les générations d'images Flux dev.

    Coût d'entraînement : ~120-200 EUR via fal-ai/flux-lora-fast-training
    (~1500 secondes GPU). Stocké comme `lora_url` (URL fal.ai du fichier .safetensors).
    L'org peut avoir plusieurs LoRA actifs (ex: "été", "hiver", "campagne X").
    """
    __tablename__ = "brand_loras"

    lora_id          = Column(String(36), primary_key=True, index=True)
    compagnie_id     = Column(Integer, nullable=False, index=True)
    user_id_createur = Column(Integer, nullable=False)
    label            = Column(String(120), nullable=False)
    trigger_word     = Column(String(80), nullable=False)        # ex: "ACMECORP"
    description      = Column(String(500), nullable=True)
    fal_request_id   = Column(String(120), nullable=True)        # tracking fal.ai
    lora_url         = Column(String(500), nullable=True)        # URL .safetensors
    statut           = Column(String(30), nullable=False, default="pending", index=True)
    # pending | training | ready | failed
    nb_images_train  = Column(Integer, nullable=False, default=0)
    cout_paye_fcfa   = Column(Integer, nullable=False, default=0)
    actif            = Column(Boolean, default=True, index=True)
    cree_le          = Column(DateTime, default=datetime.utcnow, nullable=False)
    training_demarre = Column(DateTime, nullable=True)
    training_fini    = Column(DateTime, nullable=True)
    erreur           = Column(String(500), nullable=True)


# ─── INIT & HELPERS ───────────────────────────────────────────────────────────

async def init_db() -> None:
    """Crée toutes les tables et ajoute les colonnes manquantes (migrations sans Alembic).

    Sérialisé entre workers gunicorn via pg_advisory_lock (PostgreSQL),
    pour éviter UniqueViolationError sur pg_class_relname_nsp_index quand
    plusieurs workers tentent CREATE TABLE en parallèle.
    """
    is_postgres = settings.DATABASE_URL.startswith("postgresql")
    _LOCK_KEY = 9712  # clé arbitraire, partagée par tous les workers
    async with engine.begin() as conn:
        if is_postgres:
            try:
                await conn.execute(text(f"SELECT pg_advisory_lock({_LOCK_KEY})"))
            except Exception as e:
                logger.warning(f"[DB] pg_advisory_lock indisponible: {e}")
        try:
            await conn.run_sync(Base.metadata.create_all)
        finally:
            if is_postgres:
                try:
                    await conn.execute(text(f"SELECT pg_advisory_unlock({_LOCK_KEY})"))
                except Exception:
                    pass

    # ── Migrations colonnes manquantes (ALTER TABLE IF NOT EXISTS) ─────────────
    # PostgreSQL 9.6+ supporte ADD COLUMN IF NOT EXISTS.
    # Chaque entrée : (table, colonne, type SQL, valeur DEFAULT optionnelle)
    _nouvelles_colonnes = [
        # ProfilProfessionnelDB — colonnes ajoutées après le déploiement initial
        ("profils_pro", "photo_profil_chemin",        "VARCHAR(300)", None),
        ("profils_pro", "cv_texte",                   "TEXT",      None),
        ("profils_pro", "cv_fichier_chemin",          "VARCHAR(300)", None),
        ("profils_pro", "profil_recherche_emploi",    "TEXT",      None),
        ("profils_pro", "recherche_emploi_active",    "BOOLEAN",   "FALSE"),
        ("profils_pro", "frequence_recherche_heures", "INTEGER",   "24"),
        ("profils_pro", "derniere_recherche_emploi",  "TIMESTAMP", None),
        ("profils_pro", "offres_emploi_recentes",     "JSONB",     "'[]'"),
        ("profils_pro", "marches_publics_recents",    "JSONB",     "'[]'"),
        ("profils_pro", "derniere_recherche_marches", "TIMESTAMP", None),
        ("profils_pro", "secteur_activite",           "VARCHAR(100)", None),
        ("profils_pro", "derniere_activite",          "TIMESTAMP", None),
        # UtilisateurDB
        ("utilisateurs",         "bloque_jusqu_au",            "TIMESTAMP", None),
        ("utilisateurs",         "tentatives_echec",           "INTEGER",   "0"),
        ("utilisateurs",         "totp_secret",                "VARCHAR(64)", None),
        ("utilisateurs",         "totp_active",                "BOOLEAN",   "FALSE"),
        # SessionCopiloteDB (table créée par create_all — colonnes ajoutées si migration partielle)
        ("copilote_sessions",    "contexte_actif",             "VARCHAR(200)", None),
        ("copilote_sessions",    "modifie_le",                 "TIMESTAMP", None),
        # CompagnieDB — webhook HMAC secret
        ("compagnies",           "webhook_secret",             "VARCHAR(128)", None),
        # BureauBonTravailDB — WhatsApp client + notif de fin
        ("bureau_bons_travail",  "client_whatsapp",            "VARCHAR(30)",  None),
        ("bureau_bons_travail",  "notif_fin_envoyee",          "BOOLEAN",      "FALSE"),
        ("bureau_bons_travail",  "notif_fin_horodatage",       "TIMESTAMP",    None),
        # Sprint admin-cross — séparation app source pour le dashboard unifié.
        # Pré-existant : default 'pro' / 'sec' selon la table.
        ("consommations_tokens", "app_origine",                "VARCHAR(10)",  "'pro'"),
        ("consommations_bureau", "app_origine",                "VARCHAR(10)",  "'sec'"),
    ]
    async with engine.begin() as conn:
        for table, col, col_type, default in _nouvelles_colonnes:
            default_clause = f" DEFAULT {default}" if default else ""
            sql = f"ALTER TABLE {table} ADD COLUMN IF NOT EXISTS {col} {col_type}{default_clause}"
            try:
                await conn.execute(text(sql))
            except Exception as e:
                logger.warning(f"[DB] Migration colonne {table}.{col} ignorée: {e}")

    logger.info("[DB] Tables initialisées + migrations colonnes appliquées")


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """Dépendance FastAPI pour l'injection de session DB."""
    async with async_session_maker() as session:
        yield session
