"""
Main Entry Point
=================
Punto de entrada para ejecutar el agente de detección de incidencias.

Uso:
    # Ejecutar v3 (recomendado - funciona en free tier)
    python main.py --date 2025-09-08 --version v3
    
    # Ejecutar para todas las fechas disponibles
    python main.py --all --version v3
    
    # Ejecutar versiones anteriores (requiere plan pago de Gemini)
    python main.py --date 2025-09-08 --version v1
    python main.py --date 2025-09-08 --version v2

Versiones:
    v1: Multi-agente baseline (8 agentes LLM, ~20+ API calls)
    v2: Multi-agente con prompts mejorados (misma arquitectura, mejor lenguaje)
    v3: Híbrida optimizada (detección Python + 1 LLM call para reporte)
"""

import argparse
import asyncio
import os
import sys
from datetime import datetime

from dotenv import load_dotenv

# Cargar variables de entorno
load_dotenv()


def check_api_key():
    """Verifica que la API key esté configurada."""
    if not os.getenv("GOOGLE_API_KEY"):
        print("ERROR: GOOGLE_API_KEY no esta configurada.")
        print("   Crea un archivo .env con: GOOGLE_API_KEY=tu_api_key_aqui")
        print("   O ejecuta: export GOOGLE_API_KEY=tu_api_key_aqui")
        sys.exit(1)


async def run_for_date(execution_date: str, version: str = "v3"):
    """
    Ejecuta el agente para una fecha específica.
    
    Args:
        execution_date: Fecha en formato YYYY-MM-DD
        version: Versión del agente a usar (v1, v2, v3)
    """
    print(f"\n{'='*70}")
    print(f"  Ejecutando agente {version} para fecha: {execution_date}")
    print(f"   Dia: {datetime.strptime(execution_date, '%Y-%m-%d').strftime('%A')}")
    
    if version in ("v1", "v2"):
        print(f"   NOTA: {version} requiere plan pago de Gemini (~20+ API calls)")
    else:
        print(f"   v3 hibrida: deteccion Python + 1 LLM call")
    
    print(f"{'='*70}\n")
    
    # Importar la versión correcta del agente
    if version == "v1":
        from agents.v1.agent import run_agent
    elif version == "v2":
        from agents.v2.agent import run_agent
    elif version == "v3":
        from agents.v3.agent import run_agent
    else:
        print(f"Version {version} no reconocida. Usa v1, v2 o v3.")
        return
    
    # Ejecutar el agente
    try:
        report = await run_agent(execution_date)
        
        # Guardar el reporte
        output_dir = os.path.join("outputs", version)
        os.makedirs(output_dir, exist_ok=True)
        
        output_file = os.path.join(output_dir, f"report_{execution_date}.md")
        with open(output_file, "w", encoding="utf-8") as f:
            f.write(report)
        
        print(f"\n  Reporte guardado en: {output_file}")
        print(f"\n{'='*70}")
        print("REPORTE GENERADO:")
        print(f"{'='*70}")
        print(report)
        
    except Exception as e:
        print(f"Error ejecutando agente: {e}")
        raise


async def run_all(version: str = "v3"):
    """Ejecuta el agente para todas las fechas disponibles."""
    from agents.v1.tools.data_tools import get_available_dates
    
    dates = get_available_dates()
    if not dates:
        print("No se encontraron fechas disponibles en data/daily_files/")
        return
    
    print(f"Fechas disponibles: {len(dates)}")
    for d in dates:
        print(f"   - {d['date']} ({d['day']})")
    
    for d in dates:
        await run_for_date(d["date"], version)


def main():
    """Punto de entrada principal."""
    parser = argparse.ArgumentParser(
        description="Agente de Deteccion de Incidencias - Payment File Processing"
    )
    parser.add_argument(
        "--date", 
        type=str, 
        help="Fecha de ejecucion (YYYY-MM-DD). Ej: 2025-09-08"
    )
    parser.add_argument(
        "--all", 
        action="store_true", 
        help="Ejecutar para todas las fechas disponibles"
    )
    parser.add_argument(
        "--version", 
        type=str, 
        default="v3",
        choices=["v1", "v2", "v3"],
        help="Version del agente (default: v3). v1/v2=multi-agente, v3=hibrida"
    )
    
    args = parser.parse_args()
    
    # Verificar API key
    check_api_key()
    
    if args.all:
        asyncio.run(run_all(args.version))
    elif args.date:
        asyncio.run(run_for_date(args.date, args.version))
    else:
        print("No se especifico fecha. Usa --date YYYY-MM-DD o --all")
        print("")
        print("   Ejemplos:")
        print("   python main.py --date 2025-09-08 --version v3   (recomendado)")
        print("   python main.py --all --version v3                (todos los dias)")
        print("   python main.py --date 2025-09-08 --version v1   (multi-agente baseline)")
        print("   python main.py --date 2025-09-08 --version v2   (multi-agente mejorado)")


if __name__ == "__main__":
    main()
