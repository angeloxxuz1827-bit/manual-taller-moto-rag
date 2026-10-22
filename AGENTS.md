# AGENTS.md — manual-taller-moto-rag

## Qué es este proyecto

RAG end-to-end sobre el **manual de taller de una motocicleta (PDF)**. Flujo principal:

```
PDF (data/manual/ y S3)
  → extracción (texto + tablas, con nº de página)
  → chunking con metadata (página / sección / fuente)
  → embeddings Bedrock (Titan Text Embed v2, 1024 dimensiones)
  → vector store (Chroma local en V1; Supabase pgvector en fase futura)
  → retrieval MMR
  → respuesta en español con citas (página/capítulo) vía LLM Bedrock configurable
  → interfaz inicial Telegram (adaptador sobre la librería propia del usuario)
     con estructura preparada para migrar a EC2
```

## Documentos de contexto (leer antes de tocar nada)

1. `docs/SPECS.md` — especificaciones **realizadas (✓)** y **pendientes**, organizadas por fases (F0–F10).
2. `.opencode/memory/INDEX.md` — índice de la memoria del proyecto; cargar solo los archivos que indique.

Si ambos entran en conflicto, **manda `docs/SPECS.md`** y avisar al usuario.

## Arquitectura: puertos y adaptadores

- Cada capa define su **interfaz** en `base.py` (puerto): `storage`, `embeddings`, `vectorstore`.
- Las implementaciones concretas (adaptadores) se eligen por **variable de entorno** vía `config.py`.
- **Regla:** salvo `config.py` (o su factory), ninguna capa importa un adaptador concreto.
- Cambiar de proveedor o de nube **no debe** tocar la lógica de negocio (ingest, retrieval, generación).
- `interfaces/` solo traduce entradas/salidas externas (Telegram, CLI) al núcleo RAG. El núcleo no conoce Telegram.

## Mapa del proyecto

| Ruta | Responsabilidad |
|---|---|
| `src/manual_taller_rag/config.py` | Settings leídos de `.env`; construcción de adaptadores |
| `src/manual_taller_rag/storage/` | `base.py` (puerto), `local.py`, `s3.py` |
| `src/manual_taller_rag/ingestion/` | `extractor.py` (PDF texto+tablas), `chunker.py`, `pipeline.py` (idempotente) |
| `src/manual_taller_rag/embeddings/` | `base.py`, `bedrock_titan.py` (1024d) |
| `src/manual_taller_rag/vectorstore/` | `base.py`, `chroma.py`, `supabase_pgvector.py` (stub, fase futura) |
| `src/manual_taller_rag/retrieval/` | `retriever.py` (MMR, parámetros por config) |
| `src/manual_taller_rag/generation/` | `prompts.py`, `llm.py` (modelo por `.env`) |
| `src/manual_taller_rag/chat_history.py` | Historial de N turnos por usuario |
| `src/manual_taller_rag/rag.py` | Cadena orquestadora: retrieval → respuesta con citas |
| `src/manual_taller_rag/interfaces/` | `cli.py` (pruebas locales), `telegram_adapter.py` |
| `scripts/` | `ingest.py`, `evaluate.py` |
| `tests/` | Tests + `evals/queries.json` (set de evaluación) |
| `data/manual/` | PDF local (origen en desarrollo) |
| `docs/SPECS.md` | Especificaciones realizadas y pendientes |

## Comandos

```powershell
# Instalación (usar el .venv existente de Python 3.14; NO recrearlo)
pip install -r requirements.txt

# Ingesta (local → S3 → indexar) — habilitado en Fase 4
python scripts/ingest.py --file data/manual/<manual>.pdf

# Evaluación de retrieval — habilitado en Fase 5
python scripts/evaluate.py

# Tests
python -m pytest

# REPL local sin Telegram — habilitado en Fase 7
python -m manual_taller_rag.interfaces.cli

# Docker — habilitado en Fase 8
docker compose up --build
```

> Los comandos se activan conforme se completan las fases; el estado vive en `docs/SPECS.md`.

## Convenciones

- **Python 3.14** con el `.venv` existente; no recrearlo sin pedirlo.
- Dependencias solo vía `requirements.txt` (pip). Toda dependencia nueva se añade ahí.
- **LangChain 1.x** (API actual). No copiar ejemplos de 0.x (`LLMChain`, `from_documents` antiguo, etc.).
- **Secrets**: únicamente `.env` (nunca en el repo ni en la memoria). `.env.example` documenta variables **sin valores**.
- Type hints en todo el código público; docstrings breves en español.
- Idioma: código/comentarios/docstrings en español; **las respuestas del RAG al usuario, en español**.
- **Ingesta idempotente**: IDs estables por chunk (hash de contenido + página) o borrar/reindexar antes de re-ingerir. Sin duplicados en Chroma.
- **Paths**: resolver desde la raíz del proyecto, jamás depender del CWD.
- Guardar en metadata de cada chunk lo necesario para **citar** (página, sección) y para **depurar** (id, fuente).

## Reglas de trabajo (aprobaciones)

Requieren **aprobación explícita del usuario** antes de ejecutarse:

- Commits, pushes, merges y cualquier operación git destructiva.
- Creación o modificación de recursos cloud (bucket S3, modelos Bedrock, EC2, Supabase).
- Borrado o sobrescritura de archivos ajenos a los aprobados.

Procedimiento estándar:

1. Analizar e investigar (solo lectura) antes de proponer.
2. Proponer el plan mínimo y esperar aprobación.
3. Tras un cambio aprobado, ejecutar la **menor verificación relevante** (pytest, script de ingesta, comando suelto).
4. Actualizar `docs/SPECS.md` (✓/pendiente) y la memoria si hay decisiones nuevas.

## Estado actual

**Fase 0 completada (2026-10-22)**: documentos de contexto, `git init -b main`, scaffolding
(`requirements.txt` fijado, `pyproject.toml` con instalación editable, `.env.example`, README,
estructura `src/`) y verificación de import + smoke test. **Siguiente: Fase 1 (storage local + S3).**
