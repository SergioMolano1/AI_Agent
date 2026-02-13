"""
MCP Integration Example
========================
Muestra cómo conectar el MCP Server de Slack con el agente ADK.

Google ADK soporta MCP tools de forma nativa, lo que significa que
se puede agregar cualquier MCP Server como herramienta de los agentes.

Uso:
    python mcp_tools/integration_example.py --date 2025-09-08

Prerequisitos:
    pip install google-adk mcp httpx
    Configurar SLACK_WEBHOOK_URL en .env
"""

import os
import asyncio
from dotenv import load_dotenv

load_dotenv()


async def run_agent_with_slack(execution_date: str):
    """
    Ejecuta el agente v2 con la capacidad de enviar reportes a Slack.
    
    La integración funciona así:
    1. Se crea el MCP Tool a partir de nuestro servidor
    2. Se agrega como tool al agente consolidador de reportes
    3. Cuando el agente genera el reporte, puede invocar send_slack_notification()
    4. El reporte llega al canal de Slack automáticamente
    """
    from google.adk.agents import Agent
    from google.adk.tools import FunctionTool
    from google.adk.runners import Runner
    from google.adk.sessions import InMemorySessionService
    from google.genai import types
    
    # Importar tools de datos
    from agents.v1.tools.data_tools import (
        get_source_list, parse_cv, load_today_files,
        load_last_weekday_files, get_available_dates,
        get_cv_summary_for_detector,
    )
    from agents.v2.prompts.templates import (
        ORCHESTRATOR_PROMPT, REPORT_CONSOLIDATOR_PROMPT,
        MISSING_FILE_DETECTOR_PROMPT, DUPLICATED_FAILED_DETECTOR_PROMPT,
        EMPTY_FILE_DETECTOR_PROMPT, VOLUME_VARIATION_DETECTOR_PROMPT,
        LATE_UPLOAD_DETECTOR_PROMPT, PREVIOUS_PERIOD_DETECTOR_PROMPT,
    )

    MODEL_NAME = os.getenv("MODEL_NAME", "gemini-2.0-flash")

    shared_tools = [
        FunctionTool(get_source_list),
        FunctionTool(parse_cv),
        FunctionTool(load_today_files),
        FunctionTool(load_last_weekday_files),
        FunctionTool(get_available_dates),
        FunctionTool(get_cv_summary_for_detector),
    ]

    # =========================================================================
    # OPCIÓN A: MCP Tool via MCPToolset (conexión a MCP Server externo)
    # =========================================================================
    # Si el MCP Server corre como proceso independiente:
    #
    # from google.adk.tools.mcp_tool import MCPToolset, StdioServerParameters
    #
    # mcp_tools, exit_stack = await MCPToolset.from_server(
    #     connection_params=StdioServerParameters(
    #         command="python",
    #         args=["mcp_tools/slack_server.py"]
    #     )
    # )
    # notification_tools = mcp_tools  # Lista de tools del MCP Server
    
    # =========================================================================
    # OPCIÓN B: FunctionTool directo (más simple para este caso)
    # Usamos la lógica del MCP Server como FunctionTool de ADK
    # =========================================================================
    
    async def send_report_to_slack(report_text: str, severity: str = "info") -> dict:
        """
        Sends the incident report to the configured Slack channel.
        Use this after generating the final report to notify the team.
        
        Args:
            report_text: The complete incident report in markdown
            severity: Overall report severity - "urgent", "attention", or "ok"
        
        Returns:
            Confirmation of delivery
        """
        try:
            from mcp_tools.slack_server import send_slack_notification
            result = await send_slack_notification(report_text, severity=severity)
            return result
        except ImportError:
            return {
                "success": False,
                "error": "MCP tools not available. Install: pip install mcp httpx"
            }
    
    slack_tool = FunctionTool(send_report_to_slack)

    # Crear los detectores (mismo patrón que v2)
    detector_configs = [
        ("missing_file_detector", MISSING_FILE_DETECTOR_PROMPT, "Detects missing files"),
        ("duplicated_failed_detector", DUPLICATED_FAILED_DETECTOR_PROMPT, "Detects duplicates/failures"),
        ("empty_file_detector", EMPTY_FILE_DETECTOR_PROMPT, "Detects unexpected empty files"),
        ("volume_variation_detector", VOLUME_VARIATION_DETECTOR_PROMPT, "Detects volume anomalies"),
        ("late_upload_detector", LATE_UPLOAD_DETECTOR_PROMPT, "Detects late uploads"),
        ("previous_period_detector", PREVIOUS_PERIOD_DETECTOR_PROMPT, "Detects previous period files"),
    ]
    
    detectors = [
        Agent(name=name, model=MODEL_NAME, description=desc, instruction=prompt, tools=shared_tools)
        for name, prompt, desc in detector_configs
    ]

    # Consolidador con capacidad de enviar a Slack
    report_consolidator = Agent(
        name="report_consolidator",
        model=MODEL_NAME,
        description="Consolidates findings into a report and sends it to Slack.",
        instruction=REPORT_CONSOLIDATOR_PROMPT.format(execution_date=execution_date) + """

ADDITIONAL CAPABILITY:
After generating the report, use the send_report_to_slack tool to notify the team.
Determine the overall severity:
- "urgent" if there are any 🔴 items
- "attention" if there are 🟡 items but no 🔴
- "ok" if everything is 🟢
""",
        tools=[slack_tool],
    )

    # Orquestador principal
    orchestrator = Agent(
        name="incident_detection_orchestrator_v2_slack",
        model=MODEL_NAME,
        description="Main orchestrator with Slack notification capability.",
        instruction=ORCHESTRATOR_PROMPT.format(execution_date=execution_date),
        tools=shared_tools,
        sub_agents=detectors + [report_consolidator],
    )

    # Ejecutar
    session_service = InMemorySessionService()
    runner = Runner(
        agent=orchestrator,
        app_name="incident_detection_slack",
        session_service=session_service,
    )
    
    session = await session_service.create_session(
        app_name="incident_detection_slack",
        user_id="operator",
    )
    
    user_message = types.Content(
        role="user",
        parts=[types.Part(text=(
            f"Analyze all data sources for {execution_date}. "
            f"Run all detectors, generate the report, and send it to Slack."
        ))]
    )
    
    print(f"🚀 Running agent with Slack integration for {execution_date}...")
    
    final_response = ""
    async for event in runner.run_async(
        user_id="operator",
        session_id=session.id,
        new_message=user_message,
    ):
        if event.is_final_response():
            for part in event.content.parts:
                if part.text:
                    final_response += part.text
    
    print(f"\n📄 Report generated and sent to Slack!")
    return final_response


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", default="2025-09-08")
    args = parser.parse_args()
    
    asyncio.run(run_agent_with_slack(args.date))
