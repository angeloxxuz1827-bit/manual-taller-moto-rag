# manual-taller-moto-rag

RAG end-to-end sobre el **manual de taller de una motocicleta (PDF)**:

PDF (local `data/manual/` y S3) → extracción (texto + tablas, con página) → chunking con
metadata → embeddings Bedrock (Titan v2, 1024d) → Chroma local → retrieval **MMR** →
respuesta en español con **citas** vía LLM Bedrock configurable → interfaz inicial Telegram
(adaptador), con estructura preparada para migrar a **EC2** y con Supabase pgvector como
fase futura de vector store.

## Estado

Proyecto en **Fase 0** (scaffolding). El detalle de fases, requisitos y decisiones vive en:

- [`docs/SPECS.md`](docs/SPECS.md) — especificaciones realizadas y pendientes.
- [`AGENTS.md`](AGENTS.md) — convenciones, comandos y arquitectura (puertos/adaptadores).
- `.opencode/memory/` — memoria del proyecto para agentes.

## Puesta en marcha

```powershell
# 1. Dependencias (usa el .venv existente de Python 3.14)
pip install -r requirements.txt
pip install -e .

# 2. Configuración
Copy-Item .env.example .env   # rellenar secretos (TELEGRAM_BOT_TOKEN, etc.)

# 3. Tests
python -m pytest
```

## Estructura

```
src/manual_taller_rag/
├── config.py        # settings desde .env + construcción de adaptadores
├── storage/         # puertos y adaptadores: local | s3
├── ingestion/       # extractor (PDF) | chunker | pipeline idempotente
├── embeddings/      # bedrock_titan (1024d)
├── vectorstore/     # chroma (V1) | supabase_pgvector (fase futura)
├── retrieval/       # MMR
├── generation/      # prompts + llm (modelo por .env)
├── chat_history.py  # historial de N turnos por usuario
├── rag.py           # orquestación retrieval → respuesta con citas
└── interfaces/      # cli (pruebas) | telegram_adapter
scripts/             # ingest.py | evaluate.py
tests/               # tests + evals/queries.json
data/manual/         # PDF local (no se versiona)
```
