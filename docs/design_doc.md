# 📋 Documento de Diseño Técnico: Agente de Detección de Incidencias
## AI Engineer Test - Agent Factory

---

## 1. Entendimiento del Problema (¿Qué estamos resolviendo?)

### 1.1 La situación actual (El "dolor")

Imagina que trabajas en una empresa que procesa pagos digitales. Cada día llegan **cientos de archivos** de diferentes proveedores: transacciones, liquidaciones, devoluciones, reportes regulatorios. Estos archivos llegan a **18 fuentes de datos diferentes** (piensa en ellas como 18 buzones, cada uno con sus propias reglas).

Hoy, un equipo de personas revisa **manualmente** estos 18 buzones cada mañana durante **3-4 horas** buscando problemas como:

- "¿Llegó el archivo que esperábamos?" (Missing files)
- "¿Llegó duplicado?" (Duplicated files)
- "¿Por qué está vacío si normalmente tiene datos?" (Empty files)
- "¿Por qué tiene 100 registros si normalmente tiene 100,000?" (Volume anomalies)
- "¿Por qué llegó a las 3am si siempre llega a las 8am?" (Late uploads)
- "¿Este archivo es de ayer o de hace una semana?" (Previous period files)

### 1.2 Lo que queremos construir (La solución)

Un **agente de IA** que haga este trabajo automáticamente y genere un **reporte diario** que diga:

> 🔴 "¡URGENTE! En la fuente X faltan 14 archivos. Necesitan acción inmediata."
> 🟡 "En la fuente Y el volumen es 30% mayor de lo normal. Investigar."
> 🟢 "Las fuentes Z, W, V están perfectas."

### 1.3 El valor de negocio

| Impacto | Sin agente | Con agente |
|---------|-----------|------------|
| **Tiempo** | 3-4 horas/día manuales | ~2 minutos automatizados |
| **Financiero** | Multas $10K-$50K USD por errores | Detección temprana |
| **Operacional** | 20+ horas/semana | Equipo enfocado en resolver, no en buscar |
| **Reputacional** | Errores llegan a stakeholders | Reportes proactivos |

---

## 2. Los Datos (¿Con qué contamos?)

### 2.1 Las Hojas de Vida (CVs) — "El manual de cada buzón"

Cada una de las 18 fuentes tiene un archivo markdown que describe su **comportamiento normal**. Esto es fundamental porque cada fuente es diferente:

| Fuente | Archivos/día | Horario esperado (UTC) | ¿Fines de semana? | % Vacíos normales |
|--------|-------------|----------------------|-------------------|-------------------|
| 195385 - Settlement_Layout_2 | 32-45 (Mar-Sáb) | 08:00-08:13 | Sáb sí, Dom no | 0% |
| 195436 - MyPal_DBR RX | 1 | 14:00-15:00 | Sí, ambos | 30% (Lun/Mar) |
| 195439 - MyPal_Activity report | 1 | 02:00 | Sí, ambos | 0% |
| 196125 - Settlement_Layout_1 | 41-53 (Mar-Sáb) | 08:00-08:12 | Sáb sí, Dom no | 2.6% |
| 199944 - Soop Transaction PIX 3 | 2 (PIX+BANKING) | 11:01-11:33 | Sí, ambos | 5.4% |
| 207936 - Soop Tipo 2 | 3 (SHOP/PAGO/POS) | 11:01-11:44 | Sí, ambos | 33% (POS) |
| 207938 - Soop Tipo 3 | 3 (similar a Tipo2) | 10:45-12:30 | Lun-Sáb, Dom no | 31.9% (POS) |
| 209773 - Desco PIX | 1 | 15:10-15:25 | Sí, ambos | 7% |
| 211544 - Desco Devoluções | 1 | 15:00-16:30 | Sí, ambos | 0% |
| 220504 - Payments_Layout_1_V3 | 16-19 | 08:08-08:18 | Sí, ambos | 24.8% (normal para ciertas entidades) |
| 220505 - Payments_Layout_2_V3 | 2 (Debito+MVP) | 08:02-08:11 | Sí, ambos | 3.7% (filtered jobs) |
| 220506 - Payments_Layout_3_V3 | 1 (_BR_3DS) | 08:03-08:19 | Sí, ambos | 0% |
| 224602 - Itm Pagamentos | 1 | 14:00-15:00 | Sí, ambos | 0% (post-backfill) |
| 224603 - Itm Devolução | 1 | 12:15 (actual) | Sí, ambos | 0% (post-ene2025) |
| 228036 - WuPay_Sale payments_2 | 2 (Lun-Vie) | 20:10-20:25 | Sáb esporádico, Dom no | 6.5% |
| 228038 - WuPay_STL payments_2 | 2 (Lun-Vie) | 20:05-20:35 | Sáb esporádico, Dom no | 46.5% (alto pero normal) |
| 239611 - WuPay_Sale_adjustments_3 | 2 (Lun-Vie) | 20:12-20:23 | Sáb esporádico, Dom no | 9% |
| 239613 - WuPay_STL adjustments_3 | 2 (Lun-Vie) | 20:05-20:23 | Sáb esporádico, Dom no | 9.9% |

**Punto clave**: No puedes aplicar las mismas reglas a todas las fuentes. Un archivo vacío en `MyPal_DBR RX` un lunes es **normal** (80%+ son vacíos). El mismo archivo vacío en `Desco Devoluções` sería una **incidencia grave** (0% histórico de vacíos).

### 2.2 Los Datos Diarios — "Lo que llegó hoy"

Para cada día (2025-09-08 al 2025-09-12) tenemos:

- **`files.json`**: Los últimos 200 archivos de cada fuente (incluye archivos de hoy y recientes). Cada archivo tiene:
  - `filename`: Nombre del archivo
  - `rows`: Cantidad de registros
  - `status`: processed / empty / failure / stopped / deleted
  - `is_duplicated`: true/false
  - `uploaded_at`: Timestamp de carga
  - `file_size`: Tamaño en MB

- **`files_last_weekday.json`**: Archivos del mismo día de la semana anterior (para comparación directa). Por ejemplo, si hoy es martes, contiene los archivos del martes pasado.

### 2.3 El Feedback — "Qué opinó el cliente de reportes anteriores"

Un archivo Excel con 3 días de feedback (sept 8, 9, 10) que contiene:
- El reporte generado por una versión alpha
- Comentarios del stakeholder sobre qué mejorar
- Métricas de accuracy (ej: 90%)

**Hallazgos clave del feedback:**
1. ✅ Ser más directo: "Faltan 3 archivos de X, Y, Z" en vez de texto técnico largo
2. ✅ Eliminar jerga: No decir "re-trigger ingestion" ni "check landing location"
3. ✅ Combinar resumen + detalle: "Solo 4/18 archivos recibidos" + lista de faltantes
4. ✅ Las acciones recomendadas deben ser entendibles por el cliente
5. ✅ La sección amarilla debe explicar claramente el problema

---

## 3. Arquitectura del Agente (¿Cómo lo construimos?)

### 3.1 ¿Por qué Google ADK?

**ADK (Agent Development Kit)** es el framework de Google para construir agentes de IA. Lo elegimos porque:

1. **Orquestación multi-agente nativa**: Podemos crear sub-agentes especializados (uno por cada tipo de incidencia) y un agente principal que los coordina
2. **Integración con Gemini**: Usa modelos de Google (Gemini) como LLM base
3. **Tools nativas**: Permite definir funciones Python como herramientas que el agente puede invocar
4. **Callbacks y sesiones**: Control granular del flujo de ejecución
5. **Ecosistema GCP**: Se integra naturalmente con Vertex AI, Cloud Storage, BigQuery, etc.

### 3.2 Diagrama de Arquitectura (Vista General)

```
┌─────────────────────────────────────────────────────────────────┐
│                    ORQUESTADOR PRINCIPAL                        │
│                 (IncidentDetectionAgent)                        │
│              Modelo: gemini-2.0-flash                           │
│                                                                 │
│  Responsabilidad: Coordinar sub-agentes, consolidar reporte    │
│                                                                 │
│  ┌──────────────┐    ┌──────────────────────────────────────┐  │
│  │  PREPARADOR   │───▶│         SUB-AGENTES DETECTORES       │  │
│  │  DE INPUTS    │    │                                      │  │
│  │              │    │  ┌────────┐ ┌────────┐ ┌────────┐   │  │
│  │ • parse_cv() │    │  │Missing │ │Duplicat│ │ Empty  │   │  │
│  │ • parse_     │    │  │ File   │ │& Failed│ │ File   │   │  │
│  │   files()    │    │  │Detector│ │Detector│ │Detector│   │  │
│  │ • filter_    │    │  └────────┘ └────────┘ └────────┘   │  │
│  │   today()    │    │  ┌────────┐ ┌────────┐ ┌────────┐   │  │
│  └──────────────┘    │  │Volume  │ │Late    │ │Previous│   │  │
│                      │  │Variati.│ │Upload  │ │Period  │   │  │
│                      │  │Detector│ │Detector│ │Detector│   │  │
│                      │  └────────┘ └────────┘ └────────┘   │  │
│                      └──────────────────────────────────────┘  │
│                                     │                          │
│                                     ▼                          │
│                      ┌──────────────────────────────────────┐  │
│                      │      CONSOLIDADOR DE REPORTE          │  │
│                      │                                      │  │
│                      │  • Agrupa incidencias por fuente     │  │
│                      │  • Clasifica severidad (🔴🟡🟢)       │  │
│                      │  • Genera recomendaciones claras     │  │
│                      │  • Formato ejecutivo para negocio    │  │
│                      └──────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────┘
```

### 3.3 Componentes en Detalle

#### A) Preparador de Inputs (Tools/Functions — No es un agente LLM)

Este componente **NO usa LLM**. Son funciones Python puras que procesan datos:

```
¿Por qué no usar LLM aquí?
→ Parsear JSON y markdown es determinístico
→ No necesitas "inteligencia" para filtrar archivos por fecha
→ Es más rápido, barato y predecible
→ En ADK, estas se definen como "Tools" (FunctionTool)
```

**Funciones principales:**

| Función | Input | Output | Descripción |
|---------|-------|--------|-------------|
| `parse_cv(source_id)` | Archivo .md del CV | Objeto estructurado con patrones | Extrae horarios, volúmenes esperados, % vacíos normales por día |
| `load_today_files(source_id, date)` | files.json + fecha | Lista de archivos de hoy | Filtra files.json por `uploaded_at` del día de ejecución |
| `load_last_weekday_files(source_id)` | files_last_weekday.json | Lista de archivos | Carga archivos del mismo día semana anterior |
| `get_cv_summary(source_id)` | CV parseado | Texto resumido | Resume el CV en formato que el LLM pueda consumir eficientemente |

#### B) Detectores de Incidencias (Sub-Agentes ADK)

Cada detector es un **sub-agente** con su propia instrucción (prompt) especializada. Esto es clave en ADK porque permite:

- **Separación de responsabilidades**: Cada detector tiene un prompt enfocado
- **Reutilización**: Puedes mejorar un detector sin tocar los demás
- **Testeo independiente**: Puedes evaluar cada detector por separado

**Detector 1: Missing File Detector**
```
Propósito: ¿Llegó todo lo que debía llegar?

Lógica:
1. Del CV → obtener cuántos archivos se esperan para este día de la semana
2. De files.json → contar cuántos archivos llegaron hoy
3. De files_last_weekday.json → cuántos llegaron el mismo día la semana pasada
4. Si llegaron menos de lo esperado → INCIDENCIA

Ejemplo:
  CV dice: "Martes = 40 archivos (±11)"
  Hoy (martes) llegaron: 30 archivos
  Martes pasado: 39 archivos
  → INCIDENCIA: Faltan ~10 archivos vs. lo esperado

Severidad: URGENTE si faltan archivos críticos
```

**Detector 2: Duplicated & Failed File Detector**
```
Propósito: ¿Hay archivos duplicados o con errores?

Lógica:
1. Filtrar archivos de hoy donde is_duplicated == TRUE
2. Filtrar archivos de hoy donde status == "stopped" o "failure"
3. Verificar si hay nombres de archivo repetidos
4. Reportar cada caso encontrado

Severidad: URGENTE si duplicados + stopped/failure
```

**Detector 3: Unexpected Empty File Detector**
```
Propósito: ¿Hay archivos vacíos que no deberían estarlo?

Lógica:
1. Filtrar archivos de hoy con rows == 0
2. Del CV → verificar si ESA fuente normalmente tiene vacíos ese día
3. Si el CV dice "Lunes: 80% vacíos" y hoy es lunes → NO es incidencia
4. Si el CV dice "0% vacíos" y hay un vacío → SÍ es incidencia

Caso especial: Fuentes como 207936 (Soop Tipo 2) tienen POS siempre vacío = NORMAL
Caso especial: 220504 tiene Innovation/POC/safemode siempre vacíos = NORMAL

Severidad: REQUIERE ATENCIÓN (a menos que sea patrón conocido)
```

**Detector 4: Unexpected Volume Variation Detector**
```
Propósito: ¿El volumen de registros es anormal?

Lógica:
1. Del CV → obtener mean, median, stdev de rows para este día de la semana
2. De files.json → obtener rows de los archivos de hoy
3. Calcular si está fuera del rango esperado (mean ± 2*stdev o intervalo 95%)
4. Comparar también con files_last_weekday

Ejemplo:
  CV dice: "Miércoles mean=131,025, stdev=~50,000"
  Hoy (miércoles): 5,000 registros
  → INCIDENCIA: Volumen 96% menor al esperado

IMPORTANTE: Comparar por día de la semana, no globalmente.
Verificar si fines de semana aplica distinto comportamiento.

Severidad: URGENTE si la desviación es extrema (>3 stdev)
           REQUIERE ATENCIÓN si moderada (>2 stdev)
```

**Detector 5: File Upload After Schedule Detector**
```
Propósito: ¿Llegaron archivos muy tarde?

Lógica:
1. Del CV → obtener ventana de upload esperada para este día
2. De files.json → obtener uploaded_at de archivos de hoy
3. Si uploaded_at > ventana_esperada + 4 horas → INCIDENCIA

Ejemplo:
  CV dice: "Upload esperado: 08:00-08:18 UTC"
  Archivo llegó: 14:30 UTC (+6 horas)
  → INCIDENCIA: Archivo 6 horas tarde

REGLA: Este incidente es SIEMPRE tipo "advertencia" (🟡)
       NUNCA debe ser clasificado como urgente (🔴)

Severidad: REQUIERE ATENCIÓN (máximo)
```

**Detector 6: Upload of Previous File Detector**
```
Propósito: ¿Llegaron archivos de periodos anteriores?

Lógica:
1. Del CV → obtener el ECD (Expected Coverage Data) — qué fechas cubre normalmente
2. De files.json → verificar si el archivo tiene fecha de nombre fuera del ECD
3. Estos suelen ser subidas manuales/históricas

Ejemplo:
  Hoy es 2025-09-10
  Llega archivo con fecha 2025-09-05 en el nombre
  Lag habitual del CV = 1 día
  → INCIDENCIA: Archivo de periodo anterior (probablemente backfill manual)

REGLA: NUNCA clasificar como error crítico
       Es informativo, indica subida manual/histórica

Severidad: REQUIERE ATENCIÓN (máximo)
```

#### C) Consolidador de Reporte (Agente LLM)

Este sí usa el LLM porque necesita **sintetizar**, **priorizar** y **redactar** en lenguaje de negocio:

```
Input: Resultados de los 6 detectores para las 18 fuentes
Output: Reporte ejecutivo con:

🔴 URGENTE - Acción Inmediata Requerida
   Criterio: >1 archivo con incidente urgente O >3 incidentes requiere atención
   
🟡 REQUIERE ATENCIÓN - Necesita Investigación  
   Criterio: Al menos 1 incidente que requiera atención

🟢 TODO BIEN - Sin Problemas
   Criterio: No hay incidentes

+ Recomendaciones claras en lenguaje de negocio (sin jerga técnica)
```

### 3.4 Patrón ADK: ¿Cómo se conectan los componentes?

En Google ADK, la estructura se implementa así:

```
Orquestador (Agent principal)
├── Tools (FunctionTool):
│   ├── parse_cv()
│   ├── load_today_files()
│   ├── load_last_weekday_files()
│   └── get_source_list()
│
├── Sub-Agents (cada uno es un Agent ADK):
│   ├── MissingFileDetector (Agent con instrucciones especializadas + tools)
│   ├── DuplicatedFailedDetector (Agent con instrucciones especializadas + tools)
│   ├── EmptyFileDetector (Agent con instrucciones especializadas + tools)
│   ├── VolumeVariationDetector (Agent con instrucciones especializadas + tools)
│   ├── LateUploadDetector (Agent con instrucciones especializadas + tools)
│   └── PreviousPeriodDetector (Agent con instrucciones especializadas + tools)
│
└── Sub-Agent:
    └── ReportConsolidator (Agent que genera el reporte final)
```

**Flujo de ejecución simplificado:**

```
1. Usuario ejecuta el agente con la fecha del día
   │
2. Orquestador invoca Tools para preparar datos
   │  → parse_cv() para cada fuente
   │  → load_today_files() para cada fuente  
   │  → load_last_weekday_files() para cada fuente
   │
3. Orquestador delega a cada Sub-Agente Detector
   │  → Cada detector recibe: CV parseado + archivos de hoy + archivos semana pasada
   │  → Cada detector devuelve: lista de incidencias encontradas (o vacía)
   │
4. Orquestador recopila todos los resultados
   │
5. Orquestador delega al ReportConsolidator
   │  → Recibe: todas las incidencias de todos los detectores
   │  → Genera: reporte ejecutivo con severidad y recomendaciones
   │
6. Reporte final entregado
```

---

## 4. Estrategia de Evaluación (¿Cómo sabemos que funciona bien?)

### 4.1 ¿Por qué es importante evaluar?

No basta con que el agente "funcione". Necesitamos **medir qué tan bien funciona** y **mejorar iterativamente**. Esto es lo que diferencia a un prototipo de un sistema de producción.

### 4.2 Ground Truth: El Feedback como Referencia

El feedback del stakeholder nos da **3 días de "respuesta correcta"** (sept 8, 9, 10). De ahí extraemos:

| Fecha | Incidencias reales reportadas | Accuracy del alpha |
|-------|------------------------------|-------------------|
| Sept 8 | 3 urgentes (220504, 220505, 220506 missing files) + 4 atención | No reportada |
| Sept 9 | 4 urgentes (196125, 207936, 207938, 199944) + 6 atención | No reportada |
| Sept 10 | 5 urgentes (220504, 220505, 220506, 196125, 195385) | 90% |

### 4.3 Métricas de Evaluación

```
┌─────────────────────────────────────────────────────────────┐
│                    MÉTRICAS DEL AGENTE                       │
│                                                             │
│  1. DETECCIÓN (¿Encuentra los problemas?)                   │
│     ├── Precision: De lo que reportó, ¿cuánto era real?     │
│     ├── Recall: De lo real, ¿cuánto detectó?                │
│     └── F1-Score: Balance entre ambos                       │
│                                                             │
│  2. CLASIFICACIÓN (¿Los clasifica bien?)                    │
│     ├── Accuracy de severidad: 🔴🟡🟢 correctos            │
│     └── Confusion matrix: ¿Confunde urgente con atención?   │
│                                                             │
│  3. CALIDAD DEL REPORTE (¿Es útil para el negocio?)        │
│     ├── Claridad: ¿Lenguaje entendible? (eval LLM-as-judge)│
│     ├── Accionabilidad: ¿Las recomendaciones son útiles?    │
│     └── Completitud: ¿Incluye toda la info necesaria?       │
│                                                             │
│  4. RENDIMIENTO                                             │
│     ├── Tiempo de ejecución                                 │
│     ├── Tokens consumidos                                   │
│     └── Costo por ejecución                                 │
└─────────────────────────────────────────────────────────────┘
```

### 4.4 Pipeline de Evaluación

```
Para cada día de prueba (sept 8-12):
│
├── 1. Ejecutar agente → obtener reporte generado
│
├── 2. Comparar vs. ground truth (feedback)
│   ├── ¿Detectó las mismas incidencias? (Precision/Recall)
│   ├── ¿Asignó la misma severidad? (Accuracy clasificación)
│   └── ¿Las recomendaciones son mejores que el alpha? (LLM-as-judge)
│
├── 3. Calcular métricas agregadas
│   ├── Precision promedio
│   ├── Recall promedio
│   ├── F1-Score
│   └── Accuracy de severidad
│
└── 4. Registrar resultados para comparar entre versiones
```

### 4.5 Evaluación con LLM-as-Judge (Técnica avanzada)

Para evaluar la **calidad del texto** del reporte (no solo si detectó bien), usamos otro LLM como juez:

```
Prompt al LLM evaluador:
"Dado este feedback del stakeholder: [feedback]
Y este reporte generado por el agente: [reporte]

Evalúa del 1-10:
1. ¿El lenguaje es claro y sin jerga técnica?
2. ¿Las recomendaciones son accionables para un no-técnico?
3. ¿El resumen es directo y conciso?
4. ¿Identificó correctamente los problemas del feedback?"
```

---

## 5. Estrategia de Versionamiento Evolutivo

### 5.1 El concepto: Build → Evaluate → Improve → Repeat

```
  ┌──────────┐     ┌──────────┐     ┌──────────┐
  │  v1.0    │────▶│ EVALUAR  │────▶│  v2.0    │────▶ ...
  │ Baseline │     │ métricas │     │ Mejorado │
  └──────────┘     │ feedback │     └──────────┘
                   └──────────┘
```

### 5.2 Plan de Versiones

#### v1.0 — Baseline (Reglas + LLM básico)
```
Qué hace:
- Detectores basados principalmente en reglas determinísticas
- LLM solo para consolidar y redactar el reporte
- Prompts simples y directos

Qué evaluamos:
- ¿Detecta las incidencias del feedback? (Recall)
- ¿Genera falsos positivos? (Precision)
- ¿El reporte es entendible?

Resultado esperado: Funcional pero con margen de mejora en el lenguaje
```

#### v2.0 — Incorporación del Feedback
```
Cambios basados en evaluación de v1.0:
- Mejorar prompts del consolidador con ejemplos del feedback
  ("Decir 'Faltan 14/18 archivos' en vez de listar técnicamente")
- Ajustar umbrales de los detectores si v1 tuvo falsos positivos/negativos
- Agregar few-shot examples al prompt del consolidador usando reportes
  que el stakeholder aprobó

Qué evaluamos:
- ¿Mejoró el F1-Score vs v1?
- ¿El lenguaje es más claro? (LLM-as-judge)
- ¿Se eliminaron los problemas del feedback?
```

#### v3.0 — Optimización de Arquitectura (Hybrid Approach)
```
Cambios basados en limitaciones reales de v1/v2:
- PROBLEMA: v1/v2 hacen ~20+ llamadas LLM → rate limit en Gemini free tier (15 req/min)
- INSIGHT: La detección es DETERMINÍSTICA (contar archivos, comparar volúmenes = math, no lenguaje)
- SOLUCIÓN: Python puro para detección (6 detectores, 0 LLM calls) + 1 LLM call para reporte
- RESULTADO: De 20+ calls a 1-2 calls. Funciona en free tier. Más rápido y barato.

ADK Components en v3:
- Agent: Consolidador de reporte (hereda prompts mejorados de v2)
- FunctionTool: Envuelve el pipeline de detección Python
- Runner + InMemorySessionService: Ejecución del agente

Qué evaluamos:
- ¿Misma calidad de detección que v1/v2? (precision/recall)
- ¿Mejor rendimiento? (tiempo, costo, tasa de éxito)
- ¿El reporte mantiene calidad de lenguaje de v2?
```

#### Futuras mejoras
```
Posibles mejoras:
- Ajuste fino de umbrales por fuente
- Detección de patrones estacionales (ej: feriados de Curitiba)
- Integración con MCP para enviar reportes a Slack/Email
- Uso de Vertex AI para analytics avanzados
```

### 5.3 Cómo se evidencia el versionamiento (Git)

```
repo/
├── agents/
│   ├── v1/                          ← Multi-agente baseline
│   │   ├── agent.py                 ← Orquestador + 6 sub-agentes + consolidador
│   │   ├── detectors/
│   │   ├── prompts/                 ← Prompts básicos
│   │   └── tools/                   ← data_tools.py (compartido)
│   ├── v2/                          ← Multi-agente con prompts mejorados
│   │   ├── agent.py                 ← Misma arquitectura
│   │   ├── detectors/
│   │   └── prompts/                 ← Prompts mejorados con feedback
│   └── v3/                          ← Híbrida (optimización de arquitectura)
│       ├── agent.py                 ← 1 agente ADK (solo reporte)
│       ├── detectors/
│       │   └── rule_based.py        ← 6 detectores Python puros
│       └── prompts/                 ← Prompt consolidador hereda de v2
│
├── evaluation/
│   ├── eval_pipeline.py             ← Script de evaluación
│   ├── ground_truth/                ← Feedback parseado como verdad
│   ├── results/
│   │   ├── v1_results.json          ← Métricas v1
│   │   └── v2_results.json          ← Métricas v2 (se comparan)
│   └── comparison_report.md         ← "v2 mejoró recall de 85% a 95%"
│
├── data/
│   ├── datasource_cvs/              ← Los 18 CVs
│   ├── 2025-09-08_20_00_UTC/        ← Datos por día
│   ├── ...
│   └── feedback/
│
├── docs/
│   ├── architecture.md              ← Este documento
│   └── design_decisions.md
│
└── README.md
```

---

## 6. Integración con Ecosistema GCP

### 6.1 Componentes GCP relevantes

| Componente GCP | Uso en el proyecto | Por qué |
|---------------|-------------------|---------|
| **Vertex AI** | Hosting del modelo Gemini | Endpoint gestionado, escalable |
| **Cloud Storage (GCS)** | Almacenar CVs, archivos JSON, reportes | Fuente de datos centralizada |
| **BigQuery** | Analytics de métricas de evaluación | Consultas SQL sobre resultados históricos |
| **Cloud Functions** | Trigger diario del agente | Ejecución serverless programada |
| **Cloud Scheduler** | Cron job diario | Dispara la ejecución a la hora correcta |
| **Secret Manager** | API keys, credenciales | Seguridad de secrets |
| **Artifact Registry** | Contenedor del agente | Despliegue versionado |

### 6.2 Flujo de producción (visión futura)

```
Cloud Scheduler (6:00 AM UTC)
  │
  ▼
Cloud Function (trigger)
  │
  ▼
Agente ADK (Vertex AI)
  ├── Lee CVs de GCS
  ├── Lee files.json de GCS
  ├── Ejecuta detectores
  ├── Genera reporte
  │
  ▼
Reporte → GCS + Slack/Email (vía MCP Tool)
Métricas → BigQuery (para dashboard de evaluación)
```

---

## 7. Criterios Opcionales (Bonus)

### 7.1 MCP Tool para mensajería

Implementar un **MCP (Model Context Protocol) Server** custom o usar uno existente para enviar el reporte a Slack o Email:

```
Opción A: MCP Server custom para Slack webhook
Opción B: MCP Server para SendGrid (email)
Opción C: Usar un MCP existente de la comunidad
```

### 7.2 Técnicas avanzadas

- **Few-shot prompting**: Incluir ejemplos de reportes buenos/malos en los prompts
- **Chain-of-Thought**: Hacer que los detectores "razonen" paso a paso
- **LLM-as-Judge**: Para evaluación automática de calidad del reporte
- **Structured Output**: Forzar JSON schema en las respuestas de los detectores

### 7.3 Patrones y buenas prácticas

- **Separation of Concerns**: Cada detector es independiente
- **Dependency Injection**: Los datos se inyectan como tools, no hardcodeados
- **Idempotencia**: Ejecutar el agente 2 veces con los mismos datos da el mismo resultado
- **Logging estructurado**: Cada decisión del agente se registra para debugging
- **Error handling**: Si un detector falla, los demás siguen funcionando

---
