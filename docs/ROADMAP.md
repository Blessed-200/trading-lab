# ROADMAP

Estado: `[ ]` pendiente · `[~]` en curso · `[x]` hecho · `[!]` bloqueado

## Fase 0: Base del proyecto
- [x] CHARTER (método, riesgo, honestidad) y REGISTRY
- [x] Arreglo de CI: `pytest.ini` con `pythonpath = .` (antes ninguna ejecución pasaba de las pruebas)
- [x] Recolector sin sesgo de moneda: TODOS los perpetuos USDT de Binance (incl. delistados) vía listado oficial de archivos; sin filtro por volumen de hoy
- [x] Recolector nativo Hyperliquid que **acumula** historia (antes sobrescribía)
- [x] Primera ejecución real en Actions (48 shards, 0 errores, 52,6 GB)

## Fase 1: Datos
- [x] Smoke test y revisión de manifests
- [x] Backfill Binance 1m + métricas 5m desde 2023-06 (925 perpetuos, incl. 29 delistados)
- [x] Panel 5m (914 símbolos, 164 M barras) y partición dev / bóveda A / bóveda B sellada con sha256 (`experiments/SEALED_MANIFEST.json`)
- [ ] Backfill de funding Hyperliquid desde 2023-06 y acumulación diaria de velas 1m nativas
- [ ] Mapeo HL↔Binance: revisar `hyperliquid_without_binance` en `universe.json`
- [ ] Calibración proxy Binance↔Hyperliquid (necesita ambos conjuntos juntos; pendiente de un job de calibración)
- [x] Partición fijada en `src/lab/splits.py` y metas pre-registradas en `docs/TARGETS.md`

## Fase 2: Investigación (cada hipótesis en `experiments/REGISTRY.md`)
- [x] Línea base y familias EXP-001, 002, 004, 005 en train: **todas descartadas** (ver REGISTRY). Fuga de OI detectada y corregida.
- [x] EXP-006 (atlas de excursiones), EXP-007 (ML directo walk-forward), EXP-008 (ejecución pasiva con selección adversa): todas sin pasar Puerta 1
- [ ] EXP-003 (lead-lag) pendiente
- [ ] Filtro de liquidez **point-in-time** (volumen rodante conocido en t, nunca el de hoy)
- [ ] Hipótesis estructurales: funding, flujo agresor + open interest, lead-lag, liquidaciones en cascada
- [ ] Walk-forward con corrección por número de intentos
- [ ] Apertura única de la bóveda ciega para las finalistas

## Fase 2b: Datos propios de microestructura (siguiente)
- [ ] Grabador en vivo (GitHub Actions por tramos de ~5,5 h) de libro L2 y trades de Hyperliquid + precio de referencia, para las ~30 monedas más líquidas; verificar si el WebSocket de Binance es accesible desde los runners
- [ ] Hipótesis sobre esos datos: desbalance del libro, rezago Binance→Hyperliquid, cascadas de liquidación nativas
- [ ] Evaluar ejecución maker (costo ~3 bps) con modelo de relleno conservador

## Fase 3: Modo sombra
- [ ] Bot de papel/testnet con la misma lógica del backtest
- [ ] 7+ días y comparación contra el modelo

## Fase 4: Operación real (solo si Fase 3 aprueba)
- [ ] Wallet de API dedicada, sin retiro; capital mínimo, 1x, kill switch y tope diario
