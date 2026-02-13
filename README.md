# Agente de Detección de Incidencias — AI Engineer Test

Sistema multi-agente con Google ADK (Agent Development Kit) + Gemini 2.0 Flash para la detección automática de incidencias en archivos de procesamiento de pagos.

Analiza **18 fuentes de datos** diariamente buscando 6 tipos de incidencias, genera un **reporte ejecutivo** clasificado por severidad, y demuestra **versionamiento evolutivo** (v1 → v2 → v3).

---

## Arquitectura y Versiones

El proyecto demuestra 3 tipos de mejora iterativa:

| Versión | Tipo de Mejora | Arquitectura | LLM Calls | Tier Requerido |
|---------|---------------|-------------|-----------|----------------|
| **v1** | Baseline | Multi-agente (8 agentes LLM) | ~20+ | Plan pago Gemini |
| **v2** | Prompt improvement (feedback-driven) | Multi-agente (misma arch, mejores prompts) | ~20+ | Plan pago Gemini |
| **v3** | Architecture optimization (cost-driven) | Híbrida (Python + 1 LLM) | 1-2 | **Free tier** ✅ |

**v1 → v2**: Mejora de prompts basada en evaluación del feedback de stakeholders.
**v2 → v3**: Mejora de arquitectura basada en limitaciones reales (rate limits, costo, latencia).

---

## Requisitos Previos

- **Python 3.10+**
- **Cuenta Google AI Studio** con API Key ([obtener aquí](https://aistudio.google.com/apikey))
- **Git** (para clonar el repositorio)

---

## Instalación

> **Nota sobre terminales:** Los comandos de esta guía funcionan en:
> - **Windows**: PowerShell, Command Prompt (cmd), o Windows Terminal
> - **macOS**: Terminal (zsh/bash)
> - **Linux**: Terminal (bash/zsh)
>
> Las diferencias entre sistemas se señalan donde aplique.

### Paso 1: Clonar el repositorio

```bash
git clone <url-del-repositorio>
cd agent-factory-project
```

### Paso 2: Crear entorno virtual

**Windows (PowerShell):**
```powershell
python -m venv venv
.\venv\Scripts\Activate.ps1
```

**Windows (Command Prompt / cmd):**
```cmd
python -m venv venv
venv\Scripts\activate.bat
```

**macOS / Linux (Terminal):**
```bash
python3 -m venv venv
source venv/bin/activate
```

### Paso 3: Instalar dependencias

```bash
pip install -r requirements.txt
```

### Paso 4: Configurar API Key

Crear un archivo `.env` en la raíz del proyecto:

**Windows (PowerShell):**
```powershell
echo "GOOGLE_API_KEY=tu_api_key_aqui" > .env
```

**Windows (Command Prompt / cmd):**
```cmd
echo GOOGLE_API_KEY=tu_api_key_aqui > .env
```

**macOS / Linux:**
```bash
echo "GOOGLE_API_KEY=tu_api_key_aqui" > .env
```

> Reemplaza `tu_api_key_aqui` con tu API Key de [Google AI Studio](https://aistudio.google.com/apikey).

---

## Ejecución

### Ejecutar v3 (recomendado — funciona en free tier)

```bash
python main.py --date 2025-09-08 --version v3
```

### Ejecutar para todas las fechas disponibles

```bash
python main.py --all --version v3
```

### Ejecutar v1 o v2 (requiere plan pago de Gemini)

```bash
python main.py --date 2025-09-08 --version v1
python main.py --date 2025-09-08 --version v2
```

### Fechas disponibles

| Fecha | Día |
|-------|-----|
| 2025-09-08 | Lunes |
| 2025-09-09 | Martes |
| 2025-09-10 | Miércoles |
| 2025-09-11 | Jueves |
| 2025-09-12 | Viernes |

### Salida

Los reportes se guardan automáticamente en:
```
outputs/
├── v1/
│   └── report_2025-09-08.md
├── v2/
│   └── report_2025-09-08.md
└── v3/
    └── report_2025-09-08.md
```

---

## Evaluación

El pipeline de evaluación compara los reportes generados contra el feedback de stakeholders (ground truth).

```bash
# Evaluar una versión específica
python evaluation/eval_pipeline.py --version v3

# Comparar dos versiones
python evaluation/eval_pipeline.py --compare v1 v3
python evaluation/eval_pipeline.py --compare v2 v3
```

**Métricas calculadas:**
- **Precision**: De lo que el agente reportó, ¿cuánto era real?
- **Recall**: De las incidencias reales, ¿cuántas detectó?
- **F1-Score**: Balance entre precision y recall
- **Severity Accuracy**: ¿Clasificó bien la severidad?

---

## Estructura del Proyecto

```
agent-factory-project/
├── agents/                          # Versiones del agente
│   ├── v1/                          # Multi-agente baseline
│   │   ├── agent.py                 # 8 agentes ADK (orquestador + 6 detectores + consolidador)
│   │   ├── prompts/templates.py     # Prompts básicos
│   │   └── tools/data_tools.py      # Funciones de acceso a datos (compartido)
│   ├── v2/                          # Multi-agente con prompts mejorados
│   │   ├── agent.py                 # Misma arquitectura que v1
│   │   └── prompts/templates.py     # Prompts mejorados con feedback de stakeholders
│   └── v3/                          # Híbrida (arquitectura optimizada)
│       ├── agent.py                 # 1 agente ADK (solo reporte LLM)
│       ├── detectors/rule_based.py  # 6 detectores Python determinísticos
│       └── prompts/templates.py     # Hereda mejoras de v2
│
├── data/                            # Datos de entrada
│   ├── datasource_cvs/              # 18 hojas de vida de fuentes (markdown)
│   ├── daily_files/                 # 5 carpetas diarias con files.json
│   └── feedback/                    # Feedback de stakeholders (Excel)
│
├── evaluation/                      # Pipeline de evaluación
│   ├── eval_pipeline.py             # Script principal de evaluación
│   ├── ground_truth/                # Feedback parseado como verdad
│   └── results/                     # Resultados por versión (JSON)
│
├── docs/                            # Documentación
│   ├── design_doc.md                # Documento de diseño técnico completo
│   └── challenges_and_lessons.md    # Decisiones de diseño y lecciones
│
├── mcp_tools/                       # MCP Server para Slack (bonus)
│   ├── slack_server.py              # Servidor MCP
│   └── integration_example.py       # Ejemplo de integración
│
├── tests/                           # Tests unitarios
│   └── test_data_tools.py           # Tests de las herramientas de datos
│
├── main.py                          # Punto de entrada principal
├── requirements.txt                 # Dependencias Python
├── pytest.ini                       # Configuración de tests
└── .env                             # API Key (crear manualmente, no commitear)
```

---

## Detalle de Cada Versión

### v1 — Baseline Multi-Agente

```
Orquestador (gemini-2.0-flash)
├── Tools: parse_cv(), load_today_files(), load_last_weekday_files()
├── Sub-agents (6 detectores, cada uno con LLM):
│   ├── MissingFileDetector
│   ├── DuplicatedFailedDetector
│   ├── EmptyFileDetector
│   ├── VolumeVariationDetector
│   ├── LateUploadDetector
│   └── PreviousPeriodDetector
└── ReportConsolidator (LLM)
```

**Resultado:** Arquitectura correcta, demuestra ADK multi-agente. Requiere ~20+ LLM calls.

### v2 — Prompts Mejorados (Feedback-Driven)

Misma arquitectura que v1, pero con prompts mejorados basados en feedback real:

- Eliminada jerga técnica ("re-trigger ingestion" → "Contact the provider")
- Agregados ejemplos few-shot de incidencias reales
- Líneas de resumen obligatorias ("Only 4/18 files received")
- Detección a nivel de entidad mejorada

### v3 — Arquitectura Híbrida (Optimizada)

```
Pipeline Python (0 LLM calls)           Agente ADK (1 LLM call)
┌─────────────────────────┐              ┌────────────────────┐
│ 6 Detectores Python     │──findings──→ │ Report Consolidator│
│ • missing_file          │              │ (gemini-2.0-flash) │
│ • duplicated_failed     │              │                    │
│ • unexpected_empty      │              │ Hereda prompts v2  │
│ • volume_variation      │              └────────────────────┘
│ • late_upload           │                      │
│ • previous_period       │                      ▼
└─────────────────────────┘              Reporte Ejecutivo
```

**Resultado:** Misma calidad de detección, 1-2 LLM calls, funciona en free tier.

---

## Tests

```bash
# Ejecutar todos los tests
python -m pytest tests/ -v

# Ejecutar un test específico
python -m pytest tests/test_data_tools.py -v
```

---

## Decisiones de Diseño Documentadas

Consultar `docs/challenges_and_lessons.md` para el detalle completo. Resumen:

1. **Multi-agente vs Híbrida**: v1/v2 demuestran capacidad ADK, v3 resuelve limitaciones reales
2. **6 detectores especializados**: Separación de responsabilidades para testeo independiente
3. **Python para detección**: Contar archivos es math, no lenguaje → no necesita LLM
4. **LLM para reporte**: Sintetizar, priorizar y redactar sí requiere inteligencia lingüística
5. **Versionamiento por carpetas**: Permite comparar lado a lado sin perder historial

Consultar `docs/images/` para el diagrama visual de la arquitectura.

---

## Stack Tecnológico

| Componente | Tecnología |
|-----------|-----------|
| Framework de agentes | Google ADK (Agent Development Kit) |
| Modelo LLM | Gemini 2.0 Flash |
| Lenguaje | Python 3.10+ |
| Evaluación | Custom pipeline + LLM-as-Judge |
| MCP (bonus) | Slack MCP Server |
| GCP (diseño futuro) | Vertex AI, Cloud Functions, GCS, BigQuery |
