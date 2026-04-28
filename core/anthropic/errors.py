"""User-facing error formatting shared by API, providers, and integrations."""

import httpx
import openai


def get_user_facing_error_message(
    e: Exception,
    *,
    read_timeout_s: float | None = None,
) -> str:
    """Retourne un message d'erreur lisible pour l'utilisateur.

    Les exceptions connues (httpx, openai, etc.) sont mappées
    avant le fallback sur str(e), pour éviter que les messages
    vides ou bruyants du SDK ne court-circuitent les mappings.
    """
    if isinstance(e, httpx.ReadTimeout):
        if read_timeout_s is not None:
            return f"Délai dépassé pour la requête au fournisseur après {read_timeout_s:g}s."
        return "Délai dépassé pour la requête au fournisseur."
    if isinstance(e, httpx.ConnectTimeout):
        return "Impossible de se connecter au fournisseur."
    if isinstance(e, TimeoutError):
        if read_timeout_s is not None:
            return f"Délai dépassé pour la requête au fournisseur après {read_timeout_s:g}s."
        return "Délai dépassé pour la requête."

    if isinstance(e, openai.RateLimitError):
        return "Limite de requêtes atteinte. Veuillez réessayer dans un moment."
    if isinstance(e, openai.AuthenticationError):
        return "Authentification du fournisseur échouée. Vérifiez votre clé API."
    if isinstance(e, openai.BadRequestError):
        return "Invalid request sent to provider."

    name = type(e).__name__
    status_code = getattr(e, "status_code", None)
    if isinstance(e, openai.RateLimitError) or name == "RateLimitError":
        return "Limite de requêtes atteinte. Veuillez réessayer dans un moment."
    if isinstance(e, openai.AuthenticationError) or name == "AuthenticationError":
        return "Authentification du fournisseur échouée. Vérifiez votre clé API."
    if isinstance(e, openai.BadRequestError) or name == "InvalidRequestError":
        return "Invalid request sent to provider."
    if name == "OverloadedError":
        return "Le fournisseur est actuellement surchargé. Veuillez réessayer."
    if name == "APIError":
        if status_code in (502, 503, 504):
            return "Le fournisseur est temporairement indisponible. Veuillez réessayer."
        return "Provider API request failed."
    if name.endswith("ProviderError") or name == "ProviderError":
        return "Provider request failed."

    # Fallback final
    message = str(e).strip()
    if message:
        return message

    return "Échec inattendu de la requête au fournisseur."


def format_user_error_preview(exc: Exception, *, max_len: int = 200) -> str:
    """Truncate a user-facing error string for short chat replies."""
    return get_user_facing_error_message(exc)[:max_len]


def append_request_id(message: str, request_id: str | None) -> str:
    """Ajoute le suffixe request_id quand disponible."""
    base = message.strip() or "Échec inattendu de la requête au fournisseur."
    if request_id:
        return f"{base} (request_id={request_id})"
    return base
