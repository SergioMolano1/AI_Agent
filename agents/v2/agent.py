"""
Agent Definition v2 - Improved Based on Evaluation
===================================================
CHANGELOG from v1:
- Prompts improved based on stakeholder feedback (see prompts/templates.py)
- Same multi-agent architecture (ADK orchestrator + 6 sub-agents + consolidator)
- Same tools (data processing doesn't change)
- The improvement is in HOW the agents reason and communicate

This demonstrates the evolutionary versioning approach:
v1 (baseline) → evaluate → identify gaps → v2 (improved prompts) → evaluate again

NOTE: Like v1, this version requires a paid Gemini plan due to 20+ LLM calls.
See v3 for an architecture-optimized version that works on free tier.
"""

import os
from dotenv import load_dotenv

from google.adk.agents import Agent
from google.adk.tools import FunctionTool
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai import types

# V2 reuses v1 tools (data processing is the same)
from agents.v1.tools.data_tools import (
    get_source_list,
    parse_cv,
    load_today_files,
    load_last_weekday_files,
    get_available_dates,
    get_cv_summary_for_detector,
)

# V2 uses IMPROVED prompts
from agents.v2.prompts.templates import (
    ORCHESTRATOR_PROMPT,
    MISSING_FILE_DETECTOR_PROMPT,
    DUPLICATED_FAILED_DETECTOR_PROMPT,
    EMPTY_FILE_DETECTOR_PROMPT,
    VOLUME_VARIATION_DETECTOR_PROMPT,
    LATE_UPLOAD_DETECTOR_PROMPT,
    PREVIOUS_PERIOD_DETECTOR_PROMPT,
    REPORT_CONSOLIDATOR_PROMPT,
)

load_dotenv()

# Force API key mode (not Vertex AI)
os.environ["GOOGLE_GENAI_USE_VERTEXAI"] = "FALSE"

MODEL_NAME = os.getenv("MODEL_NAME", "gemini-2.0-flash")

# Shared tools (same as v1)
shared_tools = [
    FunctionTool(get_source_list),
    FunctionTool(parse_cv),
    FunctionTool(load_today_files),
    FunctionTool(load_last_weekday_files),
    FunctionTool(get_available_dates),
    FunctionTool(get_cv_summary_for_detector),
]

# Sub-agents with IMPROVED prompts
missing_file_detector = Agent(
    name="missing_file_detector",
    model=MODEL_NAME,
    description="Detects missing files that were expected but not received.",
    instruction=MISSING_FILE_DETECTOR_PROMPT,
    tools=shared_tools,
)

duplicated_failed_detector = Agent(
    name="duplicated_failed_detector",
    model=MODEL_NAME,
    description="Detects duplicated or failed files.",
    instruction=DUPLICATED_FAILED_DETECTOR_PROMPT,
    tools=shared_tools,
)

empty_file_detector = Agent(
    name="empty_file_detector",
    model=MODEL_NAME,
    description="Detects unexpected empty files (0 records when data was expected).",
    instruction=EMPTY_FILE_DETECTOR_PROMPT,
    tools=shared_tools,
)

volume_variation_detector = Agent(
    name="volume_variation_detector",
    model=MODEL_NAME,
    description="Detects unexpected volume variations in record counts.",
    instruction=VOLUME_VARIATION_DETECTOR_PROMPT,
    tools=shared_tools,
)

late_upload_detector = Agent(
    name="late_upload_detector",
    model=MODEL_NAME,
    description="Detects files uploaded more than 4 hours after the expected schedule.",
    instruction=LATE_UPLOAD_DETECTOR_PROMPT,
    tools=shared_tools,
)

previous_period_detector = Agent(
    name="previous_period_detector",
    model=MODEL_NAME,
    description="Detects files from previous periods uploaded outside the Expected Coverage Data window.",
    instruction=PREVIOUS_PERIOD_DETECTOR_PROMPT,
    tools=shared_tools,
)

# Report consolidator with SIGNIFICANTLY improved prompt
report_consolidator = Agent(
    name="report_consolidator",
    model=MODEL_NAME,
    description="Consolidates all findings into a clear, business-friendly executive report.",
    instruction=REPORT_CONSOLIDATOR_PROMPT,
    tools=[],
)


def create_orchestrator(execution_date: str) -> Agent:
    """Creates the v2 orchestrator agent."""
    return Agent(
        name="incident_detection_orchestrator_v2",
        model=MODEL_NAME,
        description="Main orchestrator (v2 - improved based on evaluation feedback).",
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


async def run_agent(execution_date: str) -> str:
    """Runs the v2 incident detection agent."""
    orchestrator = create_orchestrator(execution_date)
    session_service = InMemorySessionService()
    
    runner = Runner(
        agent=orchestrator,
        app_name="incident_detection_v2",
        session_service=session_service,
    )
    
    session = await session_service.create_session(
        app_name="incident_detection_v2",
        user_id="operator",
    )
    
    user_message = types.Content(
        role="user",
        parts=[types.Part(text=(
            f"Analyze all data sources for date {execution_date}. "
            f"Run all 6 detectors on all 18 sources and generate the consolidated incident report. "
            f"Be direct and clear in the report — use business language, not technical jargon."
        ))]
    )
    
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
