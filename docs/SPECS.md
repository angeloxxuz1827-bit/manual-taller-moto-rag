# Especificaciones — manual-taller-moto-rag

- **Congelado el**: 2026-10-22
- **Regla**: cualquier cambio de decisión se anota aquí (y su porqué en `.opencode/memory/memory.md`).
- **Leyenda**: ✅ realizada/decidida · 🚧 en curso · ⬜ pendiente · 🔮 futuro

---

## 1. Especificaciones realizadas (✅ decididas)

### 1.1 Objetivo

RAG end-to-end sobre el manual de taller de una motocicleta en PDF, con etapas **modulares y claramente separadas**: fuente (local + S3) → chunking → embeddings → vector store → retrieval → respuesta. Interfaz inicial Telegram, estructura preparada para migrar a EC2.

### 1.2 Stack (decidido)

| Capa | Elección | Nota |
|---|---|---|
| Lenguaje | Python 3.14 (`.venv` existente) | Compatibilidad de dependencias verificada |
| Orquestación IA | **LangChain 1.x** (+ `langchain-aws`) | API 1.x, no 0.x |
| LLM | **AWS Bedrock**, modelo por `.env` | Default: `anthropic.claude-haiku-4-5-20251001-v1:0` |
| Embeddings | **`amazon.titan-embed-text-v2:0`** | 1024 dims; cambiarlo ⇒ reindexar |
| Vector store V1 | **ChromaDB local** (persistencia en disco) | |
| Vector store V2 | **Supabase pgvector** | 🔮 Fase 10, fuera de la V1 |
| Storage | **S3 real (boto3) + driver local** | Bucket `manual-taller-moto-rag-610433739351` ✅ creado 2026-10-22 |
| Extracción PDF | **Texto + tablas** (pdfplumber + PyMuPDF) | Imágenes/diagramas fuera de alcance V1 |
| Retrieval | **MMR** | `k`, `fetch_k`, `lambda_mult` configurables |
| Citas | **Sí: página/capítulo** | Requiere metadata en chunks |
| Memoria | **Historial de N turnos/usuario** | N inicial = 6 (configurable) |
| Interfaz | **Telegram vía adaptador** sobre la librería propia del usuario | El núcleo no depende de Telegram |
| Dependencias | **pip + requirements.txt** | No uv/poetry |
| Docker | **Sí, desde el inicio** (`docker-compose`) | Preparado para EC2 |
| Git | **Init + commits por etapa** | Siempre con aprobación explícita |
| Evaluación | **Set de pruebas de retrieval** | `tests/evals/queries.json` + `scripts/evaluate.py` |
| Memoria del agente | **`.opencode/memory/`** | `INDEX.md` + `memory.md` |
| Idioma de respuesta | **Español** | |

### 1.3 Requisitos funcionales

- **RF-01** El PDF vive en `data/manual/` (origen local) y se almacena en el bucket S3; un driver local permite pruebas sin nube.
- **RF-02** Extracción de texto **y tablas** conservando el **nº de página** de cada elemento.
- **RF-03** Chunking con metadata (página, sección, fuente) e **IDs estables** para re-ingestas sin duplicados.
- **RF-04** Pipeline de ingesta **idempotente** ejecutable por CLI (`scripts/ingest.py`).
- **RF-05** Retrieval **MMR** con parámetros por `.env`.
- **RF-06** Respuesta en **español** con **citas** (página/capítulo) y formato consistente.
- **RF-07** Memoria de conversación: últimos N turnos por usuario de Telegram.
- **RF-08** Doble interfaz: **CLI local** (pruebas) y **adaptador Telegram** (interfaz inicial).
- **RF-09** Toda la configuración por **`.env`** (`.env.example` documenta variables sin secretos).
- **RF-10** **Docker Compose** funcional desde la V1.
- **RF-11** Set de evaluación de retrieval con queries representativas y de borde.

### 1.4 Requisitos no funcionales

- **RNF-01 Modularidad**: puertos (`base.py`) + adaptadores; cambiar proveedor/nube no toca el negocio.
- **RNF-02 Sin secretos en el repo** ni en la memoria del agente.
- **RNF-03 Idempotencia**: re-ingerir no duplica chunks.
- **RNF-04 Sin dependencia del CWD**: paths resueltos desde la raíz del proyecto.
- **RNF-05 Verificabilidad**: cada fase cierra con un criterio de aceptación ejecutable.

### 1.5 Configuración prevista (`.env.example`, crear en Fase 0)

| Variable | Ejemplo / default | Fase |
|---|---|---|
| `AWS_REGION` | `us-east-2` | F1 |
| `S3_BUCKET` | `manual-taller-moto-rag-610433739351` | F1 |
| `STORAGE_DRIVER` | `local` \| `s3` | F1 |
| `LOCAL_DATA_DIR` | `./data` | F1 |
| `BEDROCK_CHAT_MODEL_ID` | `anthropic.claude-haiku-4-5-20251001-v1:0` | F6 |
| `BEDROCK_EMBED_MODEL_ID` | `amazon.titan-embed-text-v2:0` | F4 |
| `EMBEDDINGS_DIMENSIONS` | `1024` | F4 |
| `VECTORSTORE_DRIVER` | `chroma` \| `supabase` | F4/F10 |
| `CHROMA_PERSIST_DIR` | `./.chroma` | F4 |
| `CHUNK_SIZE` / `CHUNK_OVERLAP` | `1200` / `150` (propuesto, ajustar con el PDF real) | F3 |
| `RETRIEVAL_K` / `MMR_FETCH_K` / `MMR_LAMBDA_MULT` | `6` / `20` / `0.5` | F5 |
| `MEMORY_MAX_TURNS` | `6` | F6 |
| `TELEGRAM_BOT_TOKEN` | (secreto, va en `.env` del usuario) | F7 |
| `LOG_LEVEL` | `INFO` | F0 |

---

## 2. Fases de implementación

### Fase 0 — Scaffolding del proyecto ✅ (completada 2026-10-22)

- ✅ `AGENTS.md`, `docs/SPECS.md`, `.opencode/memory/` (INDEX + memory)
- ✅ `git init -b main` + `.gitignore` (excluye `.venv/`, `.env`, PDFs de `data/`, `.chroma/`, `__pycache__/`)
- ✅ `requirements.txt` con **versiones fijadas**: langchain 1.4.7 · langchain-aws 1.9.0 · langchain-chroma 1.1.0 · chromadb 1.5.9 · boto3 1.43.117 · pymupdf 2.0 · pdfplumber 0.11.10 · python-dotenv 1.2.4 · pytest 9.1.1
- ✅ `pyproject.toml` (setuptools, layout `src/`) + instalación editable `pip install -e .` — necesario para que `import manual_taller_rag` funcione sin `PYTHONPATH`
- ✅ `.env.example` (todas las variables de §1.5), `README.md`
- ✅ Estructura `src/manual_taller_rag/` (8 paquetes con `__init__.py`), `scripts/`, `tests/` (+ smoke test), `data/manual/`
- ✅ **Criterio de aceptación verificado**: instalación limpia en Python 3.14 · `import manual_taller_rag` → `OK 0.1.0` · `pytest` → `1 passed`

### Fase 1 — Storage (local + S3) ✅ (completada 2026-10-22)

- ✅ Puerto `StoragePort` (`put_file`, `get_file`, `exists`, `list`, `delete`) + adaptadores `local.py` y `s3.py`; errores **normalizados** (`FileNotFoundError` en ambos) y rechazo de path traversal en local
- ✅ `config.py`: `Settings` (dataclass con todos los valores de `.env.example`) + fábrica `get_storage()` según `STORAGE_DRIVER`; paths relativos resueltos contra la raíz del proyecto
- ✅ **Bucket `manual-taller-moto-rag-610433739351` creado** en `us-east-2` (ARN `arn:aws:s3:::manual-taller-moto-rag-610433739351`)
- ✅ **Criterio de aceptación verificado**: mismo round-trip (subida → descarga con **hash idéntico** → borrado idempotente) para local y S3 real → `5 passed, 1 skipped` (suite local) + `1 passed` (S3)
- ⬜ Pendiente: subir el **PDF real** cuando esté en `data/manual/` (la subida completa vive en `scripts/ingest.py`, Fase 4)
- Nota: `test_s3_round_trip` toca la nube sólo con `RUN_S3_TESTS=1` (fuera de la suite por defecto)

### Fase 2 — Extracción del PDF

- ⬜ `extractor.py`: párrafos de texto + tablas detectadas, cada elemento con `page_number`
- ⬜ Tablas a formato legible para el LLM (Markdown)
- ⬜ Test con el PDF real (`data/manual/`)
- **Criterio**: una tabla de torque real se extrae legible y con su página.

### Fase 3 — Chunking

- ⬜ `chunker.py` con LangChain splitter: `CHUNK_SIZE`/`CHUNK_OVERLAP` por config
- ⬜ Metadata (`page`, `section`, `source`) + **IDs estables** (hash)
- ⬜ Ajuste de parámetros tras revisar el PDF real (ver §3)
- **Criterio**: metadata presente en el 100% de los chunks; sin pérdida de texto.

### Fase 4 — Embeddings + vector store

- ⬜ `embeddings/bedrock_titan.py` (vía `langchain-aws`, 1024d)
- ⬜ `vectorstore/chroma.py` (puerto + adaptador, persistencia en disco)
- ⬜ `scripts/ingest.py` end-to-end: storage → extract → chunk → embed → index, **idempotente**
- **Criterio**: doble ejecución de ingesta no duplica; búsqueda devuelva chunks coherentes.

### Fase 5 — Retrieval + evaluación

- ⬜ `retriever.py` con **MMR** y parámetros por config
- ⬜ `tests/evals/queries.json`: queries representativas (procedimientos, torque, códigos de pieza) y de borde (fuera de alcance, mal escritas)
- ⬜ `scripts/evaluate.py`: métrica **recall@k / hit@k** sobre el set
- **Criterio**: el set pasa; umbral inicial a fijar tras la primera corrida.

### Fase 6 — Generación + memoria

- ⬜ `generation/prompts.py` (contexto + instrucción de cita + idioma español) y `llm.py` (modelo por `.env`)
- ⬜ `chat_history.py`: historial N turnos por usuario
- ⬜ `rag.py`: orquestación retrieval → respuesta con fuentes
- **Criterio**: toda respuesta cita página/capítulo; "¿y el par 2?" resuelve con el contexto previo.

### Fase 7 — Interfaces (CLI + Telegram)

- ⬜ `interfaces/cli.py`: REPL local para pruebas sin Telegram
- ⬜ `interfaces/telegram_adapter.py`: traduce la **librería propia del usuario** (a cargar en el proyecto) al núcleo RAG; manejo de errores y rate limits básicos
- **Criterio**: el bot responde en Telegram usando el RAG completo.

### Fase 8 — Docker

- ⬜ `Dockerfile` + `docker-compose.yml` (servicio app; Chroma embebido en V1)
- **Criterio**: `docker compose up --build` levanta el bot/CLI en una máquina limpia.

### Fase 9 — 🔮 Migración a EC2 (futuro)

- Notas de diseño ya previstas: mismo compose; secrets vía entorno; security group restringido; logging a archivo/cloudwatch básico; la memoria N turnos actual es **en memoria** ⇒ en EC2 multi-proceso valorar persistencia (Redis o BD).

### Fase 10 — 🔮 Supabase pgvector (futuro)

- ⬜ `vectorstore/supabase_pgvector.py` sobre el mismo `VectorStorePort`
- ⬜ Migración del índice: re-ingerir desde S3 (los embeddings se recalculan)
- ⬜ Variables nuevas: `SUPABASE_URL`, `SUPABASE_SERVICE_KEY` (o conexión Postgres directa)

---

## 3. Decisiones pendientes (abiertas)

| # | Decisión | Estado | Nota |
|---|---|---|---|
| D-01 | `CHUNK_SIZE` / `CHUNK_OVERLAP` definitivos | ⬜ | Propuesto 1200/150; ajustar observando el PDF real |
| D-02 | N de turnos de memoria | ⬜ | Propuesto 6 |
| D-03 | Umbral de similitud para responder "no lo sé" | ⬜ | Definir tras métricas de F5 |
| D-04 | Formato de tabla dentro de los chunks | ⬜ | Markdown propuesto |
| D-05 | Set de queries de evaluación y umbral | ⬜ | Se define en F5 con el PDF indexado |
| D-06 | Cómo carga el usuario su librería de Telegram al proyecto | ⬜ | Condiciona el contrato de `telegram_adapter.py` (F7) |
| D-07 | Estrategia de despliegue en EC2 (systemd vs compose) | 🔮 | Se decide en F9 |

---

## 4. Riesgos conocidos

- **Imágenes/diagramas** del manual quedan fuera del alcance V1 (solo texto+tablas).
- **Coste de ingesta**: 1024 dims por chunk en Bedrock; dimensionar según nº de páginas.
- **Cambio de modelo de embeddings** ⇒ reindex completo (F4 debe permitir reconstrucción total).
- **Errores de extracción** en PDFs con columnas/tablas complejas ⇒ mitigar con tests sobre el PDF real (F2).
- **Memoria en memoria**: no sobrevive reinicios; aceptable en V1, revisar en F9.
