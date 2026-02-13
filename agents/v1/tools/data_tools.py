"""
Input Preparator Tools
======================
Funciones puras de Python (sin LLM) que procesan los datos de entrada.
En ADK, estas se registran como FunctionTool para que los agentes las invoquen.

¿Por qué no usar LLM aquí?
- Parsear JSON y markdown es determinístico (siempre da el mismo resultado)
- Es más rápido y barato que llamar al LLM
- Es más predecible y testeable
"""

import json
import os
import re
from datetime import datetime, timedelta
from typing import Optional
from dateutil import parser as date_parser


# =============================================================================
# PATHS - Rutas base del proyecto
# =============================================================================

BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
DATA_DIR = os.path.join(BASE_DIR, "data")
CVS_DIR = os.path.join(DATA_DIR, "datasource_cvs")
DAILY_DIR = os.path.join(DATA_DIR, "daily_files")


# =============================================================================
# TOOL 1: get_source_list
# Retorna la lista de todas las fuentes de datos disponibles
# =============================================================================

def get_source_list() -> dict:
    """
    Obtiene la lista de todas las fuentes de datos (sources) disponibles.
    Retorna un diccionario con source_id → nombre de la fuente.
    
    Esto le dice al agente: "Estas son las 18 fuentes que debes analizar"
    """
    sources = {}
    for filename in sorted(os.listdir(CVS_DIR)):
        if filename.endswith("_native.md"):
            source_id = filename.replace("_native.md", "")
            # Leer la primera línea del CV para obtener el nombre
            filepath = os.path.join(CVS_DIR, filename)
            with open(filepath, "r", encoding="utf-8") as f:
                first_line = f.readline().strip().lstrip("# ").strip()
            sources[source_id] = first_line
    return sources


# =============================================================================
# TOOL 2: parse_cv
# Parsea la hoja de vida de una fuente y extrae patrones clave
# =============================================================================

def parse_cv(source_id: str) -> dict:
    """
    Parsea el CV (hoja de vida) de una fuente de datos y extrae
    información estructurada sobre sus patrones normales.
    
    Args:
        source_id: ID de la fuente (ej: "195385")
    
    Returns:
        Diccionario con patrones extraídos del CV
    """
    filepath = os.path.join(CVS_DIR, f"{source_id}_native.md")
    if not os.path.exists(filepath):
        return {"error": f"CV not found for source {source_id}"}
    
    with open(filepath, "r", encoding="utf-8") as f:
        content = f.read()
    
    cv_data = {
        "source_id": source_id,
        "source_name": _extract_source_name(content),
        "file_patterns": _extract_file_stats_by_day(content),
        "upload_schedule": _extract_upload_schedule(content),
        "volume_stats": _extract_volume_stats(content),
        "day_of_week_summary": _extract_day_of_week_summary(content),
        "processing_status": _extract_processing_status(content),
        "recurring_patterns": _extract_section(content, "Recurring Patterns"),
        "analyst_comments": _extract_section(content, "Comments for the Analyst"),
        "raw_content": content  # El agente puede leer el CV completo si necesita más contexto
    }
    return cv_data


def _extract_source_name(content: str) -> str:
    """Extrae el nombre de la fuente de la primera línea."""
    first_line = content.split("\n")[0].strip().lstrip("# ").strip()
    return first_line


def _extract_file_stats_by_day(content: str) -> dict:
    """
    Extrae la tabla de 'File Processing Statistics by Day'.
    Retorna: {day: {mean, median, mode, stdev, min, max}}
    """
    stats = {}
    # Buscar la tabla de estadísticas de archivos por día
    pattern = r"\|\s*(Mon|Tue|Wed|Thu|Fri|Sat|Sun)\s*\|\s*(\d+)\s*\|\s*(\d+)\s*\|\s*(\d+)\s*\|\s*(\d+)\s*\|\s*(\d+)\s*\|\s*(\d+)\s*\|"
    matches = re.findall(pattern, content)
    
    for match in matches:
        day, mean, median, mode, stdev, min_val, max_val = match
        stats[day] = {
            "mean_files": int(mean),
            "median_files": int(median),
            "mode_files": int(mode),
            "stdev_files": int(stdev),
            "min_files": int(min_val),
            "max_files": int(max_val)
        }
    return stats


def _extract_upload_schedule(content: str) -> dict:
    """
    Extrae la tabla de 'Upload Schedule Patterns by Day'.
    Retorna: {day: {mean_hour, median_hour, mode_hour, stdev, window}}
    """
    schedule = {}
    # Buscar la tabla de horarios de upload
    pattern = r"\|\s*(Mon|Tue|Wed|Thu|Fri|Sat|Sun)\s*\|\s*(\d{1,2}:\d{2})\s*\|\s*(\d{1,2}:\d{2})\s*\|\s*(\d{1,2}:\d{2})\s*\|\s*([\d\s:hm]+)\s*\|\s*([\d:–\-\sUTC]+)\s*\|"
    matches = re.findall(pattern, content)
    
    for match in matches:
        day = match[0]
        schedule[day] = {
            "mean_hour_utc": match[1],
            "median_hour_utc": match[2],
            "mode_hour_utc": match[3],
            "stdev": match[4].strip(),
            "expected_window": match[5].strip()
        }
    return schedule


def _extract_volume_stats(content: str) -> dict:
    """Extrae estadísticas de volumen generales."""
    stats = {}
    
    patterns = {
        "mean": r"Mean:\s*([\d,.]+)",
        "median": r"Median:\s*([\d,.]+)",
        "stdev": r"Stdev:\s*([\d,.]+)",
        "min": r"Min:\s*([\d,.]+)",
        "max": r"Max:\s*([\d,.]+)",
        "empty_files": r"Empty files:\s*(\d+)",
        "normal_95_interval": r"Normal \(95%\) interval:\s*([\d,.]+ - [\d,.]+)",
    }
    
    # Buscar solo en la sección de Volume Characteristics
    volume_section = _extract_section(content, "Volume Characteristics")
    search_text = volume_section if volume_section else content
    
    for key, pattern in patterns.items():
        match = re.search(pattern, search_text)
        if match:
            stats[key] = match.group(1).replace(",", "")
    
    return stats


def _extract_day_of_week_summary(content: str) -> dict:
    """
    Extrae la tabla de Day-of-Week Summary con estadísticas de rows y empty files.
    Esta es la tabla más importante para los detectores.
    """
    summary = {}
    
    # Buscar patrón de la tabla Core Reference
    # Formato: | Day | Row Statistics | Empty Files Analysis | Processing Notes |
    day_pattern = r"\|\s*(Mon|Tue|Wed|Thu|Fri|Sat|Sun)\s*\|"
    
    # Encontrar todas las filas de la tabla
    lines = content.split("\n")
    in_core_reference = False
    
    for line in lines:
        if "Core Reference" in line or "Day-of-Week Summary" in line:
            in_core_reference = True
            continue
        
        if in_core_reference and re.match(day_pattern, line.strip()):
            day_match = re.match(r"\|\s*(Mon|Tue|Wed|Thu|Fri|Sat|Sun)\s*\|(.+)", line.strip())
            if day_match:
                day = day_match.group(1)
                rest = day_match.group(2)
                
                # Extraer Min, Max, Mean, Median de Row Statistics
                row_stats = {}
                for stat in ["Min", "Max", "Mean", "Median"]:
                    match = re.search(rf"{stat}:\s*([\d,.]+)", rest)
                    if match:
                        row_stats[stat.lower()] = float(match.group(1).replace(",", ""))
                
                # Extraer Empty Files Mean y Mode
                empty_stats = {}
                # El segundo bloque de estadísticas es para empty files
                empty_section = rest.split("|")
                if len(empty_section) > 1:
                    empty_text = empty_section[1] if len(empty_section) > 2 else ""
                    empty_mean_match = re.search(r"Mean:\s*([\d.]+)", empty_text)
                    empty_mode_match = re.search(r"Mode:\s*(\d+)", empty_text)
                    if empty_mean_match:
                        empty_stats["mean"] = float(empty_mean_match.group(1))
                    if empty_mode_match:
                        empty_stats["mode"] = int(empty_mode_match.group(1))
                
                summary[day] = {
                    "row_stats": row_stats,
                    "empty_files": empty_stats
                }
        
        # Stop at next section
        if in_core_reference and line.strip().startswith("## ") and "Day-of-Week" not in line:
            in_core_reference = False
    
    return summary


def _extract_processing_status(content: str) -> dict:
    """Extrae el resumen de procesamiento (% processed, failed, empty, etc.)"""
    status = {}
    patterns = {
        "processed": r"Successfully processed:\s*([\d.]+)%\s*\((\d+)\s*files?\)",
        "empty": r"Empty files?:\s*([\d.]+)%\s*\((\d+)\s*files?\)",
        "failed": r"Failed processing:\s*([\d.]+)%\s*\((\d+)\s*files?\)",
        "stopped": r"Stopped processing:\s*([\d.]+)%\s*\((\d+)\s*files?\)",
        "duplicated": r"Duplicate files?:\s*([\d.]+)%\s*\((\d+)\s*files?\)",
    }
    
    for key, pattern in patterns.items():
        match = re.search(pattern, content)
        if match:
            status[key] = {
                "percentage": float(match.group(1)),
                "count": int(match.group(2))
            }
    
    return status


def _extract_section(content: str, section_name: str) -> str:
    """Extrae el texto de una sección específica del CV."""
    pattern = rf"##\s*\**\d*\.?\s*{re.escape(section_name)}.*?\**\s*\n(.*?)(?=\n##|\Z)"
    match = re.search(pattern, content, re.DOTALL)
    if match:
        return match.group(1).strip()
    return ""


# =============================================================================
# TOOL 3: load_today_files
# Carga y filtra los archivos del día de ejecución
# =============================================================================

def load_today_files(source_id: str, execution_date: str) -> dict:
    """
    Carga los archivos de una fuente y filtra solo los del día de ejecución.
    
    Args:
        source_id: ID de la fuente (ej: "195385")
        execution_date: Fecha de ejecución en formato "YYYY-MM-DD" (ej: "2025-09-08")
    
    Returns:
        Diccionario con archivos de hoy y metadatos
    """
    folder = os.path.join(DAILY_DIR, f"{execution_date}_20_00_UTC")
    files_path = os.path.join(folder, "files.json")
    
    if not os.path.exists(files_path):
        return {"error": f"No data found for date {execution_date}"}
    
    with open(files_path, "r", encoding="utf-8") as f:
        all_data = json.load(f)
    
    if source_id not in all_data:
        return {"error": f"Source {source_id} not found in files.json for {execution_date}"}
    
    all_files = all_data[source_id]
    
    # Filtrar archivos cuyo uploaded_at corresponde al día de ejecución
    today_files = []
    other_files = []
    
    for file_entry in all_files:
        uploaded_at = file_entry.get("uploaded_at", "")
        if uploaded_at:
            try:
                upload_date = date_parser.parse(uploaded_at).date()
                exec_date = datetime.strptime(execution_date, "%Y-%m-%d").date()
                
                if upload_date == exec_date:
                    today_files.append(file_entry)
                else:
                    other_files.append(file_entry)
            except (ValueError, TypeError):
                other_files.append(file_entry)
    
    # Calcular métricas resumen
    total_rows_today = sum(f.get("rows", 0) for f in today_files)
    empty_today = sum(1 for f in today_files if f.get("rows", 0) == 0)
    duplicated_today = sum(1 for f in today_files if f.get("is_duplicated", False))
    failed_today = sum(1 for f in today_files if f.get("status") in ("failure", "stopped"))
    
    return {
        "source_id": source_id,
        "execution_date": execution_date,
        "day_of_week": datetime.strptime(execution_date, "%Y-%m-%d").strftime("%a"),
        "today_files": today_files,
        "today_file_count": len(today_files),
        "today_total_rows": total_rows_today,
        "today_empty_count": empty_today,
        "today_duplicated_count": duplicated_today,
        "today_failed_count": failed_today,
        "historical_files": other_files[:20],  # últimos 20 para contexto
        "total_files_in_dataset": len(all_files)
    }


# =============================================================================
# TOOL 4: load_last_weekday_files
# Carga los archivos del mismo día de la semana anterior
# =============================================================================

def load_last_weekday_files(source_id: str, execution_date: str) -> dict:
    """
    Carga los archivos del mismo día de la semana anterior para comparación.
    
    Args:
        source_id: ID de la fuente
        execution_date: Fecha de ejecución en formato "YYYY-MM-DD"
    
    Returns:
        Diccionario con archivos de la semana pasada
    """
    folder = os.path.join(DAILY_DIR, f"{execution_date}_20_00_UTC")
    lw_path = os.path.join(folder, "files_last_weekday.json")
    
    if not os.path.exists(lw_path):
        return {"error": f"No last weekday data for {execution_date}"}
    
    with open(lw_path, "r", encoding="utf-8") as f:
        lw_data = json.load(f)
    
    if source_id not in lw_data:
        return {
            "source_id": source_id,
            "last_weekday_files": [],
            "last_weekday_file_count": 0,
            "last_weekday_total_rows": 0,
            "note": f"Source {source_id} had no files on the same weekday last week"
        }
    
    files = lw_data[source_id]
    total_rows = sum(f.get("rows", 0) for f in files)
    
    return {
        "source_id": source_id,
        "last_weekday_files": files,
        "last_weekday_file_count": len(files),
        "last_weekday_total_rows": total_rows,
        "last_weekday_empty_count": sum(1 for f in files if f.get("rows", 0) == 0),
    }


# =============================================================================
# TOOL 5: get_available_dates
# Retorna las fechas disponibles para análisis
# =============================================================================

def get_available_dates() -> list:
    """Retorna las fechas de ejecución disponibles en el dataset."""
    dates = []
    if os.path.exists(DAILY_DIR):
        for folder in sorted(os.listdir(DAILY_DIR)):
            if folder.startswith("2025-"):
                date_str = folder.split("_")[0]
                day_name = datetime.strptime(date_str, "%Y-%m-%d").strftime("%A")
                dates.append({"date": date_str, "day": day_name})
    return dates


# =============================================================================
# TOOL 6: get_cv_summary_for_detector
# Genera un resumen compacto del CV optimizado para un detector específico
# =============================================================================

def get_cv_summary_for_detector(source_id: str, execution_date: str) -> str:
    """
    Genera un resumen compacto del CV de una fuente, contextualizado
    para el día de la semana de la fecha de ejecución.
    
    Esto es lo que cada detector recibe como contexto sobre "qué es normal".
    """
    cv = parse_cv(source_id)
    if "error" in cv:
        return json.dumps(cv)
    
    exec_dt = datetime.strptime(execution_date, "%Y-%m-%d")
    day_abbr = exec_dt.strftime("%a")  # Mon, Tue, etc.
    day_full = exec_dt.strftime("%A")  # Monday, Tuesday, etc.
    
    # Obtener estadísticas del día específico
    file_stats = cv["file_patterns"].get(day_abbr, {})
    schedule = cv["upload_schedule"].get(day_abbr, {})
    dow_summary = cv["day_of_week_summary"].get(day_abbr, {})
    
    summary = f"""
=== CV Summary for {cv['source_name']} (ID: {source_id}) ===
Day of analysis: {day_full} ({day_abbr})

FILE EXPECTATIONS FOR {day_abbr.upper()}:
- Expected files: mean={file_stats.get('mean_files', 'N/A')}, median={file_stats.get('median_files', 'N/A')}, mode={file_stats.get('mode_files', 'N/A')}
- Range: min={file_stats.get('min_files', 'N/A')}, max={file_stats.get('max_files', 'N/A')}, stdev={file_stats.get('stdev_files', 'N/A')}

UPLOAD SCHEDULE FOR {day_abbr.upper()}:
- Expected hour (UTC): mean={schedule.get('mean_hour_utc', 'N/A')}, median={schedule.get('median_hour_utc', 'N/A')}
- Expected window: {schedule.get('expected_window', 'N/A')}
- StdDev: {schedule.get('stdev', 'N/A')}

VOLUME STATS FOR {day_abbr.upper()}:
- Rows: min={dow_summary.get('row_stats', {}).get('min', 'N/A')}, max={dow_summary.get('row_stats', {}).get('max', 'N/A')}
- Rows: mean={dow_summary.get('row_stats', {}).get('mean', 'N/A')}, median={dow_summary.get('row_stats', {}).get('median', 'N/A')}
- Empty files: mean={dow_summary.get('empty_files', {}).get('mean', 'N/A')}, mode={dow_summary.get('empty_files', {}).get('mode', 'N/A')}

OVERALL PROCESSING STATUS:
{json.dumps(cv.get('processing_status', {}), indent=2)}

RECURRING PATTERNS:
{cv.get('recurring_patterns', 'N/A')[:1000]}

ANALYST COMMENTS:
{cv.get('analyst_comments', 'N/A')[:1000]}
"""
    return summary.strip()
