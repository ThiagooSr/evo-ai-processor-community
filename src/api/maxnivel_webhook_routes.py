# -*- coding: utf-8 -*-
"""
Webhook Routes ÔÇö Integra├º├Áes Externas (Maxnivel)

Endpoint: POST /api/v1/webhook/cadastro-distribuidor
Triggered by: Sistema Maxnivel ao cadastrar novo distribuidor

Env vars necess├írias:
    # Maxnivel OAuth2
    MAXNIVEL_AUTH_URL        ÔåÆ URL do token OAuth2 da Maxnivel
    MAXNIVEL_CLIENT_ID       ÔåÆ appId (client_id)
    MAXNIVEL_CLIENT_SECRET   ÔåÆ appSecret (client_secret)
    MAXNIVEL_API_BASE_URL    ÔåÆ Base URL da API de dados
    WEBHOOK_SECRET           ÔåÆ (opcional) segredo para autenticar o webhook

    # Meta / WABA
    META_PHONE_ID            ÔåÆ Phone Number ID do WABA
    META_ACCESS_TOKEN        ÔåÆ Token permanente do WABA
    META_TEMPLATE_NAME       ÔåÆ Nome da template (padr├úo: boas_vindas)
    META_TEMPLATE_IMAGE_URL  ÔåÆ (opcional) URL da imagem no header da template

    # CRM (Chatwoot)
    CRM_URL                  ÔåÆ URL do CRM (padr├úo: https://crm.kaiabi.com)
    CRM_API_TOKEN            ÔåÆ Token do agente no Chatwoot
    CRM_ACCOUNT_ID           ÔåÆ ID da conta Chatwoot (padr├úo: 1)
    CRM_INBOX_ID             ÔåÆ ID da caixa de entrada WhatsApp no Chatwoot
"""

import logging
import os
from typing import Union

import requests
from fastapi import APIRouter, Header, HTTPException, Request
from fastapi.responses import JSONResponse

from src.services.maxnivel_client import maxnivel_client

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/webhook", tags=["Webhook"])


# =============================================================================
# Helpers internos
# =============================================================================

def _parse_id_distribuidor(body: Union[int, str, dict, None]) -> str:
    """
    Aceita os 3 formatos que a Maxnivel pode enviar:
    - N├║mero puro:   7984
    - String pura:   "7984"
    - JSON com chave: {"id_distribuidor": "7984"}
    """
    if isinstance(body, (int, float)):
        return str(int(body)).strip()
    if isinstance(body, str):
        return body.strip()
    if isinstance(body, dict):
        val = body.get("id_distribuidor") or body.get("id")
        if val:
            return str(val).strip()
    raise ValueError("Payload inv├ílido ÔÇö imposs├¡vel extrair id_distribuidor")


def _formatar_telefone(telefone_raw: str) -> str:
    """Remove n├úo-d├¡gitos e garante prefixo 55 (Brasil)."""
    limpo = "".join(filter(str.isdigit, telefone_raw))
    if not limpo.startswith("55"):
        limpo = "55" + limpo
    return limpo


def _enviar_template_meta(telefone: str, nome: str) -> dict:
    """Dispara a template WABA via Meta Graph API."""
    phone_id = os.getenv("META_PHONE_ID", "").strip()
    access_token = os.getenv("META_ACCESS_TOKEN", "").strip()
    template_name = os.getenv("META_TEMPLATE_NAME", "boas_vindas").strip()
    image_url = os.getenv("META_TEMPLATE_IMAGE_URL", "").strip()

    if not phone_id or not access_token:
        raise EnvironmentError("META_PHONE_ID e META_ACCESS_TOKEN s├úo obrigat├│rios")

    payload = {
        "messaging_product": "whatsapp",
        "to": telefone,
        "type": "template",
        "template": {
            "name": template_name,
            "language": {"code": "pt_BR"},
        },
    }

    # Componente de header com imagem (opcional)
    if image_url:
        payload["template"]["components"] = [
            {
                "type": "header",
                "parameters": [{"type": "image", "image": {"link": image_url}}],
            }
        ]

    resp = requests.post(
        f"https://graph.facebook.com/v19.0/{phone_id}/messages",
        headers={
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json",
        },
        json=payload,
        timeout=15,
    )

    logger.info(f"[Meta] Resposta: {resp.status_code} ÔÇö {resp.text[:200]}")

    if resp.status_code not in (200, 201):
        raise RuntimeError(f"Erro Meta API: {resp.status_code} ÔÇö {resp.text}")

    return resp.json()


def _registrar_no_crm(nome: str, telefone: str, template_name: str, meta_msg_id: str) -> int | None:
    """
    Busca ou cria contato no Chatwoot, abre conversa e registra a mensagem enviada.
    Retorna o ID da conversa criada ou None se falhar.
    """
    crm_url = os.getenv("CRM_URL", "https://crm.kaiabi.com").rstrip("/")
    crm_token = os.getenv("CRM_API_TOKEN", "").strip()
    crm_account_id = os.getenv("CRM_ACCOUNT_ID", "1").strip()
    crm_inbox_id = os.getenv("CRM_INBOX_ID", "").strip()

    if not crm_token or not crm_inbox_id:
        logger.warning("[CRM] CRM_API_TOKEN ou CRM_INBOX_ID n├úo configurados ÔÇö pulando registro.")
        return None

    headers = {"api_access_token": crm_token, "Content-Type": "application/json"}
    base = f"{crm_url}/api/v1/accounts/{crm_account_id}"

    # ÔöÇÔöÇ 1. Buscar ou criar contato ÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇ
    contact_id: int | None = None
    try:
        r = requests.get(
            f"{base}/contacts/search",
            headers=headers,
            params={"q": telefone, "include_contacts": True},
            timeout=8,
        )
        if r.status_code == 200:
            contacts = r.json().get("payload", {}).get("contacts", [])
            if contacts:
                contact_id = contacts[0]["id"]
                logger.info(f"[CRM] Contato encontrado: id={contact_id}")
    except Exception as e:
        logger.error(f"[CRM] Erro ao buscar contato: {e}")

    if not contact_id:
        try:
            r = requests.post(
                f"{base}/contacts",
                headers=headers,
                json={"name": nome, "phone_number": f"+{telefone}"},
                timeout=8,
            )
            if r.status_code in (200, 201):
                contact_id = r.json().get("id")
                logger.info(f"[CRM] Contato criado: id={contact_id}")
            else:
                logger.error(f"[CRM] Falha ao criar contato: {r.json()}")
                return None
        except Exception as e:
            logger.error(f"[CRM] Erro ao criar contato: {e}")
            return None

    # ÔöÇÔöÇ 2. Criar conversa ÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇ
    conv_id: int | None = None
    try:
        r = requests.post(
            f"{base}/conversations",
            headers=headers,
            json={
                "contact_id": contact_id,
                "inbox_id": int(crm_inbox_id),
                "additional_attributes": {
                    "origem": "cadastro_maxnivel",
                    "template": template_name,
                    "meta_msg_id": meta_msg_id,
                },
            },
            timeout=8,
        )
        if r.status_code in (200, 201):
            conv_id = r.json().get("id")
            logger.info(f"[CRM] Conversa criada: id={conv_id}")
        else:
            logger.error(f"[CRM] Falha ao criar conversa: {r.json()}")
            return None
    except Exception as e:
        logger.error(f"[CRM] Erro ao criar conversa: {e}")
        return None

    # ÔöÇÔöÇ 3. Registrar mensagem enviada ÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇ
    try:
        conteudo = (
            f"­ƒôñ Template *{template_name}* enviado via WhatsApp\n"
            f"­ƒæñ Distribuidor: {nome}\n"
            f"­ƒô▒ N├║mero: +{telefone}\n"
            f"­ƒåö ID Meta: {meta_msg_id}"
        )
        r = requests.post(
            f"{base}/conversations/{conv_id}/messages",
            headers=headers,
            json={"content": conteudo, "message_type": "outgoing", "private": False},
            timeout=8,
        )
        if r.status_code in (200, 201):
            logger.info(f"[CRM] Ô£à Mensagem registrada na conversa {conv_id}")
        else:
            logger.error(f"[CRM] Falha ao registrar mensagem: {r.json()}")
    except Exception as e:
        logger.error(f"[CRM] Erro ao registrar mensagem: {e}")

    return conv_id


# =============================================================================
# Endpoint principal
# =============================================================================

@router.post(
    "/cadastro-distribuidor",
    summary="Webhook ÔÇö Cadastro de Distribuidor Maxnivel",
    description=(
        "Recebe notifica├º├úo da Maxnivel ao cadastrar novo distribuidor. "
        "Busca dados do distribuidor via OAuth2, envia template WABA e "
        "registra a conversa no CRM."
    ),
)
async def cadastro_distribuidor_webhook(
    request: Request,
    x_webhook_secret: str = Header(default=None, alias="x-webhook-secret"),
    authorization: str = Header(default=None),
):
    # ÔöÇÔöÇ Autentica├º├úo opcional via WEBHOOK_SECRET ÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇ
    secret = os.getenv("WEBHOOK_SECRET", "").strip()
    if secret:
        token_ok = (
            (authorization and secret in authorization)
            or x_webhook_secret == secret
        )
        if not token_ok:
            raise HTTPException(status_code=401, detail="N├úo autorizado")

    # ÔöÇÔöÇ Parse do payload ÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇ
    try:
        body = await request.json()
    except Exception:
        body = (await request.body()).decode().strip()

    try:
        id_distribuidor = _parse_id_distribuidor(body)
    except ValueError as e:
        logger.warning(f"[Webhook Cadastro] Payload inv├ílido: {e} ÔÇö body={body}")
        raise HTTPException(status_code=400, detail=str(e))

    logger.info(f"[Webhook Cadastro] Processando id_distribuidor={id_distribuidor}")

    # ÔöÇÔöÇ 1. Buscar dados na Maxnivel (OAuth2 autom├ítico) ÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇ
    try:
        dados = maxnivel_client.obter_distribuidor(id_distribuidor)
    except Exception as e:
        logger.error(f"[Webhook Cadastro] Erro ao consultar Maxnivel: {e}")
        raise HTTPException(status_code=502, detail=f"Erro ao consultar Maxnivel: {e}")

    distribuidores = dados.get("distribuidores", [])
    if not distribuidores:
        raise HTTPException(status_code=404, detail=f"Distribuidor {id_distribuidor} n├úo encontrado")

    dist = distribuidores[0]
    nome = dist.get("nome", "Novo Distribuidor")

    # Extrai telefone
    telefones = dist.get("telefones", [])
    telefone_raw = ""
    if telefones and isinstance(telefones, list):
        telefone_raw = telefones[0].get("telefone", "")
    if not telefone_raw:
        telefone_raw = dist.get("celular") or dist.get("telefone") or ""

    if not telefone_raw:
        logger.warning(f"[Webhook Cadastro] Distribuidor {id_distribuidor} sem telefone.")
        raise HTTPException(status_code=400, detail="Distribuidor n├úo possui telefone cadastrado")

    telefone = _formatar_telefone(telefone_raw)
    logger.info(f"[Webhook Cadastro] Distribuidor: {nome} | Telefone: {telefone}")

    # ÔöÇÔöÇ 2. Enviar template via Meta WABA ÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇ
    template_name = os.getenv("META_TEMPLATE_NAME", "boas_vindas")
    try:
        meta_resp = _enviar_template_meta(telefone, nome)
        meta_msg_id = (meta_resp.get("messages") or [{}])[0].get("id", "N/D")
        logger.info(f"[Webhook Cadastro] Template enviado! Meta ID: {meta_msg_id}")
    except Exception as e:
        logger.error(f"[Webhook Cadastro] Erro ao enviar template: {e}")
        raise HTTPException(status_code=502, detail=f"Erro ao enviar template WABA: {e}")

    # ÔöÇÔöÇ 3. Registrar no CRM (n├úo bloqueia em caso de falha) ÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇÔöÇ
    conv_id = None
    try:
        conv_id = _registrar_no_crm(nome, telefone, template_name, meta_msg_id)
        if conv_id:
            logger.info(f"[Webhook Cadastro] Registrado no CRM ÔåÆ conversa #{conv_id}")
    except Exception as e:
        logger.error(f"[Webhook Cadastro] Erro ao registrar no CRM (n├úo cr├¡tico): {e}")

    return JSONResponse(
        content={
            "status": "sucesso",
            "distribuidor": nome,
            "telefone": telefone,
            "template": template_name,
            "meta_msg_id": meta_msg_id,
            "crm_conversa_id": conv_id,
        }
    )
