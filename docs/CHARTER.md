# Research charter

1. Registro previo de hipótesis, mecanismo y número de variantes.
2. Separación cronológica train / validation / vault, con el vault sellado.
3. Walk-forward; ninguna conclusión basada en una sola partición.
4. Reportar comisiones Hyperliquid vigentes, deslizamiento, impacto, funding, costes de liquidación y sensibilidad.
5. Señal sólo con información disponible al cierre de t; ejecución simulada no antes de t+1.
6. Control adversarial de sobreajuste, fuga, cherry-picking, múltiples intentos y sesgo supervivencia.
7. Binance es proxy: no inferir ejecutabilidad ni spreads históricos de Hyperliquid sin datos propios.
8. Sólo shadow antes de operar con dinero real; wallet dedicada y riesgo limitado después de validación.
9. Todo dato no probado en vivo se declara NO PROBADO, sin garantías de beneficios.
