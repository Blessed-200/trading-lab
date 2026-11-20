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

## Exploratorias
Todo hallazgo surgido de mirar train (incluidas observaciones heurísticas) debe registrarse aquí como EXP-1xx con su mecanismo **antes** de evaluarse en val.

## Resultados
(vacío: aún no se ha corrido ningún experimento)
