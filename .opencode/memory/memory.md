# memory.md — contexto de manual-taller-moto-rag

> Última actualización: 2026-10-22. Las especificaciones viven en `docs/SPECS.md`;
> aquí se guarda el **porqué** de las decisiones y el estado del entorno.

## Decisiones técnicas (y su porqué)

| Área | Decisión | Porqué |
|---|---|---|
| LLM | AWS Bedrock, modelo por `.env` (`BEDROCK_CHAT_MODEL_ID`); default `anthropic.claude-haiku-4-5-20251001-v1:0` | Unifica con S3/EC2 en AWS (una sola factura/credencial). Elegido "configurable por .env" para poder comparar modelos sin tocar código. |
| Embeddings | `amazon.titan-embed-text-v2:0`, **1024 dimensiones** | Nativo AWS y verificado disponible en `us-east-2`. **Si cambia el modelo, hay que reindexar todo** (misma dimensión no garantiza mismo espacio vectorial). |
| Vector store V1 | ChromaDB local persistido en disco | Cero infraestructura para pruebas locales; integración directa con LangChain. |
| Vector store V2 | Supabase pgvector (fase futura) | Mismo puerto `VectorStorePort`; la migración no toca el resto del pipeline. Decidido como **fase 2, fuera de la V1**. |
| Storage | Driver local + driver S3 real (boto3); PDF de origen en `data/manual/` | Requisito: nube y local para pruebas. Bucket dedicado `manual-taller-moto-rag-610433739351` (**por crear**, requiere aprobación). |
| Extracción PDF | Texto **y tablas** (pdfplumber + PyMuPDF), conservando nº de página | Los manuales de taller concentran datos críticos en tablas (torque, tolerancias, circuitos). Imágenes/diagramas: **fuera de alcance** en V1. |
| Chunking | Con metadata de página/sección/fuente + IDs estables | Habilita citas en la respuesta e ingesta idempotente. Tamaño exacto: pendiente de ver el PDF real. |
| Retrieval | **MMR** (parámetros `k`, `fetch_k`, `lambda_mult` por config) | Evita resultados duplicados/solapados (p. ej. procedimiento + su tabla de torque). |
| Respuestas | En **español**, con **citas página/capítulo** | Confianza del usuario y facilidad de debugging. |
| Memoria | Historial de **N turnos por usuario** (arranque N=6, configurable) | Soporta preguntas de seguimiento ("¿y el par 2?") sin estado complejo. |
| Telegram | **Librería propia del usuario** vía `interfaces/telegram_adapter.py` | El usuario ya tiene librería para enviar/recibir mensajes y la cargará al proyecto; el núcleo RAG no depende de ningún paquete de Telegram. |
| Dependencias | pip + `requirements.txt`, `.venv` de Python 3.14 existente | Decisión explícita del usuario; venv NO se recrea. |
| Docker | `docker-compose` desde el inicio | Facilita la migración posterior a EC2. |
| Git | Init + commits por etapa, **siempre con aprobación explícita** | Regla global de trabajo. |
| Evaluación | Set de queries (`tests/evals/queries.json`) + `scripts/evaluate.py` | Detectar regresiones de retrieval tras cada cambio. |

## Infraestructura verificada (2026-10-22, solo lectura)

- **AWS**: cuenta `610433739351`, usuario IAM `vscode-dev`, región **`us-east-2`** (`sts get-caller-identity` OK).
- **Bedrock en us-east-2**: disponibles `anthropic.claude-haiku-4-5-20251001-v1:0`, `anthropic.claude-sonnet-4-6`, `amazon.nova-*-v1:0`, `amazon.titan-embed-text-v2:0`.
- **S3**: bucket del proyecto **`manual-taller-moto-rag-610433739351` creado (2026-10-22, us-east-2)**; además existen `bucket-test-entrevista` y `telegram-raw-messages-angel-...`.
- **Python**: `.venv` con 3.14.6. Compatibilidad confirmada en PyPI: `langchain` 1.4.7, `langchain-openai` 1.7.2, `chromadb` 1.5.9 (wheels abi3), `pymupdf` 2.0, `pdfplumber` 0.11.10, `boto3` 1.43.
- **Telegram**: token del bot en manos del usuario (no almacenar en memoria ni en el repo; irá a `.env`).

## Estado de fases

Ver checklist completo en `docs/SPECS.md`. **F0–F3 completadas (2026-10-22)**: scaffolding; storage local+S3 con bucket; extractor pdfplumber (1654 bloques, 623/626 páginas, ≈6 min); chunker con tablas atómicas, metadata 100% e IDs estables (2017 chunks: 986 texto + 1031 tablas; D-01 cerrado con 1200/150). Suite: `23 passed, 1 skipped`. F4–F8 pendientes; F9 (EC2) y F10 (Supabase) futuras.

## Aprendizajes

- **LangChain está en 1.x**: los ejemplos de la web en versión 0.x (`LLMChain`, cadenas clásicas) ya no aplican; usar LCEL / API 1.x y `langchain-aws` para Bedrock.
- `chromadb` publica wheels `abi3` y `onnxruntime` 1.31 tiene wheel `cp314-win_amd64` → todo instala limpio en Python 3.14.
- `list-foundation-models` de AWS CLI devuelve `modelSummaries` (no `foundationModelSummaries`).
- Con layout `src/` hace falta **instalación editable** (`pip install -e .` vía `pyproject.toml`) o `pythonpath = ["src"]` en pytest; sin eso, `import manual_taller_rag` falla.
- **Errores normalizados en el puerto**: `FileNotFoundError` tanto en local como en S3, para que la capa superior no dependa del proveedor. Ojo con `pytest.raises(match=...)`: evitar palabras con acento en el patrón si la consola no los maneja bien (falló con "raíz").
- **PyMuPDF 2.0 `find_tables` cuesta 5–8 s/página** (modelo de layout `pymupdf-layout`, sin caché): inviable en 626 páginas. **pdfplumber**: 0,05–0,2 s/página y detectó tablas en **402/626** páginas → extractor reescrito en pdfplumber (D-08).
- **Caracteres PUA de la fuente Symbol**: el manual usa U+F0D7 (`N·m`, 191 usos) y U+F046 (`→ (Página …)`, 1837 usos). Al teclearlos literalmente es inevitable confundirlos (se escribió U+F057 por U+F0D7 **dos veces**, invisible en el fuente) → **siempre `chr(0x…)` o escapes**, y verificar con `print([hex(k) for k in MAPA])`.
- La consola de Windows (cp1252) **no puede imprimir `→`** y lanza `UnicodeEncodeError` → usar `PYTHONIOENCODING=utf-8` en pytest/scripts.
- **Chroma exige IDs únicos**: bloques hermanos idénticos (fragmentos de tabla repetidos en una página) generaban hashes colisionados → el ID lleva el **ordinal del bloque** dentro de su grupo (página, tipo); determinista aunque se procese un subconjunto de páginas. Siempre test de regresión para esto.

## Próxima acción

1. **Commit de la Fase 3** — aprobado por el usuario (stats de D-01 y fix de IDs incluidos).
2. **Fase 4**: embeddings Bedrock (Titan v2, 1024d) + `vectorstore/chroma.py` + `scripts/ingest.py` idempotente — **pendiente de aprobación** (el usuario pidió solo commit de F3 por ahora; implica llamadas reales a Bedrock).
3. Vigilar en F5 la calidad de las **1031 tablas** (mediana 75 chars: muchos fragmentos pequeños) con el set de evals.
