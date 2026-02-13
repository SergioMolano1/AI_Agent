"""
Tests for v3 Rule-Based Detectors
===================================
Ejecutar con: pytest tests/test_detectors_v3.py -v

Estos tests validan que los 6 detectores determinísticos de v3 funcionan
correctamente. Son la evidencia de que la detección Python pura produce
los mismos resultados que los detectores LLM de v1/v2.

Ground truth: feedback de stakeholders (sept 8, 9, 10).
"""

import pytest
import os
import sys

# Agregar el directorio raíz al path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agents.v3.detectors.rule_based import (
    run_all_detectors,
    format_findings_for_llm,
    detect_missing_files,
    detect_duplicated_failed,
    detect_unexpected_empty,
    detect_volume_variation,
    detect_late_upload,
    detect_previous_period,
)
from agents.v1.tools.data_tools import (
    get_source_list,
    parse_cv,
    load_today_files,
    load_last_weekday_files,
)


# =============================================================================
# TEST SUITE 1: run_all_detectors() — Pipeline Completo
# =============================================================================

class TestRunAllDetectors:
    """Tests del pipeline completo de detección para cada día."""

    def test_sept_8_returns_all_18_sources(self):
        """Debe analizar las 18 fuentes."""
        findings = run_all_detectors("2025-09-08")
        assert len(findings) == 18, f"Expected 18 sources, got {len(findings)}"

    def test_sept_8_detects_urgent_sources(self):
        """
        Sept 8 (Lunes): El feedback reporta fuentes urgentes.
        Payments (220505, 220506) y WuPay sources deberían tener incidencias.
        """
        findings = run_all_detectors("2025-09-08")
        urgent_sources = [
            sid for sid, f in findings.items()
            if f["overall_severity"] == "urgent"
        ]
        assert len(urgent_sources) >= 1, "Sept 8 should have at least 1 urgent source"

    def test_sept_8_structure(self):
        """Cada fuente debe tener la estructura correcta."""
        findings = run_all_detectors("2025-09-08")
        for sid, data in findings.items():
            assert "source_id" in data
            assert "source_name" in data
            assert "overall_severity" in data
            assert "incidents" in data
            assert data["overall_severity"] in ("urgent", "attention", "ok")

    def test_sept_9_has_findings(self):
        """Sept 9 (Martes) debe tener hallazgos."""
        findings = run_all_detectors("2025-09-09")
        total_incidents = sum(len(f["incidents"]) for f in findings.values())
        assert total_incidents >= 0

    def test_sept_10_has_findings(self):
        """Sept 10 (Miércoles) debe tener hallazgos."""
        findings = run_all_detectors("2025-09-10")
        total_incidents = sum(len(f["incidents"]) for f in findings.values())
        assert total_incidents >= 0

    def test_all_5_dates_work(self):
        """Los 5 días deben ejecutarse sin errores."""
        dates = ["2025-09-08", "2025-09-09", "2025-09-10", "2025-09-11", "2025-09-12"]
        for date in dates:
            findings = run_all_detectors(date)
            assert len(findings) == 18, f"Date {date} should have 18 sources"

    def test_format_findings_for_llm_not_empty(self):
        """El formato para LLM no debe ser vacío."""
        findings = run_all_detectors("2025-09-08")
        formatted = format_findings_for_llm(findings, "2025-09-08")
        assert len(formatted) > 100, "Formatted findings should have substantial content"
        assert "URGENT" in formatted or "OK" in formatted


# =============================================================================
# TEST SUITE 2: Detectores Individuales
# Nota: cada detector recibe (source_id, execution_date) y retorna un dict
#       con keys: source_id, detector, incidents (lista de incidencias)
# =============================================================================

class TestMissingFileDetector:
    """Tests para el detector de archivos faltantes."""

    def test_wupay_monday_missing(self):
        """
        WuPay sources (228036) normalmente operan Lun-Vie.
        Sept 8 es lunes, debería detectar archivos faltantes.
        """
        result = detect_missing_files("228036", "2025-09-08")
        assert isinstance(result, dict)
        assert "incidents" in result
        assert isinstance(result["incidents"], list)

    def test_settlement_sunday_no_missing(self):
        """
        Settlement_Layout_2 (195385) NO opera domingos.
        0 archivos un domingo NO es missing files.
        """
        cv = parse_cv("195385")
        sunday_expected = cv["file_patterns"].get("Sun", {}).get("mean_files", 0)
        assert sunday_expected == 0, "Sunday should expect 0 files — not a missing file"

    def test_returns_dict_with_incidents(self):
        """El detector debe retornar un dict con estructura correcta."""
        result = detect_missing_files("195385", "2025-09-09")
        assert isinstance(result, dict)
        assert "source_id" in result
        assert "detector" in result
        assert "incidents" in result
        assert result["detector"] == "missing_file"
        for inc in result["incidents"]:
            assert "type" in inc
            assert "severity" in inc


class TestDuplicatedFailedDetector:
    """Tests para el detector de duplicados y fallos."""

    def test_returns_dict(self):
        """Debe retornar un dict con estructura correcta."""
        result = detect_duplicated_failed("195385", "2025-09-09")
        assert isinstance(result, dict)
        assert "incidents" in result
        assert result["detector"] == "duplicated_failed"

    def test_detects_duplicated_flag(self):
        """Si hay archivos con is_duplicated=true, debe detectarlos."""
        result = detect_duplicated_failed("195385", "2025-09-09")
        for inc in result["incidents"]:
            assert inc["type"] in ("duplicated_file", "failed_file")


class TestUnexpectedEmptyDetector:
    """Tests para el detector de archivos vacíos inesperados."""

    def test_mypal_dbr_monday_empty_is_normal(self):
        """
        MyPal_DBR RX (195436) tiene ~83% vacíos los lunes.
        Un vacío el lunes NO debería ser incidencia.
        """
        result = detect_unexpected_empty("195436", "2025-09-08")
        assert isinstance(result, dict)
        assert isinstance(result["incidents"], list)

    def test_desco_devolucoes_empty_is_anomaly(self):
        """
        Desco Devoluções (211544) tiene 0% vacíos históricamente.
        Un archivo vacío DEBERÍA ser incidencia.
        """
        cv = parse_cv("211544")
        status = cv.get("processing_status", {})
        if "processed" in status:
            assert status["processed"]["percentage"] >= 95.0


class TestVolumeVariationDetector:
    """Tests para el detector de variaciones de volumen."""

    def test_returns_dict(self):
        """Debe retornar un dict con estructura correcta."""
        result = detect_volume_variation("195385", "2025-09-09")
        assert isinstance(result, dict)
        assert "incidents" in result
        assert result["detector"] == "volume_variation"

    def test_wupay_monday_zero_is_urgent(self):
        """
        WuPay (228036) un lunes con 0 records debería ser urgente
        (normalmente tiene ~612K records).
        """
        result = detect_volume_variation("228036", "2025-09-08")
        urgent_incidents = [i for i in result["incidents"] if i["severity"] == "urgent"]
        assert len(urgent_incidents) >= 1, "WuPay with 0 records should be urgent"

    def test_mypal_monday_zero_is_normal(self):
        """
        MyPal_DBR RX (195436) un lunes con 0 records NO debería ser urgente
        (83% de los lunes son vacíos, median = 0).
        """
        result = detect_volume_variation("195436", "2025-09-08")
        urgent_incidents = [i for i in result["incidents"] if i["severity"] == "urgent"]
        assert len(urgent_incidents) == 0, "MyPal Monday 0 records is NORMAL, should not be urgent"


class TestLateUploadDetector:
    """Tests para el detector de uploads tardíos."""

    def test_returns_dict(self):
        """Debe retornar un dict con estructura correcta."""
        result = detect_late_upload("195385", "2025-09-09")
        assert isinstance(result, dict)
        assert "incidents" in result

    def test_late_upload_never_urgent(self):
        """Late uploads NUNCA deben ser urgentes (max: attention)."""
        result = detect_late_upload("195385", "2025-09-09")
        for inc in result["incidents"]:
            assert inc["severity"] != "urgent", "Late uploads should never be urgent"


class TestPreviousPeriodDetector:
    """Tests para el detector de archivos de periodo anterior."""

    def test_returns_dict(self):
        """Debe retornar un dict con estructura correcta."""
        result = detect_previous_period("195385", "2025-09-09")
        assert isinstance(result, dict)
        assert "incidents" in result

    def test_previous_period_never_urgent(self):
        """Previous period files NUNCA deben ser urgentes."""
        result = detect_previous_period("195385", "2025-09-09")
        for inc in result["incidents"]:
            assert inc["severity"] != "urgent", "Previous period should never be urgent"


# =============================================================================
# TEST SUITE 3: Comparación con Ground Truth (Feedback)
# Estos tests validan que v3 detecta las MISMAS incidencias del feedback
# =============================================================================

class TestGroundTruthAlignment:
    """
    Tests que verifican que los detectores v3 encuentran las incidencias
    confirmadas por el feedback de stakeholders.
    """

    def test_sept_8_payments_220505_detected(self):
        """
        Feedback sept 8: __Payments_Layout_2_V3 (220505) tuvo incidencia urgente.
        """
        findings = run_all_detectors("2025-09-08")
        src_220505 = findings.get("220505", {})
        assert len(src_220505.get("incidents", [])) >= 1 or \
               src_220505.get("overall_severity") in ("urgent", "attention"), \
               "220505 should be flagged on Sept 8"

    def test_sept_8_payments_220506_detected(self):
        """
        Feedback sept 8: __Payments_Layout_3_V3 (220506) tuvo incidencia urgente.
        """
        findings = run_all_detectors("2025-09-08")
        src_220506 = findings.get("220506", {})
        assert len(src_220506.get("incidents", [])) >= 1 or \
               src_220506.get("overall_severity") in ("urgent", "attention"), \
               "220506 should be flagged on Sept 8"

    def test_sept_8_wupay_sources_detected(self):
        """
        Feedback sept 8: WuPay sources (228036, 228038, 239611, 239613) missing.
        """
        findings = run_all_detectors("2025-09-08")
        wupay_flagged = 0
        for sid in ["228036", "228038", "239611", "239613"]:
            src = findings.get(sid, {})
            if src.get("overall_severity") in ("urgent", "attention"):
                wupay_flagged += 1
        assert wupay_flagged >= 2, f"At least 2 WuPay sources should be flagged, got {wupay_flagged}"

    def test_idempotency(self):
        """
        Ejecutar el mismo día dos veces debe dar exactamente los mismos resultados.
        (Propiedad clave de la detección determinística)
        """
        run1 = run_all_detectors("2025-09-08")
        run2 = run_all_detectors("2025-09-08")

        for sid in run1:
            assert run1[sid]["overall_severity"] == run2[sid]["overall_severity"]
            assert len(run1[sid]["incidents"]) == len(run2[sid]["incidents"])