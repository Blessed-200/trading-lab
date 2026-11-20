# ROADMAP

Estado: `[ ]` pendiente · `[~]` en curso · `[x]` hecho · `[!]` bloqueado

## Fase 0: Base del proyecto
- [x] CHARTER (método, riesgo, honestidad) y REGISTRY
- [x] Arreglo de CI: `pytest.ini` con `pythonpath = .` (antes ninguna ejecución pasaba de las pruebas)
- [x] Recolector sin sesgo de moneda: TODOS los perpetuos USDT de Binance (incl. delistados) vía listado oficial de archivos; sin filtro por volumen de hoy
- [x] Recolector nativo Hyperliquid que **acumula** historia (antes sobrescribía)
- [~] Primera ejecución real en Actions (**NO PROBADO contra APIs en vivo hasta que corra**)

## Fase 1: Datos
- [ ] Smoke test en Actions (ventana corta) y revisión de manifests
- [ ] Backfill histórico completo de Binance 1m + métricas 5m (por shards)
- [ ] Backfill de funding Hyperliquid desde 2023-06 y acumulación diaria de velas 1m nativas
- [ ] Mapeo HL↔Binance: revisar `hyperliquid_without_binance` en `universe.json`
- [ ] Calibración proxy Binance↔Hyperliquid (necesita ambos conjuntos juntos; pendiente de un job de calibración)
- [ ] Partición train / validation / vault con fechas fijadas y registradas ANTES de explorar

## Fase 2: Investigación (cada hipótesis en `experiments/REGISTRY.md`)
- [ ] Línea base: estrategias triviales (para saber cuánto vale vencerlas)
- [ ] Filtro de liquidez **point-in-time** (volumen rodante conocido en t, nunca el de hoy)
- [ ] Hipótesis estructurales: funding, flujo agresor + open interest, lead-lag, liquidaciones en cascada
- [ ] Walk-forward con corrección por número de intentos
- [ ] Apertura única de la bóveda ciega para las finalistas

## Fase 3: Modo sombra
- [ ] Bot de papel/testnet con la misma lógica del backtest
- [ ] 7+ días y comparación contra el modelo

## Fase 4: Operación real (solo si Fase 3 aprueba)
- [ ] Wallet de API dedicada, sin retiro; capital mínimo, 1x, kill switch y tope diario
