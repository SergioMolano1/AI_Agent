# Retos, Decisiones de Diseño y Lecciones Aprendidas

## 1. Retos Enfrentados

### Reto 1: Heterogeneidad de las 18 fuentes de datos

**El problema:** Cada fuente tiene comportamiento completamente diferente. Lo que es normal para una fuente es una incidencia grave para otra.

Ejemplos concretos:
- **MyPal_DBR RX (195436)**: 30% de archivos vacíos es *normal* (especialmente lunes/martes)
- **Desco Devoluções (211544)**: 0% de archivos vacíos histórico — un solo vacío es una *anomalía*
- **WuPay sources**: No tienen actividad los domingos — 0 archivos es *esperado*
- **207936 Soop Tipo 2**: Archivos POS siempre vacíos — es un patrón *conocido*

**Decisión tomada:** En lugar de reglas genéricas, cada detector consulta el CV de la fuente para contextualizar qué es "normal" para ESA fuente en ESE día de la semana. Esto convierte al CV en la fuente de verdad.

**Alternativa descartada:** Usar umbrales globales (ej: "más de 5% vacíos = incidencia"). Esto habría generado muchos falsos positivos.

---

### Reto 2: Comparación temporal — ¿Contra qué comparamos?

**El problema:** El volumen de archivos varía significativamente según el día de la semana. Comparar un lunes contra un viernes no tiene sentido.

Ejemplo: Source 195385 (Settlement_Layout_2):
- Lunes: 6 archivos (todos vacíos) = NORMAL
- Martes: 40 archivos = NORMAL
- Si comparas martes vs lunes, parecería que el martes tiene una explosión de volumen

**Decisión tomada:** Comparar siempre contra el MISMO día de la semana anterior (lunes vs lunes anterior), usando `files_last_weekday.json`. Además, usar las estadísticas por día del CV como referencia primaria.

**Alternativa descartada:** Promedio móvil de los últimos 7 días. Esto suavizaría demasiado los patrones semanales.

---

### Reto 3: Balancear precisión vs recall

**El problema:** Si el agente es muy sensible, genera muchos falsos positivos (el equipo ignora las alertas). Si es poco sensible, se pierden incidencias reales (multas regulatorias).

**Decisión tomada:** Priorizar recall sobre precision — es preferible investigar un falso positivo que perder una incidencia real que puede costar $50K en multas. El umbral de volumen se estableció en mean ± 2*stdev para el detector de variación.

**Cómo lo medimos:** El pipeline de evaluación calcula ambas métricas contra el ground truth (feedback de stakeholders), permitiendo ajustar iterativamente entre versiones.

---

### Reto 4: Lenguaje del reporte — Técnico vs. Negocio

**El problema (identificado en el feedback):** La versión alpha usaba frases como "re-trigger ingestion", "check SFTP drop location", "ensure downstream deduplication" — el stakeholder no entiende esto.

Feedback textual del cliente:
> "expressions like 're-trigger ingestion' and 'check landing location' don't make sense to the client, as they don't have visibility into these processes"

**Decisión tomada en v2:** 
1. Lista explícita de "frases baneadas" en el prompt del consolidador
2. Ejemplos concretos de cómo reformular: "re-trigger ingestion" → "Contact the provider to resend the files"
3. Formato "summary + detail": empezar con "Only 4 of 18 files received" y luego listar detalles

**Lección aprendida:** El prompt engineering para el tono del reporte es tan importante como la detección técnica. Un agente que detecta todo pero comunica mal es igual de inútil que uno que no detecta nada.

---

### Reto 5: Orquestación de 8 agentes — Costo y latencia

**El problema:** 8 agentes (6 detectores + 1 consolidador + 1 orquestador) analizando 18 fuentes = muchas llamadas al LLM. Esto impacta tiempo de ejecución y costo de API.

**Decisión tomada:**
1. Las funciones de procesamiento de datos (parse_cv, load_files) son Python puro — NO usan LLM
2. Solo se usa el LLM para razonamiento (¿es incidencia?) y redacción (reporte final)
3. Se eligió `gemini-2.0-flash` en lugar de `gemini-2.0-pro` para optimizar velocidad y costo

**Trade-off aceptado:** Flash es menos "inteligente" que Pro, pero para detección basada en reglas claras + contexto del CV, es suficiente. Si en la evaluación se detecta que Flash no razona bien en casos edge, se podría subir a Pro solo para el consolidador.

---

### Reto 6: Cambios de régimen en las fuentes

**El problema:** Algunas fuentes cambiaron su comportamiento durante el periodo histórico:
- **220505/220506**: Horario de upload cambió de 14:06 UTC a 08:06 UTC en mayo 2025
- **195439**: Volumen cayó de 440K rows a 1,200 rows en mayo 2025
- **224603**: Horario cambió de 15:10 UTC a 12:15 UTC en julio 2025

**Decisión tomada:** Los CVs documentan estos cambios de régimen. Los detectores priorizan el patrón más reciente, pero el CV les da contexto sobre el cambio. Si el agente detecta algo que coincide con un cambio documentado, lo clasifica como "attention" no "urgent".

---

### Reto 7: Evaluación con ground truth limitado

**El problema:** Solo tenemos 3 días de feedback (sept 8, 9, 10) como ground truth. Para sept 11 y 12 no tenemos la "respuesta correcta" del stakeholder.

**Decisión tomada:**
1. Evaluación cuantitativa (precision/recall/F1) solo sobre los 3 días con feedback
2. Para sept 11 y 12, el agente genera reportes que se pueden revisar manualmente
3. LLM-as-Judge como complemento para evaluar la calidad del lenguaje del reporte

**Alternativa futura:** En producción, establecer un loop de feedback continuo donde el stakeholder valida cada reporte y eso alimenta la evaluación.

---

## 2. Decisiones de Diseño Clave

| Decisión | Razón | Alternativa descartada |
|----------|-------|----------------------|
| ADK multi-agent v1/v2 (no monolítico) | Cada detector es independiente, testeable, mejorable | Un solo agente gigante con un prompt de 5000 tokens |
| Híbrida v3 (Python + 1 LLM) | Rate limits reales en free tier, detección es determinística | Pagar plan Gemini para mantener multi-agente |
| Tools como Python puro | Determinismo, velocidad, testeable con pytest | Hacer que el LLM parsee JSON directamente |
| Gemini Flash (no Pro) | Costo/velocidad vs calidad suficiente | Gemini Pro ($$$) |
| CV como fuente de verdad | Cada fuente tiene reglas diferentes | Reglas hardcodeadas en el código |
| Versionamiento v1→v2→v3 | Demostrar mejora iterativa en prompts Y arquitectura | Una sola versión "perfecta" |
| MCP para notificaciones | Estándar, reutilizable, nativo en ADK | API call directa a Slack |

## 3. Lecciones Aprendidas

1. **El 80% del valor está en entender los datos, no en el LLM.** El análisis profundo de los 18 CVs fue lo que permitió definir qué es "normal" vs "incidencia". Sin eso, el LLM más inteligente del mundo generaría basura.

2. **Los prompts son código.** Deben versionarse, testearse y mejorarse iterativamente igual que cualquier otro artefacto de software. El cambio de v1 a v2 fue 90% mejora de prompts.

3. **Evaluar es tan importante como construir.** Sin el pipeline de evaluación, no tendríamos forma de saber si v2 es realmente mejor que v1. Las métricas (precision, recall, F1) dan evidencia objetiva.

4. **El feedback del usuario final es oro.** Las 3 líneas de feedback del stakeholder (especialmente "the action is still confuse") guiaron toda la mejora de v1 a v2. En producción, este loop de feedback debería ser continuo.

5. **Separar lógica determinística del LLM.** Las funciones de data processing (parse_cv, load_files) no necesitan inteligencia artificial — son transformaciones de datos predecibles. Esto hace el sistema más rápido, barato y testeable.

6. **No todo necesita LLM.** La evolución a v3 demostró que la detección de incidencias (contar archivos, comparar volúmenes, verificar timestamps) es fundamentalmente math, no lenguaje. Usar LLM para esto es como usar una Ferrari para ir al supermercado — funciona, pero es innecesariamente costoso. El LLM brilla donde SÍ aporta valor: redactar un reporte ejecutivo claro y accionable.

7. **Los rate limits son una restricción de diseño, no un bug.** En lugar de luchar contra el rate limit (retries, delays), la v3 lo resuelve desde la arquitectura. Esta es la diferencia entre un workaround y una solución elegante.
