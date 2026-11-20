# trading-lab

**Laboratorio cuantitativo de futuros perpetuos Hyperliquid. Fuentes gratuitas. Sin operaciones reales.**

## Arquitectura
- `scripts/collect_data.py`: selecciona hasta 30 perpetuos activos por volumen nocional 24h Hyperliquid e intersección activa Binance USD-M, descarga 105 días de velas Binance 1m y métricas 5m, financiamiento Hyperliquid paginado y snapshots nativos 1m/15m.
- `scripts/validate_data.py`: audita filas, continuidad temporal, precios válidos y cobertura; publica `audit.json`.
- `src/lab/dataset.py`: `merge_asof` punto-en-el-tiempo para eliminar filtraciones futuras.
- `src/lab/costs.py`: modelo sintético de costes, **no calibrado con ejecuciones reales**.
- `.github/workflows/collect.yml`: lanzamiento por push, manual o diario; utiliza GitHub Release `dataset-latest` para conservar el ZIP entre ejecuciones.
- `tests/`: pruebas sin red de timestamps, desbalance de flujo, joins y costes.
- `docs/CHARTER.md`, `experiments/REGISTRY.md`: método y protocolo de investigación.

## Inicio
```bash
python -m pip install -r requirements.txt
pytest -q
python scripts/collect_data.py --days 105 --count 30 --workers 6 --out data
python scripts/validate_data.py data
```

En Actions se ejecuta el workflow **Free 105d hybrid data collection**. El histórico se publica en el Release `dataset-latest`, archivo `dataset.zip`. El ZIP no debe versionarse en git. El archivo `manifest.json` refleja cobertura, errores y faltantes.

## Fuentes y sesgos
- Binance USD-M 1m es un proxy **no equivalente** al libro de órdenes, spread ni ejecución en Hyperliquid.
- Las velas y métricas se convierten a `available_at`, de acuerdo con cierre de intervalo. Para métricas Binance, el sello `create_time` cambió de fin a inicio el **25-06-2026**; por eso se añade 5 min a las nuevas etiquetas.
- Los snapshots Hyperliquid se limitan a las 5,000 velas más recientes por intervalo (aproximadamente 3.5 días en 1m y 52 días en 15m).
- La cifra de 4.5 millones de velas es una expectativa aproximada para 30 pares × 105 días, **no** una cobertura verificada. El tamaño en MB tampoco es fijo.
- No se ha validado rentabilidad ni existen garantías de beneficios. Ninguna orden será enviada.
- Antes de una estrategia real deben fijarse y auditarse fechas train/validation/vault, comisiones reales, deslizamiento, impacto y sensibilidad a la ejecución.

## Estado
- [x] Estructura base y código del colector
- [x] Workflow y pruebas sintéticas escritas
- [ ] Ejecución confirmada en API viva y auditoría de cobertura
- [ ] Partición temporal sellada y preregistro concreto de experimentos
- [ ] Backtest walk-forward y validación ciega
- [ ] Shadow/testnet mínimo 7 días
- [ ] Operación con capital real, **sólo tras aprobar las fases anteriores**
