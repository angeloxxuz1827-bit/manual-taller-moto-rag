# Desafíos de ingesta: por qué el chunking "directo" sobre el PDF no funciona

> Historia viva de las fases F2 (extracción) y F3 (chunking) del manual de taller
> **Suzuki GSX250 / Gixxer 250** (626 páginas, ~81 MB). Cada desafío incluye la
> medida tomada y su decisión asociada (D-xx de `SPECS.md`).

## Resumen ejecutivo

Un PDF de manual de taller **no es un texto plano**: es una maquetación con
columnas, tablas densas en datos críticos, símbolos tipográficos no estándar y
fragmentos repetidos. Hacer `chunking` directo sobre el texto crudo produce
chunks ilegibles (columnas entrelazadas), datos partidos (filas de torque
cortadas por la mitad) y duplicados (una misma tabla aparece en el texto de
página *y* como tabla). El pipeline correcto es:

```
PDF → extracción por bloques (texto | tabla, con nº de página) → chunking → embeddings
```

Los desafíos concretos, en orden de impacto:

| # | Desafío | Impacto si se ignora | Medida (decisión) |
|---|---|---|---|
| 1 | Páginas a **dos columnas** | Texto entrelazado ilegible para el RAG | Texto con **PyMuPDF** (D-09) + test de orden |
| 2 | **Alto contenido de tablas** (1031 tablas en ~390 páginas) | Datos críticos (torque) perdidos o partidos | Tablas **atómicas** en Markdown (D-01/D-04) |
| 3 | **Duplicación** texto/tabla | El mismo dato indexado dos veces, chunks redundantes | Exclusión de celdas del texto de página |
| 4 | Símbolos **PUA** de la fuente Symbol | `N·m` y `→` salen como caracteres invisibles/corruptos | Normalización con `chr()` |
| 5 | Motor de detección de tablas | PyMuPDF detecta **0 tablas** en este PDF (5–8 s/pág) | pdfplumber para tablas (D-08) |
| 6 | **IDs estables** e ingesta idempotente | Re-ingerir duplica el índice en Chroma | sha256 con ordinal de bloque |
| 7 | Límites de **tokens** en embeddings | Tablas largas rechazadas por Titan v2 | Medición post-chunking (máx ~2.700 tokens) |

---

## 1. Páginas a dos columnas: el enemigo silencioso del orden de lectura

El manual alterna páginas a **una y dos columnas**. pdfplumber —elegido
inicialmente como motor único (D-08)— agrupa los caracteres por **línea base
compartida**: si la columna izquierda y la derecha tienen texto a la misma
altura, fusiona las dos en la misma línea y alterna columnas línea a línea.

Ejemplo real (p.116, tal cual lo extraía pdfplumber):

```
Válvula del solenoide de control de purga del sistema Instalación   ← izq + der fusionadas
EVAP Instale la válvula del solenoide de control del sistema de purga
EVAP en el orden inverso al de su retirada. Preste atención a
Retirada                                                            ← izq
los siguientes puntos:                                              ← der
1)Retire los siguientes componentes.                                ← izq
• Apriete la tuerca de válvula del solenoide de control del         ← der
• Montaje de la cubierta del ancho de la carrocería                 ← izq
...
```

El chunk resultante es *fiel* al texto extraído, pero el texto ya venía corrupto:
frases de dos instrucciones distintas mezcladas en la misma línea. Para un RAG
es fatal: la recuperación encuentra el fragmento, pero la respuesta mezcla pasos
de "Retirada" con pasos de "Instalación".

**Medidas:**

- **D-09 — extractor híbrido**: el texto de página se extrae con **PyMuPDF**,
  que agrupa por bloques y respeta el orden de lectura (columna izquierda
  completa, luego derecha; verificado en p.116, 121, 144, 191). pdfplumber
  queda sólo para tablas (ver §5).
- **Test de regresión de orden** (gated, `RUN_PDF_TESTS=1`): no basta validar
  *presencia* de contenido — hay que validar *orden*. El test fija la secuencia
  `1) Retire… < 2) Desconecte… < 3) Retire la válvula… < Instalación < Instale…`
  en la p.116 y que la cabecera `Instalación` quede **en su propia línea**.
- **Lección de proceso**: los tests originales de F2 pasaban con el extractor
  roto porque sólo comprobaban que el torque *estuviera* en la página, no que
  se leyera en orden. Cuando el usuario detectó el problema (imagen en mano),
  el primer paso fue **comparar motores en la misma página**: PyMuPDF daba el
  texto correcto y los bloques confirmaban la separación de columnas
  (izq x≈37–278, der x≈306–556).

## 2. Alto contenido de tablas: los datos que no pueden partirse

Las tablas concentran lo más valioso del manual: **pares de apriete**,
tolerancias, códigos de pieza, herramientas especiales. En este PDF se
detectaron **1031 tablas** en ~390 páginas (casi el 62 % del documento tiene
tablas), algunas de 27 filas (p.191, especificaciones completas del motor).

Un splitter de texto convencional las cortaría por la mitad: una tabla de
torque partida en dos chunks queda inútil (la cabecera `Pieza a apretar | Par
de apriete | N·m | kgf-m | lbf-ft` se queda en un chunk y los valores en otro).

**Medidas:**

- **D-04 — tablas en Markdown**: cada tabla se convierte a tabla Markdown
  (cabecera + separador + filas, escape de `|`, columnas rellenadas). Los
  embeddings y el LLM entienden este formato y la respuesta puede reproducirlo.
- **D-01 — tablas atómicas**: `chunk_blocks()` nunca parte una tabla, aunque
  supere `CHUNK_SIZE` (la mayor tiene ~10.832 chars ≈ 2.700 tokens, dentro del
  límite de 8192 de Titan v2). 73 tablas superan el tamaño y se conservan enteras
  por diseño.
- **Sincronía texto/tabla**: el texto de la página se extrae **sin** las celdas
  de sus tablas (§3), de modo que el chunk de tabla es la *única* fuente de ese
  dato — sin competencia ni solapes.

## 3. Duplicación: una misma tabla, dos veces en el índice

PyMuPDF (y cualquier extractor de texto) devuelve **también** el contenido de
las celdas dentro del texto de página. Sin corrección, la tabla de torque de la
p.130 aparecería íntegra como bloque `table` *y* su texto suelto como bloque
`text`: el RAG devolvería dos chunks con el mismo dato y la respuesta podría
citar la versión sin estructura.

**Medidas:**

- **Exclusión por bbox**: antes de extraer el texto de la página, se detectan
  las tablas con pdfplumber y se **filtran las palabras de PyMuPDF caídas dentro
  de esos bboxes** (centro de la palabra dentro del rectángulo).
- **Sin conversión de coordenadas**: PyMuPDF y pdfplumber comparten sistema
  (origen **arriba-izquierda**, unidades en puntos PDF) → los bboxes se usan
  tal cual. Lección costada: se implementó primero un *y-flip* innecesario
  (por asumir el origen abajo-izquierda del estándar PDF) que desplazaba los
  bboxes a la mitad inferior de la página y anulaba la exclusión — el test de
  no-duplicación de p.130 lo cazó y se corrigió midiendo coordenadas reales de
  ambas librerías lado a lado.
- **Verificación**: p.191 pasa de 3.277 a 1.339 chars de texto (el resto vive
  correctamente en su bloque de tabla); en p.130 `Pieza a apretar` no aparece
  en el bloque de texto.

## 4. Símbolos PUA: caracteres invisibles en la fuente Symbol

El manual usa una fuente Symbol con dos glifos en el rango *Private Use Area*,
que extraen como caracteres Unicode invisibles y sin significado:

- `U+F0D7` → **`N·m`** (191 usos; la unidad de torque más citada del manual)
- `U+F046` → **`→ (Página 1C-2)`** (1.837 usos; referencias cruzadas)

Sin normalizar, las respuestas del RAG mostrarían un carácter corrupto justo en
el dato más importante (`6.7 N□m`) y las referencias cruzadas se perderían.

**Medida:** normalización en la extracción (`str.maketrans` + `chr(0xF0D7)`,
**nunca** el literal: al teclearlos es indistinguible — se escribió U+F057 por
U+F0D7 dos veces y el error es invisible en el fuente). Verificado: 0 PUA
restantes en las 626 páginas.

## 5. Motor de detección de tablas: PyMuPDF vs pdfplumber

`find_tables` de PyMuPDF 2.0 (modelo de layout, sin caché) cuesta **5–8 s por
página** (≈1 hora para el manual) y sobre este PDF detectó **0 tablas**.
pdfplumber: **0,05–0,2 s/página** y detecciones en 402/626 páginas.

**Medida (D-08):** motor de tablas = pdfplumber. Con la revisión D-09 el
reparto quedó definitivo: **pdfplumber para tablas, PyMuPDF para texto**, cada
uno con lo que hace bien. La ingesta completa (626 páginas) bajó de 369 s a
**288 s** de extracción.

## 6. Ingesta idempotente: IDs que no colisionan

Chroma exige IDs únicos. El ID de chunk es `sha256(fuente|página|tipo|índice|contenido)[:32]`,
determinista para que re-ingerir no duplique. Pero aparecieron **bloques
hermanos idénticos** (fragmentos de tabla repetidos en la misma página) que
producían el mismo hash → colisión rechazada por Chroma.

**Medida:** el hash incluye el **ordinal del bloque** dentro de su grupo
(página, tipo), calculado en orden de extracción → dos bloques idénticos en la
misma página reciben IDs distintos y estables. Regresión cubierta por test;
verificado en el documento completo: **2021 chunks, 0 duplicados**.

## 7. Límites de embeddings y metadata para Chroma

- **Tokens**: la tabla más larga (~10.832 chars ≈ 2.700 tokens) cabe en el
  límite de 8192 tokens de `amazon.titan-embed-text-v2:0`. Se midió tras el
  chunking, no a ojo.
- **Metadata sin `None`**: Chroma rechaza valores nulos → el chunker garantiza
  `page`, `source`, `kind`, `chunk_index` presentes (y `section` sólo si existe).
- **Citas**: cada chunk conserva `page` + `kind` para que la respuesta pueda
  citar "página 130, tabla de par de apriete" (RF-06).

## Estado y vigilancia

- Suite: **25 passed, 1 skipped** (tests gated con el PDF real: torque p.116,
  orden de columnas p.116, tabla p.130 sin duplicación).
- **Vigilancia abierta**: muchas "tablas" detectadas son fragmentos pequeños
  (mediana ~75 chars: la mediana de las tablas de texto es ~910). El usuario
  decidió **no filtrar** (se conservan todas las detecciones); si en la Fase 5
  (evaluación de retrieval) la calidad lo exige, abrir filtro ≥2×2 filas/columnas.
- Regla de oro para nuevos PDFs: **validar el orden de lectura**, no sólo la
  presencia de contenido; y medir coordenadas de las librerías antes de mezclar
  sus outputs.
