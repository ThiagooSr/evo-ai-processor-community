# Changelog

All notable changes to this microservice will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [v1.0.0-rc3] - 2026-05-17

Release de integração — adiciona ferramentas nativas para o LLM agent (Knowledge Nexus search, manage_conversation_labels, link_product_to_pipeline_item), injeção de catálogo de products no contexto do agente, merge das integrações da tabela `agent_integrations` na config do agente em runtime, e correção de bugs em handshake de Postgres e binding do chat handler. Também declara `EXTENSION_POINTS.md` como contrato público de extensão para a Enterprise edition.

### Added

- **EXTENSION_POINTS.md (EVO-1376)** (#9) — documento com os pontos de extensão expostos pelo processor para a Enterprise edition. Contrato versionado, sem código novo.
- **`knowledge_nexus_search` — tool nativa** — agentes ganham acesso a busca semântica em spaces do Nexus diretamente do prompt, sem necessidade de configurar tool customizada.
- **`manage_conversation_labels` — tool nativa** — list/add/remove de labels na conversa pelo próprio agente.
- **`link_product_to_pipeline_item` — tool nativa** — agente consegue linkar products do catálogo ao item de pipeline ativo.
- **Catálogo de products no contexto do agente** — products attachados ao agente são injetados no prompt, permitindo que o LLM tenha contexto da oferta.
- **Hints de uso de pipeline e labels no prompt** — `pipeline_manipulation` e `manage_labels` ganham hints estruturados no system prompt para orientar o LLM sobre quando e como usar.

### Changed

- **`llm-agent` — merge de integrações** — integrações da tabela `agent_integrations` agora são mescladas na config do agente em runtime. Antes a config era estática; agora reflete o estado mais recente das integrações configuradas via UI.
- **Docs** padronizados para Evolution Foundation 2026 (README, LICENSE, NOTICE, TRADEMARKS).
- **Docs (org)** — URLs do GitHub atualizadas de `EvolutionAPI` para `evolution-foundation`.

### Fixed

- **DB — `sslmode` → `ssl` para asyncpg** — o driver asyncpg não entende `sslmode` (parâmetro psycopg/libpq). Conexões com `sslmode=require` na connection string falhavam silenciosamente; agora traduzimos para o parâmetro nativo do asyncpg.
- **Chat handler — request param rebind** — corrige binding do parâmetro `request` no chat handler que causava `NameError` em determinados caminhos de erro.

## [v1.0.0-rc2] - 2026-05-05

### Fixed

- **Container startup**: invocar `alembic` e `uvicorn` via `python -m` em vez de console scripts, evitando que `sh -c` interprete os entrypoints incorretamente em algumas imagens. (#7)
- **Migration `26a14ac7025d`**: adicionado `if_not_exists=True` no `op.create_table('evo_agent_processor_execution_metrics')`, tornando a migration segura para re-run em ambientes onde a tabela já foi criada por outro serviço (banco compartilhado). (#7)

## [v1.0.0-rc1] - 2026-04-24

### Added

- Primeiro release candidate público do `evo-ai-processor-community`.

### Changed

- Refatorado para remover parâmetro `account_id` em services internos.
- Adicionado workflow de publish multi-arch no Docker Hub.
- Adicionado workflow de build/publish de imagens `develop` para staging.

### Fixed

- Resolvido `UnboundLocalError` em `run_seeders.py`.
- Adicionado `checkfirst` ao `SQLAlchemy create_all` para evitar `DuplicateTableError`.
- Corrigida ordem de middlewares e condições de CORS / rate limiting.
- `agent retrieval` migrado para chamadas assíncronas com refinamento de tratamento de erros no `EvoAuthService`.
- Tratamento de erros aprimorado em response utility e tool de mensagens privadas.
- Adicionado método `PATCH` ao `EvoCrmClient` e suporte a `stage_name` na ferramenta de manipulação de pipelines.
- Removido campo não utilizado `CORS_ORIGINS` do `settings`.
- **EVO-972**: serializa `set` em respostas JSON e enriquece superfície de erro de auth. (#6)

### Security

- Removida chave de service account GCP que vazou em commits anteriores. (#4)

## [0.1.0] - 2025-07-02

### Added

- JWT authentication via external service with FastAPI HTTPBearer integration
- Route-level protection: only sensitive endpoints require authentication
- Public endpoints (e.g. `/supported-formats`, `/health/status`) accessible without authentication
- Centralized configuration for external auth service via environment and settings
- Improved OpenAPI/Swagger experience with proper security scheme
- Error handling for unavailable or invalid authentication service
- English documentation and codebase

### Changed

- Refactored authentication logic to remove global dependencies and middleware
- Cleaned up project dependencies and removed unused packages
- Updated project structure and documentation to reflect microservice boundaries
- Improved logging and error messages for authentication and service health

### Fixed

- Fixed 401 errors on public endpoints by isolating JWT validation to protected routes only
- Fixed Swagger not sending Authorization header by using FastAPI security scheme

### Security

- All protected endpoints require valid JWT validated by external service
- No sensitive data exposed in logs or error messages

---

Older versions and future releases will be listed here.
