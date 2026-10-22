"""Exploración de chunks: extrae y chunkea páginas del manual sin hacer ingesta.

Permite ver en consola qué produciría la Fase 4 (embeddings/índice) para un
rango de páginas, con la metadata e IDs reales que se indexarían.

Uso:
    python scripts/preview_chunks.py                        # p.130 (tabla de par)
    python scripts/preview_chunks.py --paginas 116,130 --n 3 --ancho 350
    python scripts/preview_chunks.py --pdf ruta/otro.pdf --paginas 1-5

Nota: `--paginas todas` procesa las 626 páginas (~5 min).
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from manual_taller_rag.config import load_settings
from manual_taller_rag.ingestion.chunker import chunk_blocks
from manual_taller_rag.ingestion.extractor import extract_blocks

RAIZ = Path(__file__).resolve().parents[1]


def _parsear_paginas(texto: str) -> list[int] | None:
    """Convierte '116,130' o '1-5' en números de página; 'todas' → None."""
    if texto == "todas":
        return None
    paginas: list[int] = []
    for trozo in texto.split(","):
        trozo = trozo.strip()
        if "-" in trozo:
            inicio, fin = (int(x) for x in trozo.split("-", 1))
            paginas.extend(range(inicio, fin + 1))
        elif trozo:
            paginas.append(int(trozo))
    return paginas


def _pdf_por_defecto() -> Path | None:
    candidatos = sorted((RAIZ / "data" / "manual").glob("*.pdf"))
    return candidatos[0] if candidatos else None


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Extrae y chunkea páginas del manual para inspeccionarlos en consola."
    )
    parser.add_argument("--pdf", type=Path, default=None, help="Ruta del PDF (default: primer PDF de data/manual/)")
    parser.add_argument("--paginas", default="130", help="Páginas 1-based: '116,130', '1-5' o 'todas' (default: 130)")
    parser.add_argument("--n", type=int, default=5, help="Máximo de chunks a mostrar (default: 5)")
    parser.add_argument("--ancho", type=int, default=400, help="Caracteres por chunk a imprimir (default: 400)")
    args = parser.parse_args()

    settings = load_settings()
    pdf = args.pdf or _pdf_por_defecto()
    if pdf is None or not pdf.is_file():
        sys.exit(f"No se encontró el PDF. Colócalo en {RAIZ / 'data' / 'manual'} o usa --pdf <ruta>")

    paginas = _parsear_paginas(args.paginas)
    bloques = extract_blocks(pdf, pages=paginas)
    chunks = chunk_blocks(bloques, chunk_size=settings.chunk_size, chunk_overlap=settings.chunk_overlap)

    n_texto = sum(1 for c in chunks if c.metadata["kind"] == "text")
    rango = "todas" if paginas is None else ",".join(str(p) for p in paginas)
    print(f"PDF: {pdf.name} | páginas: {rango}")
    print(
        f"chunk_size={settings.chunk_size} overlap={settings.chunk_overlap} | "
        f"bloques: {len(bloques)} -> chunks: {len(chunks)} (texto {n_texto}, tabla {len(chunks) - n_texto})"
    )
    print(f"mostrando {min(args.n, len(chunks))} de {len(chunks)} chunks:\n")

    for chunk in chunks[: args.n]:
        meta = chunk.metadata
        print(f"--- [{meta['kind']}] page={meta['page']} chunk={meta['chunk_index']} id={chunk.id} ({len(chunk.page_content)} chars)")
        print(chunk.page_content[: args.ancho])
        print()


if __name__ == "__main__":
    main()
