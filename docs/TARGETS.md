# TARGETS: metas y puertas de aprobación (pre-registro)

Fecha de registro: 2026-11-20, **antes de analizar cualquier dato**. Ningún número de este documento se cambia después de ver resultados; si se cambia, queda como una nueva versión fechada y los resultados previos no cuentan.

## 1. Costos verificados (Hyperliquid, nivel base, perpetuos)

Fuente: documentación oficial de comisiones de Hyperliquid, consultada el 2026-11-20.

| Concepto | Valor |
|---|---|
| Taker | 0,045% por lado |
| Maker | **+0,015% por lado (se paga, no se cobra)** |
| Rebate maker | solo con >0,5% del volumen maker total de la plataforma (nivel de creador de mercado) |
| Gas | 0 |

Corrección a una afirmación previa del proyecto: "maker paga −0,01%" **no aplica** a una cuenta nueva. Modelo base del laboratorio: taker 4,5 bps + slippage 1 bps por lado = **11 bps por round trip**. Los precios de Binance son un proxy: la calibración contra Hyperliquid sigue pendiente, por eso todo resultado se re-evalúa con costos ×1,5.

## 2. La aritmética de las metas

`retorno diario = operaciones/día × exposición por operación (× banca) × edge neto por operación`

| Meta diaria | Ops/día | Exposición | Edge neto necesario | Edge bruto necesario |
|---|---|---|---|---|
| 1% | 60 | 2x | 0,8 bps | 11,8 bps |
| 3% | 60 | 2x | 2,5 bps | 13,5 bps |
| 10% | 60 | 2x | 8,3 bps | 19,3 bps |
| 20% | 60 | 2x | 16,7 bps | 27,7 bps |
| 30% | 60 | 2x | 25,0 bps | 36,0 bps |

Lectura honesta:
- Ganar 20-30% diario exige una ventaja bruta de 28-36 bps **por operación**, sostenida, en operaciones que cuestan 11 bps. Es posible en teoría y rarísima en la práctica; el laboratorio la **persigue**, no la **supone**.
- Compuesto, 20% diario es ×237 en 30 días y ×8·10²⁸ en un año: ningún mercado lo sostiene a escala. Si apareciera, la capacidad (profundidad del libro) la limitaría mucho antes que la estrategia.
- Se prohíbe llegar a una meta subiendo el apalancamiento: el apalancamiento escala ganancias y pérdidas igual. La meta se alcanza con edge, no con riesgo.

## 3. Niveles de meta (retorno neto de costos, sobre la banca, apalancamiento efectivo ≤ 3x)

| Nivel | Retorno diario medio | Días positivos | Máx. drawdown | Para qué sirve |
|---|---|---|---|---|
| Piso | ≥ 0,3% | ≥ 55% | ≤ 20% | Mínimo para pasar a modo sombra |
| Objetivo | ≥ 1% | ≥ 60% | ≤ 20% | Lo que consideramos un éxito real |
| Ambición | ≥ 3% | ≥ 65% | ≤ 25% | Excelente; se exige evidencia extra |
| Aspiración | 10-30% | n/a | n/a | No es criterio de aprobación. Se reporta cuánto edge exigiría |

Si el mejor candidato honesto queda entre "Piso" y "Objetivo", se entrega tal cual y con su número real. "Lo más cercano posible" significa la mejor estrategia que sobreviva, no estirar una que no sobrevive.

## 4. Puertas duras (todas obligatorias, en orden)

**Puerta 1: desarrollo (train + val, walk-forward).**
- Edge neto por operación > 0 con intervalo de confianza 95% (bootstrap por bloques de día) cuyo límite inferior sea > 0 en los tramos fuera de muestra.
- Sigue siendo positivo con costos ×1,5.
- Robusto: ≥ 70% de las combinaciones vecinas de parámetros también son positivas (no un pico aislado).
- Ninguna moneda individual aporta más del 25% del PnL; los 5 mayores aportes suman < 50%.
- Positivo en al menos dos regímenes de mercado (alcista / bajista / lateral) definidos antes.
- Presupuesto total de variantes evaluadas en val: ≤ 200; cada una se cuenta y se aplica deflated Sharpe.

**Puerta 2: Bóveda A (2026-01-01 → 2026-05-31).** Máximo 3 finalistas en total, una apertura cada una, registrada en `experiments/VAULT_LEDGER.md`.
- Edge neto por operación ≥ 50% del estimado walk-forward y límite inferior del IC95% > 0.
- Profit factor ≥ 1,25; drawdown ≤ 20% al apalancamiento propuesto; ≥ 55% de semanas positivas.

**Puerta 3: Bóveda B (2026-06-01 → fin de datos).** Solo para el sobreviviente de la Puerta 2, **sin tocar ningún parámetro**, mismos umbrales. Si falla, la idea muere y no se reajusta para "volver a intentar".

**Puerta 4: modo sombra** (testnet/papel con la misma lógica del backtest).
- ≥ 14 días y ≥ 300 operaciones simuladas.
- Slippage realizado ≤ 1,5× el modelado; PnL dentro del IC del backtest.

**Puerta 5: capital real.**
- Wallet de API dedicada, sin permiso de retiro, fondeada solo con dinero que se puede perder por completo.
- Parada automática: pérdida diaria ≥ 5% o drawdown ≥ 15% desde el máximo → el bot se detiene hasta revisión humana.
- Se empieza con la mitad del capital previsto y 1x; se escala solo con evidencia en vivo.

## 5. Reglas de evidencia
- Las bóvedas A y B viven en releases separados (`vault-a`, `vault-b`) y **no se descargan al entorno de investigación** antes de que el candidato esté congelado (hash del código registrado). Cada apertura se anota en el ledger.
- Si un resultado parece demasiado bueno, se asume error (lookahead, relleno irreal, fuga) hasta demostrar lo contrario.
- Una estrategia que solo funciona en un tramo del tiempo, en pocas monedas o con un solo parámetro mágico se descarta.
