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

Variantes miradas en train hasta ahora: 162 + 72 + 18 = 252 (más 1 corrida con la fuga, descartada).
