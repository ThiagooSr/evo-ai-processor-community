# -*- coding: utf-8 -*-
"""
Maxnivel OAuth2 Client ÔÇö evo-processor
Reutiliza as mesmas credenciais do evo-nexus (.env compartilhado ou copiado).

Auth:  POST https://kaiabi.com/api/v1/auth/token
Dados: GET  https://kaiabi.com/api/v1/distribuidores/{id}

Env vars (compat├¡veis com o evo-nexus):
    MAXNIVEL_BASE_URL      ÔåÆ Base da API  (padr├úo: https://kaiabi.com/api)
    MAXNIVEL_CLIENT_ID     ÔåÆ appId
    MAXNIVEL_CLIENT_SECRET ÔåÆ appSecret
"""

import logging
import os
import threading
import time

import requests

logger = logging.getLogger(__name__)


class MaxnivelTokenManager:
    """
    Gerencia o access_token OAuth2 (client_credentials) da Maxnivel.

    Estrat├®gia LAZY com buffer de 60 s:
    - Token obtido na primeira chamada.
    - Renovado automaticamente quando falta Ôëñ 60 s para expirar.
    - Thread-safe via Lock.
    - Em caso de 401 da API, `invalidate()` for├ºa nova obten├º├úo imediata.
    """

    BUFFER_SECONDS = 60  # renova 1 min antes de expirar

    def __init__(self):
        self._token: str | None = None
        self._expires_at: float = 0.0
        self._lock = threading.Lock()

    # ------------------------------------------------------------------
    # P├║blico
    # ------------------------------------------------------------------

    def get_token(self) -> str:
        """Retorna token v├ílido, renovando se necess├írio."""
        with self._lock:
            if self._is_expired():
                self._refresh()
            return self._token  # type: ignore[return-value]

    def invalidate(self) -> None:
        """For├ºa renova├º├úo na pr├│xima chamada (use ap├│s receber 401)."""
        with self._lock:
            self._expires_at = 0.0

    # ------------------------------------------------------------------
    # Interno
    # ------------------------------------------------------------------

    def _is_expired(self) -> bool:
        return self._token is None or time.time() >= self._expires_at

    def _refresh(self) -> None:
        base_url      = os.getenv("MAXNIVEL_BASE_URL", "https://kaiabi.com/api").rstrip("/")
        client_id     = os.getenv("MAXNIVEL_CLIENT_ID", "").strip()
        client_secret = os.getenv("MAXNIVEL_CLIENT_SECRET", "").strip()
        auth_url      = f"{base_url}/v1/auth/token"

        if not client_id or not client_secret:
            raise EnvironmentError(
                "MAXNIVEL_CLIENT_ID e MAXNIVEL_CLIENT_SECRET devem estar no .env"
            )

        logger.info("[Maxnivel] Renovando access_token OAuth2ÔÇª")

        resp = requests.post(
            auth_url,
            data={
                "grant_type":    "client_credentials",
                "client_id":     client_id,
                "client_secret": client_secret,
            },
            timeout=15,
        )

        if resp.status_code != 200:
            raise RuntimeError(
                f"[Maxnivel] Falha ao obter token: {resp.status_code} ÔÇö {resp.text[:300]}"
            )

        data = resp.json()
        self._token = data["access_token"]
        expires_in = int(data.get("expires_in", 3600))
        self._expires_at = time.time() + expires_in - self.BUFFER_SECONDS

        mins = (self._expires_at - time.time()) / 60
        logger.info(f"[Maxnivel] Token renovado. Pr├│xima renova├º├úo em {mins:.0f} min.")


class MaxnivelClient:
    """
    Cliente HTTP autenticado para a API Maxnivel (kaiabi.com/api).

    Endpoint utilizado pelo webhook de cadastro:
        GET /v1/distribuidores/{id}
    Retorna: {"distribuidores": [{...}]}  ÔåÆ array com dados do distribuidor
    incluindo "nome", "telefones": [{"telefone": "..."}]
    """

    def __init__(self, token_manager: MaxnivelTokenManager):
        self._tm = token_manager
        self._base = os.getenv("MAXNIVEL_BASE_URL", "https://kaiabi.com/api").rstrip("/")

    # ------------------------------------------------------------------
    # Requisi├º├úo com retry em 401
    # ------------------------------------------------------------------

    def _get(self, path: str, params: dict | None = None) -> dict:
        url = f"{self._base}{path}"
        resp = requests.get(url, headers=self._auth_headers(), params=params, timeout=15)

        if resp.status_code == 401:
            logger.warning("[Maxnivel] 401 ÔÇö token inv├ílido/expirado. RenovandoÔÇª")
            self._tm.invalidate()
            resp = requests.get(url, headers=self._auth_headers(), params=params, timeout=15)

        resp.raise_for_status()
        return resp.json()

    def _auth_headers(self) -> dict:
        return {
            "Authorization":  f"Bearer {self._tm.get_token()}",
            "Content-Type":   "application/json",
            "Accept":         "application/json",
        }

    # ------------------------------------------------------------------
    # M├®todos de neg├│cio
    # ------------------------------------------------------------------

    def obter_distribuidor(self, id_distribuidor: str | int) -> dict:
        """
        GET /v1/distribuidores/{id}

        Resposta esperada:
        {
            "distribuidores": [
                {
                    "nome": "Jo├úo Silva",
                    "telefones": [{"telefone": "63999001234"}],
                    ...
                }
            ]
        }
        """
        return self._get(f"/v1/distribuidores/{id_distribuidor}")

    def buscar_telefones_distribuidor(self, id_distribuidor: str | int) -> list:
        """
        GET /v1/distribuidores/{id}/telefones
        Fallback caso o endpoint principal n├úo traga os telefones.
        """
        return self._get(f"/v1/distribuidores/{id_distribuidor}/telefones")


# ---------------------------------------------------------------------------
# Singleton global ÔÇö importe em outros m├│dulos como:
#   from src.services.maxnivel_client import maxnivel_client
# ---------------------------------------------------------------------------
_token_manager = MaxnivelTokenManager()
maxnivel_client = MaxnivelClient(_token_manager)
