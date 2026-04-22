"""
YukpoAssurance — Pagination par curseur (cursor-based pagination)

Avantages vs offset/limit :
- Performance stable sur grandes tables (pas de COUNT(*) ni OFFSET lent)
- Résultats stables même si des lignes sont ajoutées entre 2 pages
- Adapté aux flux temps réel (sinistres, chat, audit trail)

Format de réponse standard :
{
    "items": [...],
    "cursor_next": "eyJpZCI6MTIzfQ==",   # base64 opaque (next page)
    "cursor_prev": "eyJpZCI6MTAwfQ==",   # base64 opaque (prev page)
    "has_next": true,
    "has_prev": false,
    "total_count": null,                  # optionnel (coûteux)
    "page_size": 20,
}
"""
from __future__ import annotations

import base64
import json
from dataclasses import dataclass, field
from typing import Any, Optional, TypeVar

T = TypeVar("T")


@dataclass
class PageCurseur:
    """Résultat paginé par curseur."""
    items: list[Any]
    cursor_next: Optional[str] = None
    cursor_prev: Optional[str] = None
    has_next: bool = False
    has_prev: bool = False
    total_count: Optional[int] = None
    page_size: int = 20


def encoder_curseur(data: dict) -> str:
    """Encode un dict en curseur opaque base64."""
    return base64.urlsafe_b64encode(
        json.dumps(data, separators=(",", ":")).encode()
    ).decode().rstrip("=")


def decoder_curseur(cursor: Optional[str]) -> Optional[dict]:
    """Décode un curseur base64 en dict. Retourne None si invalide."""
    if not cursor:
        return None
    try:
        # Réajouter le padding base64
        padding = 4 - len(cursor) % 4
        if padding != 4:
            cursor += "=" * padding
        return json.loads(base64.urlsafe_b64decode(cursor).decode())
    except Exception:
        return None


def paginer_liste(
    items: list[Any],
    cursor: Optional[str] = None,
    page_size: int = 20,
    id_field: str = "id",
) -> PageCurseur:
    """
    Applique la pagination par curseur à une liste Python.
    Utilisé pour les résultats en mémoire (sessions, ORASS simulation).

    Args:
        items: Liste complète d'items (triée par id_field ASC)
        cursor: Curseur de départ (opaque base64)
        page_size: Nombre d'items par page (max 100)
        id_field: Champ utilisé comme clé de curseur

    Returns:
        PageCurseur avec items de la page + curseurs next/prev
    """
    page_size = min(max(1, page_size), 100)

    # Décoder le curseur pour trouver l'offset
    cursor_data = decoder_curseur(cursor)
    start_id = cursor_data.get("after_id") if cursor_data else None

    # Filtrer les items après le curseur
    if start_id is not None:
        start_idx = 0
        for i, item in enumerate(items):
            item_id = item.get(id_field) if isinstance(item, dict) else getattr(item, id_field, None)
            if str(item_id) == str(start_id):
                start_idx = i + 1
                break
        items_filtres = items[start_idx:]
    else:
        items_filtres = items
        start_idx = 0

    # Prendre page_size + 1 pour savoir s'il y a une page suivante
    items_page = items_filtres[:page_size + 1]
    has_next = len(items_page) > page_size
    page_items = items_page[:page_size]

    # Calculer les curseurs
    cursor_next = None
    cursor_prev = None

    if has_next and page_items:
        last_item = page_items[-1]
        last_id = (
            last_item.get(id_field)
            if isinstance(last_item, dict)
            else getattr(last_item, id_field, None)
        )
        cursor_next = encoder_curseur({"after_id": last_id})

    if start_idx > 0 and page_items:
        first_item = page_items[0]
        first_id = (
            first_item.get(id_field)
            if isinstance(first_item, dict)
            else getattr(first_item, id_field, None)
        )
        # Cursor prev = revenir page_size items en arrière
        prev_idx = max(0, start_idx - page_size)
        if prev_idx > 0:
            prev_item = items[prev_idx - 1]
            prev_id = (
                prev_item.get(id_field)
                if isinstance(prev_item, dict)
                else getattr(prev_item, id_field, None)
            )
            cursor_prev = encoder_curseur({"after_id": prev_id})
        else:
            cursor_prev = encoder_curseur({"after_id": None})

    return PageCurseur(
        items=page_items,
        cursor_next=cursor_next,
        cursor_prev=cursor_prev,
        has_next=has_next,
        has_prev=start_idx > 0,
        page_size=page_size,
    )


def paginer_sqlalchemy(
    query_items: list[Any],
    cursor: Optional[str],
    page_size: int = 20,
    id_field: str = "id",
) -> PageCurseur:
    """Alias — même comportement que paginer_liste (pour clarté sémantique)."""
    return paginer_liste(query_items, cursor, page_size, id_field)


def response_paginee(page: PageCurseur) -> dict:
    """Convertit PageCurseur en dict JSON standard pour les réponses API."""
    return {
        "items": page.items,
        "pagination": {
            "cursor_next": page.cursor_next,
            "cursor_prev": page.cursor_prev,
            "has_next": page.has_next,
            "has_prev": page.has_prev,
            "page_size": page.page_size,
            "total_count": page.total_count,
        },
    }
