# Registro de experimentos

Cada idea se registra ANTES de consultar validación o bóvedas. Metas y puertas: `docs/TARGETS.md`. Particiones: `src/lab/splits.py`.

Presupuesto global: ≤ 200 variantes evaluadas en val. Cada exploración en train se anota (cuántas miradas se dieron).

## Hipótesis a priori (registradas el 2026-11-20, antes de ver datos)

### EXP-001: capitulación por liquidaciones, reversión
- Mecanismo: una cascada de liquidaciones empuja el precio más allá del valor justo con volumen forzado y un desplome del open interest; quien aporta liquidez después cobra el rebote.
- Señal (5m, solo información cerrada en t): retorno de la barra ≤ −k·σ, volumen z ≥ v, desbalance taker ≤ −0,3, caída de OI ≥ d en 15 min. Entrada en t+1, salida a H barras o stop.
- Rejilla: k ∈ {2, 3, 4}, v ∈ {2, 3, 5}, d ∈ {0%, 0,5%, 1%}, H ∈ {3, 6, 12} → 81 variantes. Versión espejo (cortos tras pump) registrada como EXP-001b, otras 81.
- Éxito: puertas de `TARGETS.md`.

### EXP-002: flujo agresor + open interest, continuidad vs. reversión
- Mecanismo: desbalance agresor con OI creciente = posiciones nuevas con convicción (continuidad); con OI cayendo = cierres forzados (reversión).
- Rejilla: umbral de desbalance ∈ {0,2, 0,35, 0,5}, ventana ∈ {3, 6} barras, cambio de OI ∈ {+0,5%, +1%} / {−0,5%, −1%}, H ∈ {3, 6, 12} → 72 variantes.

### EXP-003: rezago BTC/ETH → altcoins (lead-lag)
- Mecanismo: las altcoins reaccionan con retraso a movimientos bruscos de BTC/ETH.
- Se registra como prueba de contraste: el edge bruto esperado es pequeño frente a 11 bps de costo, y se espera que falle. Rejilla: umbral de movimiento ∈ {0,3%, 0,5%, 0,8%}, rezago ∈ {1, 2} barras, H ∈ {1, 3} → 12 variantes.

### EXP-004: reversión cross-sectional dollar-neutral (línea base de literatura)
- Mecanismo: el exceso de retorno a 1h de una moneda frente a su universo líquido se revierte parcialmente.
- Rejilla: formación ∈ {6, 12, 24} barras, retención ∈ {12, 24, 48}, cuantil ∈ {10%, 20%} → 18 variantes.
- Sirve como piso: si una idea nuestra no supera claramente esta, no aporta.


### EXP-005: funding extremo, contrarian (a priori, registrada 2026-11-20 ANTES de ejecutar)
- Mecanismo: funding muy positivo = largos apalancados abarrotados que pagan por mantener posición; la posición se desarma con caídas bruscas (y quien está corto además cobra funding). Simétrico en negativo.
- Datos: funding horario nativo de Hyperliquid (2023-06 →) para monedas con par Binance (precio proxy 5m).
- Señal: media de funding de las últimas 8 h, comparada con su percentil rolling de 30 días **excluyendo la observación actual**. Contrarian: corto si ≥ percentil p, largo si ≤ 1−p. Una posición por moneda a la vez. Entrada en la apertura de la barra 5m siguiente.
- Rejilla: p ∈ {90%, 95%, 99%}, H ∈ {8 h, 24 h}, filtro de liquidez adv24 ≥ $5M → 6 variantes. El PnL incluye el funding cobrado/pagado durante la retención.
- Éxito: puertas de TARGETS.md.


### EXP-006: atlas de excursiones y salida por cuantil (a priori, registrada 2026-11-20 antes de ejecutar)
- Idea del dueño: medir para cada moneda hasta dónde llega el precio a favor (MFE) y en contra (MAE) en 30/60 min y salir en el punto que casi siempre se alcanza.
- Hipótesis nula explícita: bajo entradas sin ventaja, una salida por cuantil **no crea expectativa** (cambia la tasa de acierto y el pago, no su producto). Se verifica con entradas incondicionales y con las mejores condiciones de EXP-001.
- Medición: cuantiles de MFE/MAE por moneda y por grupo de liquidez; simulación de políticas TP/SL/tiempo (TP ∈ {p50, p70}, SL ∈ {p50, p70} de MAE, tiempo 6/12 barras) con regla conservadora (si TP y SL caen en la misma barra, cuenta el SL). 8 variantes.

### EXP-007: modelo directo sobre los datos (a priori, registrada 2026-11-20 antes de ejecutar)
- Idea del dueño: no probar intuiciones, dejar que los datos digan qué condiciones preceden movimientos.
- Diseño: LightGBM de regresión (configuración única fija) sobre ~30 variables de precio, flujo, OI retrasado, volatilidad, hora y contexto BTC; objetivo = retorno futuro a H barras recortado a ±5σ. Walk-forward **solo dentro de train**: entrenar 12 meses, probar el trimestre siguiente (4 pliegues: 2024Q3 → 2025Q2). H ∈ {6, 12, 48}. Operar solo el 1% o el 5% de predicciones más extremas, lado = signo, costo 11 bps. 6 variantes.
- Éxito: neto > 0 con IC95 inferior > 0 en ≥ 3 de 4 pliegues, incluido el último; si no, descartada.

## Exploratorias
Todo hallazgo surgido de mirar train (incluidas observaciones heurísticas) debe registrarse aquí como EXP-1xx con su mecanismo **antes** de evaluarse en val.

## Resultados (train 2023-06 → 2025-06; val y bóvedas NO tocadas)

### Incidente de fuga (2026-11-20): detectado y corregido
La primera pasada mostró +30 bps netos (IC95 inferior +22) en EXP-001 corto-tras-pump y +22 bps en cuatro variantes de EXP-002. Todas dependían del cambio de OI. Prueba de alineación: el cambio de OI de una barra correlaciona 0,60 con el retorno de esa barra y **0,12 con el de la siguiente**: la instantánea de OI con sello T ya incluye precio posterior a T. Corrección: OI retrasado una barra completa (`features.py`, con prueba de regresión). Los resultados con OI sin retraso quedan **descartados**. Lección: un resultado "demasiado bueno" fue una fuga; el protocolo lo atrapó antes de abrir ninguna bóveda.

### EXP-001 (con OI corregido): descartada
- Corto tras pump: negativo (media −13 bps netos).
- Largo tras capitulación: 6 de 81 variantes con IC95 inferior > 0 y solo con k=4, v=5. Mejor: +31 bps netos pero **por año: 2023 +151, 2024 +48, 2025 −4**. Ventaja agotada: falla Puerta 1 (positivo en el tramo reciente). No pasa a val.

### EXP-002 (con OI corregido): descartada
0 de 72 variantes con media neta > 0. Ventaja bruta ≈ 0 en los cuatro cuadrantes.

### EXP-003: pendiente (se espera que falle).

### EXP-004: descartada
18 de 18 variantes negativas, todos los años. Ventaja bruta 0 a 3,5 bps frente a 11 bps de costo. Confirma que la reversión cross-sectional clásica no sobrevive costos en esta escala.

### Barrido estructural abierto (train, muestra 3%, 1,58 M barras líquidas, 33 pruebas feature×horizonte)
- Ninguna variable de precio/flujo/OI muestra ventaja bruta > 11 bps a 30-60 min. A 4 h la mayor es **hora del día**: perfil suave y continuo (+17 bps entrando a las 20 UTC; −10 bps largo entrando 10 UTC), media incondicional +0,7 bps (no es deriva).
- Falla de robustez: BTC/ETH/SOL ≈ 0 bps; vive en monedas pequeñas (86% de 320 con media positiva); por semestre +21 / +20 / +22 y luego **−4,5 en 2025H1**. Descartado como candidato (mismo patrón de decaimiento que EXP-001).
- **Hallazgo central:** en todas las familias probadas la ventaja existía en 2023-2024 y se agota en 2025. Lo relevante es el régimen reciente, y ahí las ventajas simples de precio/flujo en perpetuos líquidos no sobreviven a 11 bps.

### EXP-005 (funding extremo contrarian): descartada
6 variantes. El funding cobrado aporta +3 a +12 bps pero el precio va en contra (−9 a +11 bps según variante). Mejor: p=99%, H=8h, +5,8 bps netos con IC95 inferior −16 bps y signo distinto cada año (2023: −9, 2024: +11, 2025: +3). Sin evidencia de ventaja.

Variantes miradas en train hasta ahora: 162 + 72 + 18 + 33 + 6 = 291 (más 1 corrida con la fuga, descartada).
### EXP-006 (atlas de excursiones y salida por cuantil): sin ventaja, descartada como estrategia
- Atlas (2,1 M barras líquidas train, 491 monedas): las excursiones son **simétricas**. Moneda líquida, 30 min: subida máx p50/p70/p90 = 47/82/170 bps; caída máx = 49/85/170 bps. A 60 min: 66/116/243 vs 70/120/241. El mercado se mueve mucho pero igual en ambas direcciones.
- Prueba nula (entradas incondicionales, 8 variantes de TP/SL por cuantil): ventaja bruta −4,4 a +2,3 bps ≈ 0; neto −9 a −15 bps ≈ el costo. Una salida por cuantil cambia tasa de acierto y pago pero **no crea expectativa**; la ventaja tiene que venir de la entrada.
- Sobre eventos EXP-001 (dip k=4, v=5): mejor celda +11,7 bps brutos / +0,7 netos (ventana 60 min, TP p70, SL p50, ventanas ambiguas 50/50); con la regla conservadora −22 bps. Es 1 de 8 sobre una señal que ya se agotó en 2025. No pasa.
- Corrección de proceso: la primera ejecución tenía los percentiles del lado adverso invertidos y trataba toda ventana ambigua como stop; ambas cosas corregidas y re-ejecutadas antes de sacar conclusiones.

Variantes miradas en train: 291 + 8 = 299.
### EXP-007 (LightGBM directo, walk-forward dentro de train): no cumple el criterio, señal débil real
- 4 pliegues trimestrales (2024Q3 → 2025Q2), H ∈ {6, 12, 48}, top 1% y 5% de |predicción|, costo 11 bps.
- **IC de rango positivo en 12 de 12 pliegues** (+0,007 a +0,059; media 0,018 / 0,021 / 0,031 para H=6/12/48): hay estructura predecible, pequeña.
- Ventaja bruta del top 1%: 11,8 (H=6) / 15,1 (H=12) / 0,6 (H=48) bps. Neta tras 11 bps: +0,8 / +4,1 / −10,5. Pliegues con neto > 0: 2/3/2 de 4. **Pliegues con IC95 inferior > 0: 0/0/1 de 4** (la única celda es 2025Q2 H=48 top 1%, +33 bps, y no se repite en los otros pliegues). Criterio pre-registrado (≥ 3 de 4, incluido el último): NO cumplido.
- Variables más usadas: hora y día de la semana ≈ 41% de la ganancia total (estacionalidad, que ya mostró decaer en 2025), luego contexto BTC y retornos a 4-24 h.
- Lectura: la señal bruta (~12-15 bps en el 1% extremo, ~30 operaciones/día en todo el universo) es del tamaño del costo de tomar liquidez. El cuello de botella es el costo de ejecución, no la señal.

Variantes miradas en train: 299 + 6 = 305.

### EXP-008 — protocolo (a priori, registrado ANTES de ejecutar)
- Pregunta: ¿sobrevive la señal de EXP-007 si se entra con orden límite (maker) con un modelo de relleno que incluya la selección adversa, usando velas de **1 minuto** ya descargadas?
- Datos: las selecciones fuera de muestra top 1% de EXP-007 (`exp007_selections.parquet`), 4 pliegues de train; velas 1m de los shards crudos (Actions, 48 tareas). Val y bóvedas no se tocan.
- Reglas de relleno (conservadoras): orden límite en el precio de cierre de la barra de señal, vigente 5 min (5 velas 1m). Compra se llena solo si el mínimo de una vela 1m cae **por debajo** del límite en ≥ 1 bps (atraviesa, no solo toca); venta, simétrico. Sin relleno = sin operación (se cuenta la tasa de relleno y el retorno de las no llenadas).
- Salidas: (a) taker al cierre del horizonte H; (b) límite en el precio de cierre de la barra H−1, con respaldo taker tras 2 barras sin relleno.
- Costos: maker 1,5 bps + slippage 0; taker 4,5 + 1 bps. Variantes: 2 reglas de salida × H ∈ {6, 12} = 4 variantes.
- Éxito: neto por **señal** (no solo por operación llenada) > 0 con IC95 inferior > 0 en ≥ 3 de 4 pliegues. Se reporta explícitamente el retorno de las órdenes que no se llenaron: si las no llenadas ganan más que las llenadas, hay selección adversa y el resultado queda descartado.


**Estado de las bóvedas: A y B selladas, sin abrir. Validación (2025-07 → 2025-12): sin tocar. Ningún candidato ha pasado la Puerta 1.**

### EXP-008 (ejecución pasiva realista de las selecciones de EXP-007): descartada
- 22.744 señales reproducidas en 1 minuto (464 monedas, train). Validación del simulador: el retorno taker a 1 min coincide con el de 5 min de EXP-007 (corr 1,0000, diferencia mediana 0,00 bps).
- Tasa de relleno de la entrada pasiva: 92,9%. Salida pasiva (b) rellena 94,5%.
- Neto por señal (media de 4 pliegues), H=6 / H=12: taker 0,8 / 4,1; maker-in+taker-out 0,6 / 5,5; maker-in+maker-out 1,1 negativo / 5,7. **Pliegues con IC95 inferior > 0: 0 de 4 en todas las variantes.** Criterio NO cumplido.
- **Selección adversa medida:** retorno bruto P0→cierre de las señales NO llenadas = +68,8 bps (H=6) y +48,4 bps (H=12) frente a +8,1 y +12,7 de las llenadas. La orden límite pierde justo las señales que más ganan; el ahorro de comisión (~4 bps) se anula.
- Por año (neto por señal): 2024 +4 a +15 bps, 2025 −1 a −3 bps. Mismo decaimiento que EXP-001 y el ciclo por hora.

Variantes miradas en train: 305 + 4 = 309 (ocho familias de hipótesis). Ningún candidato pasa la Puerta 1. Bóvedas A y B selladas y sin abrir; validación 2025-07→12 sin tocar.

**Conclusión del bloque:** con velas públicas y flujo agresor de perpetuos líquidos, no hay ventaja neta de costos en el régimen reciente (2025+), ni a mercado ni con ejecución pasiva realista. Existe una señal predictiva débil (IC ≈ 0,02) del tamaño del costo de ejecución.
