"""
Agent Definition v3 - Hybrid Architecture (Architecture Optimization)
=====================================================================
CHANGELOG from v2:
- ARCHITECTURE CHANGE: From full multi-agent LLM (20+ calls) to hybrid approach
- DETECTION: Python deterministic rules (6 detectors, zero LLM calls)
- REPORT: Single LLM call for executive report consolidation
- RESULT: ~1-2 LLM calls instead of 20+, works within free tier limits

Why this change?
  v1/v2 use 8 LLM agents (orchestrator + 6 detectors + consolidator) making ~20+
  API calls per execution. Gemini free tier allows only ~15 req/min, causing
  429 RESOURCE_EXHAUSTED errors. 
  
  Key insight: Detection is DETERMINISTIC — counting files, comparing volumes, 
  checking timestamps are math operations, not language tasks. The LLM adds 
  value only in the final step: writing a clear, business-friendly report.

Architecture evolution:
  v1: Multi-agent + basic prompts         → 20+ LLM calls, rate limited
  v2: Multi-agent + improved prompts      → 20+ LLM calls, rate limited  
  v3: Deterministic detection + LLM report → 1-2 LLM calls, works on free tier

ADK Components Used:
  - Agent: Report consolidator (single agent, uses improved v2 prompts)
  - FunctionTool: Wraps the rule-based detection pipeline
  - Runner: Executes the agent session
  - InMemorySessionService: Session management
"""

import os
import json
import asyncio
from datetime import datetime
from dotenv import load_dotenv

# Google ADK imports
from google.adk.agents import Agent
from google.adk.tools import FunctionTool
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai import types

# Rule-based detectors (no LLM needed)
from agents.v3.detectors.rule_based import run_all_detectors, format_findings_for_llm

# v3 uses v2's improved prompts as base (inherits feedback-driven improvements)
from agents.v3.prompts.templates import REPORT_CONSOLIDATOR_PROMPT

# Load env
load_dotenv()

# Force API key mode (not Vertex AI)
os.environ["GOOGLE_GENAI_USE_VERTEXAI"] = "FALSE"

MODEL_NAME = os.getenv("MODEL_NAME", "gemini-2.0-flash")


# =============================================================================
# TOOL: Run Detection Pipeline (deterministic, no LLM)
# =============================================================================

def run_detection_pipeline(execution_date: str) -> str:
    """
    Runs all 6 rule-based detectors across all 18 data sources for the given date.
    This function uses pure Python logic — no LLM calls — making it fast,
    deterministic, and free of rate limit concerns.
    
    Args:
        execution_date: Date in YYYY-MM-DD format (e.g., "2025-09-08")
    
    Returns:
        Structured text with all findings organized by severity
    """
    print(f"  🔍 Running rule-based detectors for {execution_date}...")
    findings = run_all_detectors(execution_date)
    
    urgent = sum(1 for f in findings.values() if f["overall_severity"] == "urgent")
    attention = sum(1 for f in findings.values() if f["overall_severity"] == "attention")
    ok = sum(1 for f in findings.values() if f["overall_severity"] == "ok")
    total_incidents = sum(len(f["incidents"]) for f in findings.values())
    
    print(f"  ✅ Detection complete: {urgent} urgent, {attention} attention, {ok} ok ({total_incidents} total incidents)")
    
    return format_findings_for_llm(findings, execution_date)


# =============================================================================
# AGENT: Report Consolidator (single ADK agent — the only LLM call)
# =============================================================================

def create_orchestrator(execution_date: str) -> Agent:
    """
    Creates the hybrid agent: deterministic detection + LLM report generation.
    
    Flow:
    1. Agent calls run_detection_pipeline() tool → gets structured findings (no LLM)
    2. Agent writes the executive report based on findings (1 LLM call)
    """
    detection_tool = FunctionTool(run_detection_pipeline)
    
    orchestrator = Agent(
        name="incident_detection_hybrid_v3",
        model=MODEL_NAME,
        description="Hybrid incident detection agent: rule-based detection + LLM report generation.",
        instruction=REPORT_CONSOLIDATOR_PROMPT.format(execution_date=execution_date) + f"""

IMPORTANT: You have a tool called 'run_detection_pipeline' that runs all 6 detectors 
across all 18 data sources using deterministic Python rules. 
Call it first with execution_date="{execution_date}", then use the results to generate 
the consolidated executive report.

The tool does the heavy lifting (detection). Your job is to write a clear, 
business-friendly report based on the findings. Use the improved language and 
formatting standards from the stakeholder feedback.
""",
        tools=[detection_tool],
    )
    return orchestrator


# =============================================================================
# EXECUTION
# =============================================================================

async def run_agent(execution_date: str) -> str:
    """Executes the v3 hybrid incident detection agent for a specific date."""
    orchestrator = create_orchestrator(execution_date)
    session_service = InMemorySessionService()
    
    runner = Runner(
        agent=orchestrator,
        app_name="incident_detection_v3",
        session_service=session_service,
    )
    
    session = await session_service.create_session(
        app_name="incident_detection_v3",
        user_id="operator",
    )
    
    user_message = types.Content(
        role="user",
        parts=[types.Part(text=(
            f"Run the detection pipeline for date {execution_date} "
            f"and generate the consolidated incident report. "
            f"Be direct and concise — use business language, not technical jargon."
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
