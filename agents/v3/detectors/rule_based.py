"""
Rule-Based Detectors
====================
Detectores basados en reglas Python puras (sin LLM).

¿Por qué cambiar de LLM a reglas?
- La detección de incidencias es DETERMINÍSTICA: si faltan 14 de 18 archivos, eso es un hecho
- Es más rápido, barato, y no depende de rate limits
- El LLM se usa donde si agrega valor: redactar el reporte ejecutivo

Esta es una decisión de diseño documentada en docs/challenges_and_lessons.md
"""

import json
import re
from datetime import datetime
from typing import List, Dict, Optional

from agents.v1.tools.data_tools import (
    get_source_list,
    parse_cv,
    load_today_files,
    load_last_weekday_files,
    get_cv_summary_for_detector,
)


# =============================================================================
# DETECTOR 1: Missing Files
# =============================================================================

def detect_missing_files(source_id: str, execution_date: str) -> dict:
    """Detecta archivos faltantes comparando esperados vs recibidos."""
    cv = parse_cv(source_id)
    today = load_today_files(source_id, execution_date)
    last_wk = load_last_weekday_files(source_id, execution_date)
    
    if "error" in cv or "error" in today:
        return {"source_id": source_id, "detector": "missing_file", "incidents": []}
    
    day_abbr = today["day_of_week"]  # Mon, Tue, etc.
    
    # Get expected file count for this day
    file_stats = cv["file_patterns"].get(day_abbr, {})
    expected_mean = file_stats.get("mean_files", 0)
    expected_min = file_stats.get("min_files", 0)
    expected_stdev = file_stats.get("stdev_files", 0)
    received = today["today_file_count"]
    
    incidents = []
    
    # If this day normally has 0 files, no incident
    if expected_mean == 0 and expected_min == 0:
        return {"source_id": source_id, "source_name": cv["source_name"],
                "detector": "missing_file", "incidents": []}
    
    # Check if significantly fewer files than expected
    if received < expected_min and expected_mean > 0:
        missing_count = int(expected_mean) - received
        severity = "urgent" if received < expected_mean * 0.5 else "attention"
        
        # Get last weekday count for comparison
        lw_count = last_wk.get("last_weekday_file_count", 0)
        
        incidents.append({
            "type": "missing_files",
            "severity": severity,
            "expected_count": int(expected_mean),
            "received_count": received,
            "missing_count": missing_count,
            "last_weekday_count": lw_count,
            "details": f"Only {received} of {int(expected_mean)} expected files received. "
                       f"Minimum expected: {expected_min}. Last {day_abbr}: {lw_count} files."
        })
    
    return {"source_id": source_id, "source_name": cv["source_name"],
            "detector": "missing_file", "incidents": incidents}


# =============================================================================
# DETECTOR 2: Duplicated & Failed Files
# =============================================================================

def detect_duplicated_failed(source_id: str, execution_date: str) -> dict:
    """Detecta archivos duplicados o con status failed/stopped."""
    cv = parse_cv(source_id)
    today = load_today_files(source_id, execution_date)
    
    if "error" in cv or "error" in today:
        return {"source_id": source_id, "detector": "duplicated_failed", "incidents": []}
    
    incidents = []
    
    for f in today.get("today_files", []):
        is_dup = f.get("is_duplicated", False)
        status = f.get("status", "")
        filename = f.get("filename", "unknown")
        
        # Duplicated + stopped = problematic
        if is_dup and status in ("stopped", "failure"):
            incidents.append({
                "type": "duplicated_file",
                "severity": "urgent",
                "filename": filename,
                "status": status,
                "is_duplicated": True,
                "details": f"File '{filename}' is duplicated with status '{status}'"
            })
        elif status in ("failure",):
            incidents.append({
                "type": "failed_file",
                "severity": "attention",
                "filename": filename,
                "status": status,
                "is_duplicated": is_dup,
                "details": f"File '{filename}' has status '{status}'"
            })
        elif is_dup and status == "stopped":
            incidents.append({
                "type": "duplicated_file",
                "severity": "attention",
                "filename": filename,
                "status": status,
                "is_duplicated": True,
                "details": f"File '{filename}' is a duplicate (stopped)"
            })
    
    return {"source_id": source_id, "source_name": cv.get("source_name", ""),
            "detector": "duplicated_failed", "incidents": incidents}


# =============================================================================
# DETECTOR 3: Unexpected Empty Files
# =============================================================================

def detect_unexpected_empty(source_id: str, execution_date: str) -> dict:
    """Detecta archivos vacíos que no deberían estar vacíos."""
    cv = parse_cv(source_id)
    today = load_today_files(source_id, execution_date)
    
    if "error" in cv or "error" in today:
        return {"source_id": source_id, "detector": "unexpected_empty", "incidents": []}
    
    day_abbr = today["day_of_week"]
    
    # Get expected empty file stats for this day
    dow_summary = cv["day_of_week_summary"].get(day_abbr, {})
    empty_stats = dow_summary.get("empty_files", {})
    expected_empty_mean = empty_stats.get("mean", 0)
    
    # Also check overall processing status
    proc_status = cv.get("processing_status", {})
    overall_empty_pct = proc_status.get("empty", {}).get("percentage", 0)
    
    # Known patterns where empty is normal
    known_empty_patterns = {
        "207936": ["POS"],          # POS always empty
        "207938": ["POS_MARKETPLACE"],  # POS marketplace always empty
        "220504": ["Innovation", "POC", "safemode"],  # These entities always empty
        "195436": None,             # High empty rate Mon/Tue is normal
    }
    
    incidents = []
    empty_files = [f for f in today.get("today_files", []) if f.get("rows", 0) == 0]
    
    for f in empty_files:
        filename = f.get("filename", "")
        
        # Check if this is a known empty pattern
        if source_id in known_empty_patterns:
            patterns = known_empty_patterns[source_id]
            if patterns is None:
                # Source has generally high empty rate — check day-specific
                if expected_empty_mean > 0.3:
                    continue  # Normal for this day
            elif any(p.lower() in filename.lower() for p in patterns):
                continue  # Known empty pattern for this entity
        
        # If this day normally has many empty files, skip
        if expected_empty_mean > 0.5:
            continue
        
        # If overall empty rate is very high, it's a pattern
        if overall_empty_pct > 20:
            continue
        
        incidents.append({
            "type": "unexpected_empty_file",
            "severity": "attention",
            "filename": filename,
            "expected_empty_mean": expected_empty_mean,
            "details": f"File '{filename}' has 0 records. "
                       f"Expected empty files for {day_abbr}: mean={expected_empty_mean:.1f}"
        })
    
    return {"source_id": source_id, "source_name": cv.get("source_name", ""),
            "detector": "unexpected_empty", "incidents": incidents}


# =============================================================================
# DETECTOR 4: Volume Variation
# =============================================================================

def detect_volume_variation(source_id: str, execution_date: str) -> dict:
    """Detecta variaciones anormales de volumen comparando contra el CV."""
    cv = parse_cv(source_id)
    today = load_today_files(source_id, execution_date)
    last_wk = load_last_weekday_files(source_id, execution_date)
    
    if "error" in cv or "error" in today:
        return {"source_id": source_id, "detector": "volume_variation", "incidents": []}
    
    day_abbr = today["day_of_week"]
    today_rows = today["today_total_rows"]
    
    # Get expected volume for this day from CV
    dow_summary = cv["day_of_week_summary"].get(day_abbr, {})
    row_stats = dow_summary.get("row_stats", {})
    
    expected_mean = row_stats.get("mean", 0)
    expected_min = row_stats.get("min", 0)
    expected_max = row_stats.get("max", 0)
    expected_median = row_stats.get("median", 0)
    
    # Also get overall volume stats
    vol_stats = cv.get("volume_stats", {})
    overall_stdev = float(vol_stats.get("stdev", 0)) if vol_stats.get("stdev") else 0
    
    lw_rows = last_wk.get("last_weekday_total_rows", 0)
    
    incidents = []
    
    # Skip if no volume data or day normally has 0
    if expected_mean == 0 and expected_median == 0:
        return {"source_id": source_id, "source_name": cv.get("source_name", ""),
                "detector": "volume_variation", "incidents": []}
    
    # Check if this source normally has high empty rate on this day
    # (e.g., MyPal_DBR RX has 83% empty files on Mondays — 0 rows is NORMAL)
    empty_rate = dow_summary.get("empty_files", {}).get("mean", 0)
    day_normally_empty = (empty_rate > 0.5 and expected_median == 0)
    
    # Check for volume anomaly
    if expected_mean > 0 and today_rows > 0:
        deviation_pct = ((today_rows - expected_mean) / expected_mean) * 100
        
        # Flag if outside expected range by significant margin
        if today_rows > expected_max * 1.5 and abs(deviation_pct) > 50:
            incidents.append({
                "type": "unexpected_volume_high",
                "severity": "attention",
                "today_rows": today_rows,
                "expected_mean": expected_mean,
                "expected_range": f"{expected_min}-{expected_max}",
                "deviation_pct": f"{deviation_pct:+.1f}%",
                "last_weekday_rows": lw_rows,
                "details": f"Volume {today_rows:,} rows is {deviation_pct:+.1f}% vs expected mean {expected_mean:,.0f}. "
                           f"Range: {expected_min:,.0f}-{expected_max:,.0f}. Last {day_abbr}: {lw_rows:,} rows."
            })
        elif today_rows < expected_min * 0.5 and expected_min > 0:
            incidents.append({
                "type": "unexpected_volume_low",
                "severity": "urgent" if deviation_pct < -70 else "attention",
                "today_rows": today_rows,
                "expected_mean": expected_mean,
                "expected_range": f"{expected_min}-{expected_max}",
                "deviation_pct": f"{deviation_pct:+.1f}%",
                "last_weekday_rows": lw_rows,
                "details": f"Volume {today_rows:,} rows is {deviation_pct:+.1f}% vs expected mean {expected_mean:,.0f}. "
                           f"Range: {expected_min:,.0f}-{expected_max:,.0f}. Last {day_abbr}: {lw_rows:,} rows."
            })
    elif expected_mean > 0 and today_rows == 0:
        if day_normally_empty:
            # This source normally has 0 rows on this day (e.g., MyPal Mon/Tue)
            # Don't flag as urgent — it's expected behavior
            pass
        else:
            incidents.append({
                "type": "unexpected_volume_low",
                "severity": "urgent",
                "today_rows": 0,
                "expected_mean": expected_mean,
                "expected_range": f"{expected_min}-{expected_max}",
                "deviation_pct": "-100%",
                "last_weekday_rows": lw_rows,
                "details": f"ZERO records received. Expected mean: {expected_mean:,.0f}."
            })
    
    return {"source_id": source_id, "source_name": cv.get("source_name", ""),
            "detector": "volume_variation", "incidents": incidents}


# =============================================================================
# DETECTOR 5: Late Upload
# =============================================================================

def detect_late_upload(source_id: str, execution_date: str) -> dict:
    """Detecta archivos subidos fuera del horario esperado (>4h tarde)."""
    cv = parse_cv(source_id)
    today = load_today_files(source_id, execution_date)
    
    if "error" in cv or "error" in today:
        return {"source_id": source_id, "detector": "late_upload", "incidents": []}
    
    day_abbr = today["day_of_week"]
    schedule = cv["upload_schedule"].get(day_abbr, {})
    
    if not schedule or not schedule.get("expected_window"):
        return {"source_id": source_id, "source_name": cv.get("source_name", ""),
                "detector": "late_upload", "incidents": []}
    
    # Parse expected window end time
    window = schedule.get("expected_window", "")
    # Format: "08:00:00–09:00:00 UTC" or similar
    times = re.findall(r'(\d{1,2}:\d{2})', window)
    if len(times) < 2:
        return {"source_id": source_id, "source_name": cv.get("source_name", ""),
                "detector": "late_upload", "incidents": []}
    
    window_end_str = times[-1]  # Last time in the window
    window_end_hour = int(window_end_str.split(":")[0])
    window_end_min = int(window_end_str.split(":")[1])
    
    incidents = []
    LATE_THRESHOLD_HOURS = 4
    
    for f in today.get("today_files", []):
        uploaded_at = f.get("uploaded_at", "")
        if not uploaded_at:
            continue
        
        try:
            upload_dt = datetime.fromisoformat(uploaded_at.replace("Z", "+00:00"))
            upload_hour = upload_dt.hour
            upload_min = upload_dt.minute
            
            # Calculate delay in hours
            upload_total_min = upload_hour * 60 + upload_min
            window_end_total_min = window_end_hour * 60 + window_end_min
            delay_min = upload_total_min - window_end_total_min
            
            if delay_min > LATE_THRESHOLD_HOURS * 60:
                delay_hours = delay_min / 60
                incidents.append({
                    "type": "late_upload",
                    "severity": "attention",  # NEVER urgent
                    "filename": f.get("filename", ""),
                    "uploaded_at": uploaded_at,
                    "expected_window": window,
                    "delay_hours": round(delay_hours, 1),
                    "details": f"File uploaded {delay_hours:.1f}h after expected window ({window})"
                })
        except (ValueError, TypeError):
            continue
    
    return {"source_id": source_id, "source_name": cv.get("source_name", ""),
            "detector": "late_upload", "incidents": incidents}


# =============================================================================
# DETECTOR 6: Previous Period Upload
# =============================================================================

def detect_previous_period(source_id: str, execution_date: str) -> dict:
    """Detecta archivos de periodos anteriores uploadados HOY (backfills)."""
    today = load_today_files(source_id, execution_date)
    cv = parse_cv(source_id)
    
    if "error" in today or "error" in cv:
        return {"source_id": source_id, "detector": "previous_period", "incidents": []}
    
    exec_date = datetime.strptime(execution_date, "%Y-%m-%d").date()
    incidents = []
    
    # Only check files uploaded TODAY that have old dates in their filename
    for f in today.get("today_files", []):
        filename = f.get("filename", "")
        # Try to extract date from filename
        date_matches = re.findall(r'(\d{4}[-_]\d{2}[-_]\d{2})', filename)
        
        for date_str in date_matches:
            try:
                file_date = datetime.strptime(date_str.replace("_", "-"), "%Y-%m-%d").date()
                lag_days = (exec_date - file_date).days
                
                # Normal lag is 1-3 days for most sources. Flag if > 7 days
                if lag_days > 7:
                    incidents.append({
                        "type": "previous_period_upload",
                        "severity": "attention",  # NEVER urgent
                        "filename": filename,
                        "file_date": str(file_date),
                        "upload_date": execution_date,
                        "lag_days": lag_days,
                        "details": f"File from {file_date} uploaded today ({lag_days} days lag). Possible backfill."
                    })
            except ValueError:
                continue
    
    return {"source_id": source_id, "source_name": cv.get("source_name", ""),
            "detector": "previous_period", "incidents": incidents}


# =============================================================================
# MAIN: Run All Detectors for All Sources
# =============================================================================

def run_all_detectors(execution_date: str) -> dict:
    """
    Ejecuta los 6 detectores para las 18 fuentes.
    Retorna todos los hallazgos organizados por fuente.
    
    Esta función es 100% Python, sin LLM.
    """
    sources = get_source_list()
    all_findings = {}
    
    detectors = [
        ("missing_file", detect_missing_files),
        ("duplicated_failed", detect_duplicated_failed),
        ("unexpected_empty", detect_unexpected_empty),
        ("volume_variation", detect_volume_variation),
        ("late_upload", detect_late_upload),
        ("previous_period", detect_previous_period),
    ]
    
    for source_id, source_name in sources.items():
        source_findings = {
            "source_id": source_id,
            "source_name": source_name,
            "incidents": [],
        }
        
        for detector_name, detector_func in detectors:
            try:
                result = detector_func(source_id, execution_date)
                source_findings["incidents"].extend(result.get("incidents", []))
            except Exception as e:
                print(f"  ⚠️ Error in {detector_name} for {source_id}: {e}")
        
        # Classify overall severity
        severities = [i["severity"] for i in source_findings["incidents"]]
        urgent_count = severities.count("urgent")
        attention_count = severities.count("attention")
        
        if urgent_count > 0 or attention_count > 3:
            source_findings["overall_severity"] = "urgent"
        elif attention_count > 0:
            source_findings["overall_severity"] = "attention"
        else:
            source_findings["overall_severity"] = "ok"
        
        # Add today's stats
        today = load_today_files(source_id, execution_date)
        if "error" not in today:
            source_findings["today_file_count"] = today["today_file_count"]
            source_findings["today_total_rows"] = today["today_total_rows"]
        
        all_findings[source_id] = source_findings
    
    return all_findings


def format_findings_for_llm(findings: dict, execution_date: str) -> str:
    """
    Formatea los hallazgos en texto estructurado que el LLM
    usará para generar el reporte ejecutivo.
    """
    day_name = datetime.strptime(execution_date, "%Y-%m-%d").strftime("%A")
    
    lines = [
        f"INCIDENT DETECTION FINDINGS FOR {execution_date} ({day_name})",
        f"{'='*60}",
        ""
    ]
    
    # Group by severity
    urgent = {k: v for k, v in findings.items() if v["overall_severity"] == "urgent"}
    attention = {k: v for k, v in findings.items() if v["overall_severity"] == "attention"}
    ok = {k: v for k, v in findings.items() if v["overall_severity"] == "ok"}
    
    lines.append(f"SUMMARY: {len(urgent)} urgent, {len(attention)} attention, {len(ok)} ok")
    lines.append("")
    
    if urgent:
        lines.append("🔴 URGENT SOURCES:")
        for sid, data in urgent.items():
            lines.append(f"  Source: {data['source_name']} (id: {sid})")
            lines.append(f"  Files: {data.get('today_file_count', '?')}, Rows: {data.get('today_total_rows', '?'):,}")
            for inc in data["incidents"]:
                lines.append(f"    [{inc['severity'].upper()}] {inc['type']}: {inc['details']}")
            lines.append("")
    
    if attention:
        lines.append("🟡 ATTENTION SOURCES:")
        for sid, data in attention.items():
            lines.append(f"  Source: {data['source_name']} (id: {sid})")
            lines.append(f"  Files: {data.get('today_file_count', '?')}, Rows: {data.get('today_total_rows', '?'):,}")
            for inc in data["incidents"]:
                lines.append(f"    [{inc['severity'].upper()}] {inc['type']}: {inc['details']}")
            lines.append("")
    
    if ok:
        lines.append("🟢 OK SOURCES:")
        for sid, data in ok.items():
            lines.append(f"  {data['source_name']} (id: {sid}): "
                        f"{data.get('today_file_count', '?')} files, "
                        f"{data.get('today_total_rows', 0):,} rows — Normal")
    
    return "\n".join(lines)
