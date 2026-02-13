"""
Agent Definition v1 - Baseline (Multi-Agent Architecture)
=========================================================
Define el agente multi-agente usando Google ADK (Agent Development Kit).

Arquitectura:
- 1 Orquestador principal (root agent)
- 6 Sub-agentes detectores (delegados por el orquestador)
- 1 Sub-agente consolidador de reporte

¿Cómo funciona ADK?
- Agent: Un agente con instrucciones (prompt), modelo LLM y herramientas
- FunctionTool: Funciones Python que el agente puede invocar
- Sub-agents: Agentes hijos a los que el agente padre puede delegar
- Runner: Ejecuta el agente y maneja la sesión
- InMemorySessionService: Almacena el estado de la conversación en memoria

NOTE: This version requires a paid Gemini plan (~2,000 req/min) due to
the high number of LLM calls (~20+ per execution). On free tier (~15 req/min),
it will hit rate limits (429 RESOURCE_EXHAUSTED). See v3 for a hybrid 
approach that works within free tier limits.
"""

import os
import json
from dotenv import load_dotenv

# Google ADK imports
from google.adk.agents import Agent
from google.adk.tools import FunctionTool
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai import types

# Nuestras tools y prompts
from agents.v1.tools.data_tools import (
    get_source_list,
    parse_cv,
    load_today_files,
    load_last_weekday_files,
    get_available_dates,
    get_cv_summary_for_detector,
)
from agents.v1.prompts.templates import (
    ORCHESTRATOR_PROMPT,
    MISSING_FILE_DETECTOR_PROMPT,
    DUPLICATED_FAILED_DETECTOR_PROMPT,
    EMPTY_FILE_DETECTOR_PROMPT,
    VOLUME_VARIATION_DETECTOR_PROMPT,
    LATE_UPLOAD_DETECTOR_PROMPT,
    PREVIOUS_PERIOD_DETECTOR_PROMPT,
    REPORT_CONSOLIDATOR_PROMPT,
)

# Cargar variables de entorno (.env)
load_dotenv()

# Force API key mode (not Vertex AI)
os.environ["GOOGLE_GENAI_USE_VERTEXAI"] = "FALSE"

# =============================================================================
# CONFIGURACIÓN
# =============================================================================

MODEL_NAME = os.getenv("MODEL_NAME", "gemini-2.0-flash")


# =============================================================================
# DEFINICIÓN DE TOOLS (FunctionTool)
# Estas son las funciones que los agentes pueden invocar.
# ADK las convierte automáticamente en herramientas que el LLM puede usar.
# =============================================================================

# Tools compartidas - todos los agentes pueden usar estas
shared_tools = [
    FunctionTool(get_source_list),
    FunctionTool(parse_cv),
    FunctionTool(load_today_files),
    FunctionTool(load_last_weekday_files),
    FunctionTool(get_available_dates),
    FunctionTool(get_cv_summary_for_detector),
]


# =============================================================================
# SUB-AGENTES DETECTORES
# Cada uno tiene sus propias instrucciones especializadas.
# El orquestador delega a estos agentes cuando necesita detectar incidencias.
# =============================================================================

missing_file_detector = Agent(
    name="missing_file_detector",
    model=MODEL_NAME,
    description="Detects missing files that were expected but not received. "
                "Delegate to this agent when you need to check if all expected files arrived for a source.",
    instruction=MISSING_FILE_DETECTOR_PROMPT,
    tools=shared_tools,
)

duplicated_failed_detector = Agent(
    name="duplicated_failed_detector",
    model=MODEL_NAME,
    description="Detects duplicated or failed files. "
                "Delegate to this agent when you need to check for duplicates or processing failures.",
    instruction=DUPLICATED_FAILED_DETECTOR_PROMPT,
    tools=shared_tools,
)

empty_file_detector = Agent(
    name="empty_file_detector",
    model=MODEL_NAME,
    description="Detects unexpected empty files (0 records when data was expected). "
                "Delegate to this agent to check if any empty files are anomalous.",
    instruction=EMPTY_FILE_DETECTOR_PROMPT,
    tools=shared_tools,
)

volume_variation_detector = Agent(
    name="volume_variation_detector",
    model=MODEL_NAME,
    description="Detects unexpected volume variations in record counts. "
                "Delegate to this agent to check if file volumes are within expected ranges.",
    instruction=VOLUME_VARIATION_DETECTOR_PROMPT,
    tools=shared_tools,
)

late_upload_detector = Agent(
    name="late_upload_detector",
    model=MODEL_NAME,
    description="Detects files uploaded more than 4 hours after the expected schedule. "
                "Delegate to this agent to check upload timing compliance.",
    instruction=LATE_UPLOAD_DETECTOR_PROMPT,
    tools=shared_tools,
)

previous_period_detector = Agent(
    name="previous_period_detector",
    model=MODEL_NAME,
    description="Detects files from previous periods uploaded outside the Expected Coverage Data window. "
                "Delegate to this agent to identify backfill or manual uploads.",
    instruction=PREVIOUS_PERIOD_DETECTOR_PROMPT,
    tools=shared_tools,
)

# =============================================================================
# SUB-AGENTE CONSOLIDADOR DE REPORTE
# =============================================================================

report_consolidator = Agent(
    name="report_consolidator",
    model=MODEL_NAME,
    description="Consolidates all detector findings into a final executive incident report. "
                "Delegate to this agent after ALL detectors have finished analyzing ALL sources.",
    instruction=REPORT_CONSOLIDATOR_PROMPT,
    tools=[],  # No necesita tools, solo recibe los resultados y genera el reporte
)


# =============================================================================
# AGENTE ORQUESTADOR PRINCIPAL (ROOT AGENT)
# Este es el agente que el usuario ejecuta. Coordina todo el flujo.
# =============================================================================

def create_orchestrator(execution_date: str) -> Agent:
    """
    Crea el agente orquestador principal configurado para una fecha específica.
    
    Args:
        execution_date: Fecha en formato "YYYY-MM-DD"
    
    Returns:
        Agent configurado y listo para ejecutar
    """
    orchestrator = Agent(
        name="incident_detection_orchestrator",
        model=MODEL_NAME,
        description="Main orchestrator agent that coordinates incident detection across all data sources.",
        instruction=ORCHESTRATOR_PROMPT.format(execution_date=execution_date),
        tools=shared_tools,
        sub_agents=[
            missing_file_detector,
            duplicated_failed_detector,
            empty_file_detector,
            volume_variation_detector,
            late_upload_detector,
            previous_period_detector,
            report_consolidator,
        ],
    )
    return orchestrator


# =============================================================================
# FUNCIÓN DE EJECUCIÓN
# Crea un Runner y ejecuta el agente completo
# =============================================================================

async def run_agent(execution_date: str) -> str:
    """
    Ejecuta el agente de detección de incidencias para una fecha específica.
    
    Args:
        execution_date: Fecha en formato "YYYY-MM-DD" (ej: "2025-09-08")
    
    Returns:
        El reporte final generado por el agente
    """
    # Crear el orquestador
    orchestrator = create_orchestrator(execution_date)
    
    # Crear el servicio de sesiones (en memoria)
    session_service = InMemorySessionService()
    
    # Crear el runner
    runner = Runner(
        agent=orchestrator,
        app_name="incident_detection",
        session_service=session_service,
    )
    
    # Crear una sesión
    session = await session_service.create_session(
        app_name="incident_detection",
        user_id="operator",
    )
    
    # Mensaje inicial al agente
    user_message = types.Content(
        role="user",
        parts=[types.Part(text=(
            f"Analyze all data sources for date {execution_date}. "
            f"Run all 6 detectors on all 18 sources and generate the consolidated incident report. "
            f"Start by getting the source list, then for each source gather the CV summary and today's files, "
            f"then run each detector, and finally consolidate the report."
        ))]
    )
    
    # Ejecutar el agente y recopilar respuestas
    final_response = ""
    async for event in runner.run_async(
        user_id="operator",
        session_id=session.id,
        new_message=user_message,
    ):
        if event.is_final_response():
            if event.content and event.content.parts:
                for part in event.content.parts:
                    if part.text:
                        final_response += part.text
    
    return final_response
