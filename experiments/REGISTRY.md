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
**Estado de las bóvedas: A y B selladas, sin abrir. Validación (2025-07 → 2025-12): sin tocar. Ningún candidato ha pasado la Puerta 1.**
