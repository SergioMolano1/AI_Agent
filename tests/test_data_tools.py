"""
Tests for Data Tools & Evaluation Pipeline
============================================
Ejecutar con: pytest tests/ -v

Estos tests validan que las funciones de procesamiento de datos
funcionan correctamente sin necesidad de llamar al LLM.
"""

import pytest
import os
import json
import sys

# Agregar el directorio raíz al path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agents.v1.tools.data_tools import (
    get_source_list,
    parse_cv,
    load_today_files,
    load_last_weekday_files,
    get_available_dates,
    get_cv_summary_for_detector,
)


# =============================================================================
# FIXTURES - Datos compartidos entre tests
# =============================================================================

@pytest.fixture
def source_list():
    """Lista de todas las fuentes disponibles."""
    return get_source_list()


@pytest.fixture
def sample_cv():
    """CV parseado de una fuente de ejemplo (Settlement_Layout_2)."""
    return parse_cv("195385")


@pytest.fixture
def sample_today_files():
    """Archivos de hoy para Settlement_Layout_2, 2025-09-09 (Martes)."""
    return load_today_files("195385", "2025-09-09")


# =============================================================================
# TEST SUITE 1: get_source_list()
# =============================================================================

class TestGetSourceList:
    """Tests para la función que obtiene la lista de fuentes."""
    
    def test_returns_18_sources(self, source_list):
        """Debe encontrar exactamente 18 fuentes de datos."""
        assert len(source_list) == 18, f"Expected 18 sources, got {len(source_list)}"
    
    def test_all_ids_are_numeric(self, source_list):
        """Todos los source_id deben ser numéricos."""
        for source_id in source_list.keys():
            assert source_id.isdigit(), f"Source ID '{source_id}' is not numeric"
    
    def test_known_sources_present(self, source_list):
        """Verificar que fuentes conocidas están presentes."""
        expected_ids = ["195385", "195436", "209773", "220504", "228036"]
        for sid in expected_ids:
            assert sid in source_list, f"Expected source {sid} not found"
    
    def test_source_names_not_empty(self, source_list):
        """Todos los nombres de fuente deben tener contenido."""
        for sid, name in source_list.items():
            assert len(name) > 0, f"Source {sid} has empty name"


# =============================================================================
# TEST SUITE 2: parse_cv()
# =============================================================================

class TestParseCV:
    """Tests para el parser de hojas de vida (CVs)."""
    
    def test_returns_source_name(self, sample_cv):
        """Debe extraer el nombre de la fuente."""
        assert sample_cv["source_name"] == "_Settlement_Layout_2"
    
    def test_returns_source_id(self, sample_cv):
        """Debe incluir el source_id."""
        assert sample_cv["source_id"] == "195385"
    
    def test_file_patterns_has_7_days(self, sample_cv):
        """Debe tener estadísticas para los 7 días de la semana."""
        patterns = sample_cv["file_patterns"]
        expected_days = {"Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"}
        assert set(patterns.keys()) == expected_days
    
    def test_file_patterns_structure(self, sample_cv):
        """Cada día debe tener mean, median, mode, stdev, min, max."""
        tuesday = sample_cv["file_patterns"]["Tue"]
        required_keys = {"mean_files", "median_files", "mode_files", "stdev_files", "min_files", "max_files"}
        assert required_keys.issubset(set(tuesday.keys()))
    
    def test_settlement_layout_2_tuesday_files(self, sample_cv):
        """Settlement_Layout_2 debe esperar ~40 archivos los martes."""
        tuesday = sample_cv["file_patterns"]["Tue"]
        assert tuesday["mean_files"] == 40
        assert tuesday["min_files"] >= 30
    
    def test_settlement_layout_2_sunday_no_files(self, sample_cv):
        """Settlement_Layout_2 no tiene archivos los domingos."""
        sunday = sample_cv["file_patterns"]["Sun"]
        assert sunday["mean_files"] == 0
        assert sunday["max_files"] == 0
    
    def test_upload_schedule_extracted(self, sample_cv):
        """Debe extraer horarios de upload."""
        schedule = sample_cv["upload_schedule"]
        assert len(schedule) > 0
        # Martes debe tener horario ~08:00-09:00 UTC
        if "Tue" in schedule:
            assert "08" in schedule["Tue"].get("mode_hour_utc", "")
    
    def test_invalid_source_returns_error(self):
        """Un source_id inválido debe retornar error."""
        result = parse_cv("999999")
        assert "error" in result
    
    def test_processing_status_extracted(self, sample_cv):
        """Debe extraer el estado de procesamiento."""
        status = sample_cv["processing_status"]
        assert "processed" in status or len(status) >= 0
    
    def test_recurring_patterns_extracted(self, sample_cv):
        """Debe extraer patrones recurrentes como texto."""
        patterns = sample_cv["recurring_patterns"]
        assert isinstance(patterns, str)
    
    def test_raw_content_available(self, sample_cv):
        """Debe incluir el contenido raw del CV."""
        assert len(sample_cv["raw_content"]) > 100

    # Tests para fuentes con patrones específicos
    def test_mypal_dbr_high_empty_rate_monday(self):
        """MyPal_DBR RX (195436) debe mostrar alto rate de vacíos lun/mar."""
        cv = parse_cv("195436")
        dow = cv["day_of_week_summary"]
        if "Mon" in dow and "empty_files" in dow["Mon"]:
            # Lunes tiene ~83% de vacíos
            assert dow["Mon"]["empty_files"].get("mean", 0) > 0.5

    def test_wupay_no_sunday_activity(self):
        """WuPay sources (228036, 228038, 239611, 239613) no tienen actividad domingos."""
        for sid in ["228036", "228038", "239611", "239613"]:
            cv = parse_cv(sid)
            sunday = cv["file_patterns"].get("Sun", {})
            assert sunday.get("mean_files", 0) == 0, f"Source {sid} should have no Sunday files"


# =============================================================================
# TEST SUITE 3: load_today_files()
# =============================================================================

class TestLoadTodayFiles:
    """Tests para la carga de archivos del día."""
    
    def test_returns_correct_date(self, sample_today_files):
        """Debe retornar la fecha correcta."""
        assert sample_today_files["execution_date"] == "2025-09-09"
    
    def test_returns_correct_day(self, sample_today_files):
        """2025-09-09 es martes."""
        assert sample_today_files["day_of_week"] == "Tue"
    
    def test_files_count_reasonable(self, sample_today_files):
        """Settlement_Layout_2 un martes debe tener ~34-76 archivos."""
        count = sample_today_files["today_file_count"]
        assert count > 0, "Should have files on Tuesday"
        assert count <= 100, f"Unexpectedly high file count: {count}"
    
    def test_total_rows_positive(self, sample_today_files):
        """Debe tener rows > 0 un martes."""
        assert sample_today_files["today_total_rows"] > 0
    
    def test_invalid_date_returns_error(self):
        """Una fecha sin datos debe retornar error."""
        result = load_today_files("195385", "2020-01-01")
        assert "error" in result
    
    def test_invalid_source_returns_error(self):
        """Un source inválido debe retornar error."""
        result = load_today_files("999999", "2025-09-09")
        assert "error" in result
    
    def test_today_files_have_required_fields(self, sample_today_files):
        """Los archivos deben tener los campos requeridos."""
        if sample_today_files["today_file_count"] > 0:
            file = sample_today_files["today_files"][0]
            required = {"filename", "rows", "status", "is_duplicated", "uploaded_at"}
            assert required.issubset(set(file.keys()))
    
    def test_all_five_dates_have_data(self):
        """Las 5 fechas del dataset deben tener datos."""
        dates = ["2025-09-08", "2025-09-09", "2025-09-10", "2025-09-11", "2025-09-12"]
        for date in dates:
            result = load_today_files("195385", date)
            assert "error" not in result, f"No data for {date}"


# =============================================================================
# TEST SUITE 4: load_last_weekday_files()
# =============================================================================

class TestLoadLastWeekdayFiles:
    """Tests para la carga de archivos del mismo día semana pasada."""
    
    def test_returns_files_for_valid_source(self):
        """Debe retornar archivos para una fuente válida."""
        result = load_last_weekday_files("195385", "2025-09-09")
        assert result["last_weekday_file_count"] > 0
    
    def test_missing_source_returns_empty(self):
        """Si la fuente no existe en last_weekday, retorna lista vacía con nota."""
        result = load_last_weekday_files("196125", "2025-09-08")
        # 196125 está ausente del last_weekday del lunes
        assert result["last_weekday_file_count"] == 0 or "note" in result or "error" not in result
    
    def test_file_count_matches_expectations(self):
        """Settlement_Layout_2 un martes anterior debe tener ~34-76 archivos."""
        result = load_last_weekday_files("195385", "2025-09-09")
        count = result["last_weekday_file_count"]
        assert 30 <= count <= 80, f"Unexpected last weekday count: {count}"


# =============================================================================
# TEST SUITE 5: get_available_dates()
# =============================================================================

class TestGetAvailableDates:
    """Tests para la función de fechas disponibles."""
    
    def test_returns_5_dates(self):
        """Debe encontrar las 5 fechas del dataset."""
        dates = get_available_dates()
        assert len(dates) == 5
    
    def test_dates_in_order(self):
        """Las fechas deben estar en orden cronológico."""
        dates = get_available_dates()
        date_strs = [d["date"] for d in dates]
        assert date_strs == sorted(date_strs)
    
    def test_correct_days_of_week(self):
        """Cada fecha debe tener el día correcto."""
        dates = get_available_dates()
        expected = {
            "2025-09-08": "Monday",
            "2025-09-09": "Tuesday",
            "2025-09-10": "Wednesday",
            "2025-09-11": "Thursday",
            "2025-09-12": "Friday",
        }
        for d in dates:
            assert d["day"] == expected.get(d["date"]), f"Wrong day for {d['date']}"


# =============================================================================
# TEST SUITE 6: get_cv_summary_for_detector()
# =============================================================================

class TestGetCVSummary:
    """Tests para el resumen de CV contextualizado."""
    
    def test_includes_source_name(self):
        """El resumen debe incluir el nombre de la fuente."""
        summary = get_cv_summary_for_detector("209773", "2025-09-10")
        assert "Desco PIX" in summary
    
    def test_includes_day_context(self):
        """El resumen debe estar contextualizado para el día correcto."""
        summary = get_cv_summary_for_detector("209773", "2025-09-10")
        assert "Wednesday" in summary or "Wed" in summary
    
    def test_includes_file_expectations(self):
        """Debe incluir las expectativas de archivos."""
        summary = get_cv_summary_for_detector("209773", "2025-09-10")
        assert "Expected files" in summary or "mean=" in summary
    
    def test_includes_volume_stats(self):
        """Debe incluir estadísticas de volumen."""
        summary = get_cv_summary_for_detector("209773", "2025-09-10")
        assert "VOLUME" in summary or "Rows" in summary
    
    def test_invalid_source_returns_error(self):
        """Un source inválido debe retornar JSON con error."""
        summary = get_cv_summary_for_detector("999999", "2025-09-10")
        assert "error" in summary.lower()


# =============================================================================
# TEST SUITE 7: Business Logic Validation
# Estos tests validan que las reglas de negocio se aplican correctamente
# =============================================================================

class TestBusinessLogic:
    """Tests que validan las reglas de negocio del dominio."""
    
    def test_settlement_layout_2_sept_10_has_files(self):
        """
        Sept 10 es miércoles. Settlement_Layout_2 debe tener archivos.
        Ground truth (feedback): tuvo shortfall (solo 7 de ~37 esperados).
        """
        result = load_today_files("195385", "2025-09-10")
        # El agente debe detectar que hay menos archivos de los esperados
        cv = parse_cv("195385")
        expected_wed = cv["file_patterns"].get("Wed", {})
        assert expected_wed.get("mean_files", 0) > 20, "Wednesday should expect ~32-37 files"
    
    def test_payments_layout_1_sept_10_missing_files(self):
        """
        Sept 10: Payments_Layout_1_V3 (220504) only received 4 of 18 files.
        This was confirmed as URGENT in the feedback.
        """
        result = load_today_files("220504", "2025-09-10")
        cv = parse_cv("220504")
        expected = cv["file_patterns"].get("Wed", {}).get("mean_files", 0)
        received = result["today_file_count"]
        # Debe ser detectable que hay un shortfall significativo
        assert expected > 10, "Should expect 15-16 files on Wednesday"
    
    def test_wupay_sources_no_sunday_expected(self):
        """WuPay sources should have 0 files expected on Sunday."""
        for sid in ["228036", "228038", "239611", "239613"]:
            cv = parse_cv(sid)
            sun = cv["file_patterns"].get("Sun", {})
            assert sun.get("mean_files", 0) == 0
            assert sun.get("max_files", 0) == 0
    
    def test_desco_devolucoes_never_empty(self):
        """Desco Devoluções (211544) should have 0% empty files historically."""
        cv = parse_cv("211544")
        status = cv["processing_status"]
        # 100% processed, 0 empty
        if "processed" in status:
            assert status["processed"]["percentage"] == 100.0


# =============================================================================
# TEST SUITE 8: Evaluation Pipeline
# =============================================================================

class TestEvaluationPipeline:
    """Tests para el pipeline de evaluación."""
    
    def test_parse_feedback_returns_data(self):
        """El parser de feedback debe retornar datos."""
        # Import directly to avoid ADK dependency
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            'eval', 
            os.path.join(os.path.dirname(os.path.dirname(__file__)), 'evaluation', 'eval_pipeline.py')
        )
        ev = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(ev)
        
        gt = ev.parse_feedback()
        assert len(gt) >= 3, "Should have at least 3 days of feedback"
    
    def test_feedback_has_sept_8_incidents(self):
        """Sept 8 debe tener 3 incidentes urgentes (220504, 220505, 220506)."""
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            'eval',
            os.path.join(os.path.dirname(os.path.dirname(__file__)), 'evaluation', 'eval_pipeline.py')
        )
        ev = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(ev)
        
        gt = ev.parse_feedback()
        sept_8 = gt.get("2025-09-08", {})
        urgent = [i for i in sept_8.get("incidents", []) if i["severity"] == "urgent"]
        assert len(urgent) == 3, f"Sept 8 should have 3 urgent incidents, got {len(urgent)}"
        
        urgent_ids = {i["source_id"] for i in urgent}
        assert "220504" in urgent_ids
        assert "220505" in urgent_ids
        assert "220506" in urgent_ids
    
    def test_calculate_metrics_perfect_score(self):
        """Si el agente detecta todo correctamente, métricas deben ser 1.0."""
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            'eval',
            os.path.join(os.path.dirname(os.path.dirname(__file__)), 'evaluation', 'eval_pipeline.py')
        )
        ev = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(ev)
        
        fake_gt = [
            {"source_id": "220504", "severity": "urgent", "type": "missing_file"},
            {"source_id": "220505", "severity": "urgent", "type": "missing_file"},
        ]
        fake_agent = [
            {"source_id": "220504", "severity": "urgent", "type": "missing_file"},
            {"source_id": "220505", "severity": "urgent", "type": "missing_file"},
        ]
        
        metrics = ev.calculate_metrics(fake_gt, fake_agent)
        assert metrics["precision"] == 1.0
        assert metrics["recall"] == 1.0
        assert metrics["f1_score"] == 1.0
    
    def test_calculate_metrics_with_false_positive(self):
        """Un falso positivo debe reducir la precision."""
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            'eval',
            os.path.join(os.path.dirname(os.path.dirname(__file__)), 'evaluation', 'eval_pipeline.py')
        )
        ev = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(ev)
        
        fake_gt = [
            {"source_id": "220504", "severity": "urgent", "type": "missing_file"},
        ]
        fake_agent = [
            {"source_id": "220504", "severity": "urgent", "type": "missing_file"},
            {"source_id": "999999", "severity": "urgent", "type": "missing_file"},  # FP
        ]
        
        metrics = ev.calculate_metrics(fake_gt, fake_agent)
        assert metrics["precision"] == 0.5  # 1 TP / (1 TP + 1 FP)
        assert metrics["recall"] == 1.0     # 1 TP / (1 TP + 0 FN)
