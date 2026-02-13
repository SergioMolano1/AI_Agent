"""
Evaluation Pipeline
===================
Pipeline de evaluación que compara los reportes del agente contra 
el feedback de stakeholders (ground truth).

Uso:
    python evaluation/eval_pipeline.py --version v1
    python evaluation/eval_pipeline.py --version v2
    python evaluation/eval_pipeline.py --version v3
    python evaluation/eval_pipeline.py --compare v1 v3
    python evaluation/eval_pipeline.py --compare v2 v3

Métricas:
    - Precision: De lo que el agente reportó como incidencia, ¿cuánto era real?
    - Recall: De las incidencias reales, ¿cuántas detectó el agente?
    - F1-Score: Media armónica de Precision y Recall
    - Severity Accuracy: ¿Clasificó bien la severidad (🔴🟡🟢)?
    - Report Quality: Evaluación de calidad del texto (LLM-as-Judge)
"""

import json
import os
import re
import sys
from datetime import datetime

import openpyxl

# =============================================================================
# PATHS
# =============================================================================

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FEEDBACK_PATH = os.path.join(BASE_DIR, "data", "feedback", "Feedback_-_week_9_sept.xlsx")
RESULTS_DIR = os.path.join(BASE_DIR, "evaluation", "results")
GROUND_TRUTH_DIR = os.path.join(BASE_DIR, "evaluation", "ground_truth")


# =============================================================================
# PASO 1: Parsear el Feedback (Ground Truth)
# =============================================================================

def parse_feedback() -> dict:
    """
    Parsea el archivo de feedback de stakeholders y extrae las incidencias
    reales que fueron confirmadas como correctas.
    
    Returns:
        Diccionario por fecha con las incidencias y severidades reales
    """
    wb = openpyxl.load_workbook(FEEDBACK_PATH)
    ws = wb.active
    
    ground_truth = {}
    
    for row in ws.iter_rows(min_row=2, values_only=True):
        date_str = row[0]
        report_text = row[1] or ""
        feedback_text = row[2] or ""
        
        if not date_str or not report_text:
            continue
        
        # Parsear la fecha
        date_key = _normalize_date(date_str)
        if not date_key:
            continue
        
        # Extraer incidencias del reporte
        incidents = _extract_incidents_from_report(report_text)
        
        ground_truth[date_key] = {
            "date": date_key,
            "incidents": incidents,
            "feedback": feedback_text,
            "raw_report": report_text
        }
    
    return ground_truth


def _normalize_date(date_str: str) -> str:
    """Normaliza la fecha del feedback."""
    if not date_str:
        return None
    date_str = str(date_str).strip().lower()
    date_map = {
        "sept 8": "2025-09-08",
        "sept 9": "2025-09-09",
        "sept 10": "2025-09-10",
        "sept 11": "2025-09-11",
        "sept 12": "2025-09-12",
    }
    return date_map.get(date_str)


def _extract_incidents_from_report(report_text: str) -> list:
    """
    Extrae las incidencias del texto del reporte de feedback.
    Identifica qué fuentes tuvieron qué tipo de incidencia y severidad.
    """
    incidents = []
    
    # Determinar la sección actual (urgent, attention, ok)
    current_severity = None
    
    lines = report_text.replace("\\n", "\n").split("\n")
    
    for line in lines:
        line = line.strip()
        
        # Detectar secciones de severidad
        if "Urgent" in line or "urgent" in line or "Acción Inmediata" in line:
            current_severity = "urgent"
        elif "Needs Attention" in line or "Attention" in line or "Necesita" in line:
            current_severity = "attention"
        elif "No Action" in line or "No Problems" in line or "TODO BIEN" in line:
            current_severity = "ok"
        
        # Extraer source IDs mencionados
        source_ids = re.findall(r"id:\s*(\d{6})", line)
        
        for sid in source_ids:
            if current_severity and current_severity != "ok":
                # Determinar tipo de incidencia
                incident_type = _classify_incident_type(line)
                incidents.append({
                    "source_id": sid,
                    "severity": current_severity,
                    "type": incident_type,
                    "description": line[:200]
                })
            elif current_severity == "ok":
                incidents.append({
                    "source_id": sid,
                    "severity": "ok",
                    "type": "none",
                    "description": "No issues"
                })
    
    return incidents


def _classify_incident_type(text: str) -> str:
    """Clasifica el tipo de incidencia basado en el texto."""
    text_lower = text.lower()
    if "missing" in text_lower or "faltant" in text_lower or "not received" in text_lower or "no uploads" in text_lower:
        return "missing_file"
    elif "duplicate" in text_lower or "duplicad" in text_lower:
        return "duplicated_failed"
    elif "empty" in text_lower or "vacío" in text_lower or "0 records" in text_lower:
        return "unexpected_empty"
    elif "volume" in text_lower or "volumen" in text_lower or "rows" in text_lower:
        return "volume_variation"
    elif "late" in text_lower or "after schedule" in text_lower or "fuera de horario" in text_lower or "outside" in text_lower:
        return "late_upload"
    elif "previous" in text_lower or "backfill" in text_lower or "anterior" in text_lower:
        return "previous_period"
    else:
        return "other"


# =============================================================================
# PASO 2: Parsear el Output del Agente
# =============================================================================

def parse_agent_report(report_path: str) -> list:
    """
    Parsea un reporte generado por el agente y extrae las incidencias detectadas.
    """
    if not os.path.exists(report_path):
        return []
    
    with open(report_path, "r", encoding="utf-8") as f:
        report_text = f.read()
    
    return _extract_incidents_from_report(report_text)


# =============================================================================
# PASO 3: Calcular Métricas
# =============================================================================

def calculate_metrics(ground_truth_incidents: list, agent_incidents: list) -> dict:
    """
    Calcula métricas de evaluación comparando ground truth vs agente.
    
    Métricas:
    - Precision: TP / (TP + FP) — "De lo que reporté, ¿cuánto era real?"
    - Recall: TP / (TP + FN) — "De lo real, ¿cuánto detecté?"
    - F1-Score: 2 * (P * R) / (P + R)
    - Severity Accuracy: ¿Clasificó bien 🔴🟡🟢?
    """
    # Crear conjuntos de (source_id, severity) para comparación
    gt_set = set()
    for inc in ground_truth_incidents:
        if inc["severity"] != "ok":
            gt_set.add((inc["source_id"], inc["type"]))
    
    agent_set = set()
    for inc in agent_incidents:
        if inc["severity"] != "ok":
            agent_set.add((inc["source_id"], inc["type"]))
    
    # True Positives: incidencias que ambos detectaron
    tp = len(gt_set & agent_set)
    
    # False Positives: el agente reportó pero no es real
    fp = len(agent_set - gt_set)
    
    # False Negatives: es real pero el agente no lo detectó
    fn = len(gt_set - agent_set)
    
    # True Negatives: ambos dicen que está bien
    # (esto es más complejo de calcular en este contexto)
    
    precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
    recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0
    f1 = 2 * (precision * recall) / (precision + recall) if (precision + recall) > 0 else 0.0
    
    # Severity accuracy: para los TP, ¿la severidad coincide?
    severity_matches = 0
    severity_total = 0
    for inc_gt in ground_truth_incidents:
        for inc_ag in agent_incidents:
            if inc_gt["source_id"] == inc_ag["source_id"] and inc_gt["type"] == inc_ag["type"]:
                severity_total += 1
                if inc_gt["severity"] == inc_ag["severity"]:
                    severity_matches += 1
    
    severity_accuracy = severity_matches / severity_total if severity_total > 0 else 0.0
    
    return {
        "true_positives": tp,
        "false_positives": fp,
        "false_negatives": fn,
        "precision": round(precision, 4),
        "recall": round(recall, 4),
        "f1_score": round(f1, 4),
        "severity_accuracy": round(severity_accuracy, 4),
        "ground_truth_count": len(gt_set),
        "agent_detected_count": len(agent_set),
        "details": {
            "correctly_detected": list(gt_set & agent_set),
            "false_alarms": list(agent_set - gt_set),
            "missed": list(gt_set - agent_set),
        }
    }


# =============================================================================
# PASO 4: Evaluación LLM-as-Judge (Calidad del Reporte)
# =============================================================================

def get_llm_judge_prompt(report_text: str, feedback_text: str) -> str:
    """
    Genera el prompt para evaluar la calidad del reporte usando otro LLM.
    
    Esta técnica se llama "LLM-as-Judge": usamos un LLM para evaluar
    la calidad del output de otro LLM, basándonos en criterios específicos.
    """
    return f"""You are evaluating the quality of an automated incident report for a payment processing company.

STAKEHOLDER FEEDBACK ON PREVIOUS REPORTS:
{feedback_text}

REPORT TO EVALUATE:
{report_text}

Rate each criterion from 1-10 and provide brief justification:

1. CLARITY: Is the language clear and free of technical jargon?
   (Bad: "re-trigger ingestion pipeline" | Good: "Request the provider to resend the missing files")

2. DIRECTNESS: Does it lead with the key finding?
   (Bad: long technical explanation | Good: "Only 4 of 18 expected files received")

3. ACTIONABILITY: Are recommendations useful for a non-technical person?
   (Bad: "check SFTP drop location" | Good: "Contact the provider to verify file delivery")

4. COMPLETENESS: Does it include all necessary information?
   (Combines summary + detail, mentions affected sources and file counts)

5. SEVERITY_ACCURACY: Are the 🔴🟡🟢 classifications appropriate?
   (Urgent for critical issues, Attention for warnings, OK for normal)

Respond in JSON format:
{{
    "clarity": {{"score": N, "justification": "..."}},
    "directness": {{"score": N, "justification": "..."}},
    "actionability": {{"score": N, "justification": "..."}},
    "completeness": {{"score": N, "justification": "..."}},
    "severity_accuracy": {{"score": N, "justification": "..."}},
    "overall_score": N,
    "summary": "..."
}}
"""


# =============================================================================
# PASO 5: Ejecutar Evaluación Completa
# =============================================================================

def run_evaluation(version: str = "v1"):
    """
    Ejecuta la evaluación completa para una versión del agente.
    """
    print(f"\n{'='*70}")
    print(f"📊 Evaluación del Agente - Versión {version}")
    print(f"{'='*70}\n")
    
    # Parsear ground truth
    ground_truth = parse_feedback()
    print(f"✅ Ground truth parseado: {len(ground_truth)} días con feedback")
    
    # Guardar ground truth
    os.makedirs(GROUND_TRUTH_DIR, exist_ok=True)
    gt_path = os.path.join(GROUND_TRUTH_DIR, "parsed_feedback.json")
    with open(gt_path, "w", encoding="utf-8") as f:
        json.dump(ground_truth, f, indent=2, ensure_ascii=False)
    print(f"   Guardado en: {gt_path}")
    
    # Evaluar cada día
    all_metrics = {}
    output_dir = os.path.join(BASE_DIR, "outputs", version)
    
    for date_key, gt_data in ground_truth.items():
        report_path = os.path.join(output_dir, f"report_{date_key}.md")
        
        if not os.path.exists(report_path):
            print(f"\n⚠️  No se encontró reporte para {date_key} en {output_dir}")
            print(f"   Ejecuta primero: python main.py --date {date_key} --version {version}")
            continue
        
        print(f"\n--- Evaluando {date_key} ---")
        
        # Parsear reporte del agente
        agent_incidents = parse_agent_report(report_path)
        print(f"   Ground truth: {len([i for i in gt_data['incidents'] if i['severity'] != 'ok'])} incidencias")
        print(f"   Agente detectó: {len([i for i in agent_incidents if i['severity'] != 'ok'])} incidencias")
        
        # Calcular métricas
        metrics = calculate_metrics(gt_data["incidents"], agent_incidents)
        all_metrics[date_key] = metrics
        
        print(f"   Precision: {metrics['precision']:.2%}")
        print(f"   Recall: {metrics['recall']:.2%}")
        print(f"   F1-Score: {metrics['f1_score']:.2%}")
        print(f"   Severity Accuracy: {metrics['severity_accuracy']:.2%}")
    
    # Calcular métricas agregadas
    if all_metrics:
        avg_precision = sum(m["precision"] for m in all_metrics.values()) / len(all_metrics)
        avg_recall = sum(m["recall"] for m in all_metrics.values()) / len(all_metrics)
        avg_f1 = sum(m["f1_score"] for m in all_metrics.values()) / len(all_metrics)
        
        summary = {
            "version": version,
            "evaluated_dates": list(all_metrics.keys()),
            "per_date_metrics": all_metrics,
            "aggregate": {
                "avg_precision": round(avg_precision, 4),
                "avg_recall": round(avg_recall, 4),
                "avg_f1_score": round(avg_f1, 4),
            }
        }
        
        # Guardar resultados
        os.makedirs(RESULTS_DIR, exist_ok=True)
        results_path = os.path.join(RESULTS_DIR, f"{version}_results.json")
        with open(results_path, "w", encoding="utf-8") as f:
            json.dump(summary, f, indent=2, ensure_ascii=False)
        
        print(f"\n{'='*70}")
        print(f"📈 RESUMEN - Versión {version}")
        print(f"{'='*70}")
        print(f"   Precision promedio: {avg_precision:.2%}")
        print(f"   Recall promedio:    {avg_recall:.2%}")
        print(f"   F1-Score promedio:  {avg_f1:.2%}")
        print(f"\n   Resultados guardados en: {results_path}")
    
    return all_metrics


def compare_versions(v1: str = "v1", v2: str = "v2"):
    """Compara métricas entre dos versiones del agente."""
    r1_path = os.path.join(RESULTS_DIR, f"{v1}_results.json")
    r2_path = os.path.join(RESULTS_DIR, f"{v2}_results.json")
    
    if not os.path.exists(r1_path) or not os.path.exists(r2_path):
        print("❌ Necesitas ejecutar la evaluación de ambas versiones primero.")
        return
    
    with open(r1_path) as f:
        r1 = json.load(f)
    with open(r2_path) as f:
        r2 = json.load(f)
    
    print(f"\n{'='*70}")
    print(f"📊 Comparación: {v1} vs {v2}")
    print(f"{'='*70}")
    
    metrics = ["avg_precision", "avg_recall", "avg_f1_score"]
    for m in metrics:
        val1 = r1["aggregate"][m]
        val2 = r2["aggregate"][m]
        diff = val2 - val1
        arrow = "📈" if diff > 0 else "📉" if diff < 0 else "➡️"
        print(f"   {m}: {val1:.2%} → {val2:.2%} ({arrow} {diff:+.2%})")


# =============================================================================
# CLI
# =============================================================================

if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Pipeline de Evaluación")
    parser.add_argument("--version", type=str, default="v1", help="Versión a evaluar")
    parser.add_argument("--compare", nargs=2, help="Comparar dos versiones: --compare v1 v2")
    parser.add_argument("--parse-feedback", action="store_true", help="Solo parsear el feedback")
    
    args = parser.parse_args()
    
    if args.parse_feedback:
        gt = parse_feedback()
        print(json.dumps(gt, indent=2, ensure_ascii=False))
    elif args.compare:
        compare_versions(args.compare[0], args.compare[1])
    else:
        run_evaluation(args.version)
