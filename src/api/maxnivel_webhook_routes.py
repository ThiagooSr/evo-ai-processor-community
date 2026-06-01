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
    base = f"{crm_url}/api/v1"

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
            contacts = r.json().get("data", [])
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
                contact_id = r.json().get("data", {}).get("contact", {}).get("id")
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
        inbox_id_val = int(crm_inbox_id)
    except ValueError:
        inbox_id_val = crm_inbox_id

    try:
        r = requests.post(
            f"{base}/conversations",
            headers=headers,
            json={
                "contact_id": contact_id,
                "inbox_id": inbox_id_val,
                "additional_attributes": {
                    "origem": "cadastro_maxnivel",
                    "template": template_name,
                    "meta_msg_id": meta_msg_id,
                },
            },
            timeout=8,
        )
        if r.status_code in (200, 201):
            conv_id = r.json().get("data", {}).get("id")
            logger.info(f"[CRM] Conversa criada: id={conv_id}")
            if conv_id:
                try:
                    requests.post(
                        f"{base}/conversations/{conv_id}/labels",
                        headers=headers,
                        json={"labels": ["cadastro-distribuidor"]},
                        timeout=5,
                    )
                    logger.info(f"[CRM] Etiqueta 'cadastro-distribuidor' aplicada à conversa {conv_id}")
                except Exception as le:
                    logger.warning(f"[CRM] Erro não crítico ao aplicar etiqueta: {le}")
        else:
            logger.error(f"[CRM] Falha ao criar conversa: {r.json()}")
            return None
    except Exception as e:
        logger.error(f"[CRM] Erro ao criar conversa: {e}")
        return None

    # ─── 3. Registrar mensagem enviada ───────────────────────────────────────
    try:
        conteudo = (
            f"📱 Template *{template_name}* enviado via WhatsApp\n"
            f"👤 Distribuidor: {nome}\n"
            f"📞 Número: +{telefone}\n"
            f"🆔 ID Meta: {meta_msg_id}"
        )
        r = requests.post(
            f"{base}/conversations/{conv_id}/messages",
            headers=headers,
            json={"content": conteudo, "message_type": "outgoing", "private": True},
            timeout=8,
        )
        if r.status_code in (200, 201):
            logger.info(f"[CRM] ✅ Mensagem registrada na conversa {conv_id}")
        else:
            logger.error(f"[CRM] Falha ao registrar mensagem: {r.json()}")
    except Exception as e:
        logger.error(f"[CRM] Erro ao registrar mensagem: {e}")

    return conv_id


def _registrar_no_pipeline(conv_id: int) -> bool:
    """
    Busca o pipeline correto e cadastra a conversa no estágio adequado.

    Variáveis de ambiente (em ordem de prioridade):
        CRM_PIPELINE_ID          → ID direto do pipeline (mais rápido)
        CRM_PIPELINE_NAME        → Busca pelo nome do pipeline (padrão: "distribuidor")
        CRM_PIPELINE_STAGE_ID    → ID direto do estágio
        CRM_PIPELINE_STAGE_NAME  → Busca pelo nome do estágio (padrão: "novo distribuidor")
    """
    crm_url = os.getenv("CRM_URL", "https://crm.kaiabi.com").rstrip("/")
    crm_token = os.getenv("CRM_API_TOKEN", "").strip()

    if not crm_token:
        logger.warning("[CRM Pipeline] CRM_API_TOKEN não configurado — pulando registro no pipeline.")
        return False

    headers = {"api_access_token": crm_token, "Content-Type": "application/json"}
    base = f"{crm_url}/api/v1"

    # Configurações via env vars
    pipeline_id_env   = os.getenv("CRM_PIPELINE_ID", "").strip()
    pipeline_name_env = os.getenv("CRM_PIPELINE_NAME", "distribuidor").strip().lower()
    stage_id_env      = os.getenv("CRM_PIPELINE_STAGE_ID", "").strip()
    stage_name_env    = os.getenv("CRM_PIPELINE_STAGE_NAME", "novo distribuidor").strip().lower()

    # ── 1. Resolver o pipeline ──────────────────────────────────────────────
    pipeline_id   = pipeline_id_env if pipeline_id_env else None
    pipeline_data = None

    if not pipeline_id:
        try:
            r = requests.get(f"{base}/pipelines", headers=headers, timeout=8)
            if r.status_code == 200:
                pipelines = r.json().get("data", [])
                if not pipelines:
                    logger.warning("[CRM Pipeline] Nenhum pipeline encontrado.")
                    return False

                # Prioridade 1: pipeline cujo nome contenha a keyword configurada
                matched = next(
                    (p for p in pipelines if pipeline_name_env in (p.get("name") or "").lower()),
                    None
                )
                # Prioridade 2: pipeline padrão
                if not matched:
                    matched = next((p for p in pipelines if p.get("is_default") is True), None)
                # Prioridade 3: primeiro da lista
                if not matched:
                    matched = pipelines[0]

                pipeline_id   = matched.get("id")
                pipeline_data = matched
                logger.info(
                    f"[CRM Pipeline] Pipeline selecionado: id={pipeline_id} | nome='{matched.get('name')}'"
                )
            else:
                logger.error(f"[CRM Pipeline] Erro ao buscar pipelines: {r.status_code} — {r.text}")
                return False
        except Exception as e:
            logger.error(f"[CRM Pipeline] Exceção ao buscar pipelines: {e}")
            return False

    if not pipeline_id:
        return False

    # ── 2. Resolver o estágio ───────────────────────────────────────────────
    stage_id = stage_id_env if stage_id_env else None

    if not stage_id:
        # Buscar estágios do pipeline selecionado
        try:
            r = requests.get(
                f"{base}/pipelines/{pipeline_id}/pipeline_stages",
                headers=headers,
                timeout=8,
            )
            if r.status_code == 200:
                stages = r.json().get("data", [])
                if stages:
                    # Prioridade 1: estágio cujo nome contenha a keyword configurada
                    matched_stage = next(
                        (s for s in stages if stage_name_env in (s.get("name") or "").lower()),
                        None
                    )
                    # Prioridade 2: primeiro estágio do pipeline
                    if not matched_stage:
                        matched_stage = stages[0]

                    stage_id = matched_stage.get("id")
                    logger.info(
                        f"[CRM Pipeline] Estágio selecionado: id={stage_id} | nome='{matched_stage.get('name')}'"
                    )
            else:
                logger.warning(
                    f"[CRM Pipeline] Não foi possível buscar estágios: {r.status_code} — pulando stage_id."
                )
        except Exception as e:
            logger.warning(f"[CRM Pipeline] Exceção ao buscar estágios: {e} — pulando stage_id.")

    # ── 3. Cadastrar conversa no pipeline com o estágio correto ────────────
    try:
        payload: dict = {
            "type": "conversation",
            "item_id": str(conv_id),
        }
        if stage_id:
            payload["pipeline_stage_id"] = str(stage_id)

        r = requests.post(
            f"{base}/pipelines/{pipeline_id}/pipeline_items",
            headers=headers,
            json=payload,
            timeout=8,
        )
        if r.status_code in (200, 201):
            logger.info(
                f"[CRM Pipeline] ✅ Conversa {conv_id} registrada no pipeline {pipeline_id}"
                f"{f' / estágio {stage_id}' if stage_id else ''}"
            )
            return True
        else:
            logger.error(
                f"[CRM Pipeline] Falha ao registrar conversa: {r.status_code} — {r.text}"
            )
            return False
    except Exception as e:
        logger.error(f"[CRM Pipeline] Exceção ao registrar no pipeline: {e}")
        return False




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
            _registrar_no_pipeline(conv_id)
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
