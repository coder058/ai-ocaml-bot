# Plan de entrega pública: laboratorio de ejecución y microestructura

Fecha de revisión inicial: 28 de septiembre de 2026, 01:55 CEST.
Alcance solicitado: plan detallado, trabajo inline, sin agentes paralelos.
Este documento propone trabajo; no certifica que sus entregables futuros existan.

## 1. Estado comprobado

- Repositorio público actual: `coder058/ai-ocaml-bot`, último
  commit local `d6c4efe`. Tres archivos nuevos de captura Hyperliquid estaban
  sin commit al revisar: el colector, su auditor de cobertura y su servicio.
- Dublín: ejecutor OCaml paper, captura Alpaca, captura pública Hyperliquid y
  temporizador de análisis estaban activos. Los tres procesos persistentes
  mostraban cero reinicios desde sus arranques actuales; esto no demuestra
  disponibilidad prolongada.
- Memoria del VPS: 1.910 MiB totales, 1.448 MiB disponibles; 48 GiB libres en
  disco. No hay evidencia actual que justifique ampliar este VPS a 8 GB.
  Esto no mide los otros servidores o bots llamados Polybow.
- Snapshot público a las 23:55 UTC del día 27: 103 órdenes de cuenta, 76
  órdenes BTC con ejecución y 135 registros de fills de cuenta. Los recuentos
  de órdenes, fills y operaciones cerradas son conceptos distintos.
- Posición BTC observada: 0,000709101 BTC, valor marcado de $59,887352. AAPL
  sigue siendo una posición anterior protegida. El equity total de cuenta
  ($101.456,70 en ese snapshot) incluye AAPL y no mide el resultado del bot.
- La UI mostraba aproximadamente −$3,30 como flujo ejecutado más inventario
  marcado; lo etiquetaba como indicativo. P&L neto cerrado: todavía no
  verificado. La UI contiene historial, fills parciales y una razón textual,
  pero algunos inspectores dicen que no conservaron los precios de la
  cotización que originó la decisión.
- Alpaca observa 15 pares cripto. Solo BTC puede enviar órdenes paper. La
  política activa es `quote_cross_30s_v1`, no calibrada. Murphy/candlesticks y
  Markov se observan en shadow y no autorizan operaciones.
- La nueva captura Hyperliquid recibió 29 confirmaciones de suscripción:
  allMids de xyz y BBO/velas 1m para 14 contratos seleccionados. En el smoke
  de 15 segundos recibió 288 mensajes; allMids incluyó 126 nombres. Recibir
  un mid no demuestra liquidez, vigencia del mercado ni análisis completo.
- Entre los FX-like activos encontrados en xyz están EUR, JPY y GBP. No se
  verificaron diez pares FX. Las especificaciones y orientación de cada
  contrato deben confirmarse antes de etiquetarlos como pares spot conocidos.
- El camino HTTP OCaml crea procesos curl. Hay timestamps de reloj civil,
  escritura/fsync y comprobaciones REST alrededor de las decisiones. No hay
  un benchmark sostenido que permita presentar el sistema actual como HFT.

### Actualización operativa, 28 de septiembre de 2026, 09:03 UTC

- La primera captura Hyperliquid se reinició dos veces por `AssertionError`:
  una reconexión cerraba el archivo, pero no restablecía el estado de fecha.
  También produjo un JSONL sin compresión de unos 200 MB. El archivo se
  conservó, sin comprimir ni borrar.
- Se corrigió el límite de sesión, se añadieron archivos gzip por hora con ID
  de sesión y el lector ahora acepta ambas generaciones de archivos.
- Tras instalar el cambio, systemd quedó activo, con 29 suscripciones
  confirmadas y 0 reinicios desde ese arranque manual. La verificación leyó
  cuatro sesiones de la fecha UTC: 731.676 mensajes BBO, 76.914 candle,
  6.447 allMids, cero líneas corruptas y cero huecos en las secuencias que
  se llegaron a escribir localmente. Esos ceros no detectan eventos omitidos
  antes de la recepción.
- El ejecutor OCaml y la captura Alpaca seguían activos sin reinicios al
  comprobar. Snapshot público posterior a las 07:18 UTC tenía 215 órdenes y
  340 fills de cuenta; el filtro de posiciones BTC de esa consulta no
  produjo una fila, así que no inferir el inventario actual. Volver a
  reconciliar con snapshot firmado y Alpaca antes de presentar P&L.

## 2. Trabajo anterior recuperado

### hlbot privado

Checkout privado local; su ruta de usuario se omite de este documento público.

- `hlbot/data/`: validación y almacenamiento de datos; los 29 tests de
  `tests/test_data.py` pasaron en esta revisión. Los 77,9 millones de barras
  y demás métricas de los informes son resultados históricos documentados;
  no se recalculó ahora todo el corpus ni se verificaron todos sus archivos.
- `hlbot/capture/ws.py`: captura de trades, BBO y contexto, bloqueo de escritor
  único, rotación y mecanismos para manejar replays/reconexiones. Los informes
  antiguos registran 531 suscripciones; no es un benchmark actual de Dublín.
- `research/` y `docs/`: evaluaciones, controles y retractaciones que deben
  conservarse en el registro de experimentos. Hay secciones antiguas que no
  incorporan conclusiones posteriores; comprobar resultados y código, no
  copiar titulares de README como si fueran evidencia nueva.
- `hlbot/live/vsurge_bot.py`: genera objetivos de cartera; en modo paper
  registra decisiones y no simula toda la vida de órdenes y fills. Su log
  local termina el 6 de agosto. La prueba de presencia de su clave dio falso.
- `hlbot/live/execute.py`: puede operar MAINNET cuando se arma. Requiere
  revisión antes de reutilizar: no es un adaptador testnet; el precio por
  defecto se calcula a ±2% del mid pese a describirse como precio al touch;
  falta reconciliar órdenes abiertas y cancelar/sustituirlas; no cierra por
  sí solo nombres ausentes del nuevo objetivo. El estado del bot se escribe
  antes de conocer el resultado de ejecución. No importar esta ruta al paper.
- `hlbot/strategy/quoter.py`: scaffold con modelo económico retractado.
  `paper_quoter.py`: simulación de cola que necesita revisar supuestos y
  versiones. Sus fills no son fills de una cuenta de exchange.

### Perp Signal Radar y Pattern Forge

El checkout privado de Perp Signal Radar contiene el precursor OCaml, un panel
Python multivenue, estudios, adaptadores, calibración, simuladores paper y
una investigación extensa. Tiene muchos cambios sin commit: preservar antes
de extraer módulos. Su catálogo de 191 estudios no demuestra 191 señales
predictivas ni reproducciones exactas de TradingView.

El repositorio público Pattern Forge contiene la presentación pública:
validación de velas, replay causal, agregación sin rellenar huecos, EMA/RSI/MACD,
Bollinger, formas de velas y gráficos. Reutilizar las funciones y fixtures
con pruebas de paridad; no copiar las páginas enteras dentro del monitor.

## 3. Producto y arquitectura propuestos

Nombre público propuesto: **OCaml Market Microstructure Lab**. Una etiqueta
independiente identifica claramente su autoría. Posicionamiento inicial:
laboratorio de ejecución por eventos, microestructura, ML y paper trading,
con benchmarks reproducibles. La denominación HFT debe depender de las
mediciones y del alcance demostrado, no del número de operaciones.

```text
Feeds públicos -> normalización + archivo durable -> replay determinista
                         |
                         v
              estado de mercado en OCaml
                         |
         indicadores / inferencia de modelo versionado
                         |
              intención -> riesgo -> OMS
                         |
              adaptador paper/testnet
                         |
        reconciliación de órdenes, fills y posiciones
                         |
              ledger -> API de lectura -> monitor

Python: preparación de datasets, entrenamiento, evaluación y reportes
LLM opcional: investigación/explicaciones con referencias, fuera de ejecución
```

OCaml mantiene el motor, estados de órdenes y riesgo. Python mantiene datos y
ML; TypeScript/Next mantiene la UI. No reescribir todo en C/C++: perfilar primero
y usar un componente nativo solo si un cuello medido lo justifica. Rails no
resuelve los cuellos observados de este motor.

## 4. Secuencia de ejecución y puertas de aceptación

### Paso 1 — Congelar y ordenar la base

1. Inventariar fuentes, versiones, cambios locales, modelos y servicios.
2. Guardar manifiestos y hashes de datasets; distinguir histórico, recibido
   en tiempo real y datos sintéticos. Preservar estados anteriores.
3. Versionar la captura nueva después de revisar bloqueo de escritor,
   cierre de archivos, reinicios y reserva de disco.
4. Registrar políticas descartadas para no repetir búsquedas ya refutadas.

**Termina cuando:** un manifiesto permite reconstruir qué código y modelo
produjo cada resultado; no quedan servicios desplegados sin versión conocida.

### Paso 2 — Cerrar contabilidad y trazabilidad

1. Crear un ledger por venue/cuenta/estrategia con importación idempotente de
   órdenes, fills, comisiones en efectivo o activo y funding cuando aplique.
2. Distinguir importe solicitado, ejecutado, cancelado y posición restante.
3. Emparejar lotes con una convención explícita; tratar parciales y residuos.
4. Separar AAPL y capital preexistente del resultado BTC; no mostrar el
   cambio de equity total como resultado del bot.
5. Unir cada intención y orden con input exacto, timestamps, regla/modelo,
   features, precios bid/ask, filtros de riesgo y resultado del broker.
6. Reconstruir evidencia histórica solo donde exista; marcar huecos reales.

**Termina cuando:** balances y cantidades cuadran con el broker a la precisión
documentada; cualquier diferencia aparece explicada. La UI puede mostrar
P&L realizado/no realizado y costes sin dobles conteos.

### Paso 3 — Registro de instrumentos y cobertura real

1. Catalogar venue, símbolo original, tipo de contrato, subyacente, divisa,
   tick/lote, calendario, estado activo y endpoint mainnet/testnet/paper.
2. Incluir BTC y otros cripto; acciones/ETF de Alpaca según permisos reales;
   HIP-3 FX-like, índices y energía según especificaciones verificadas.
3. Distinguir DIA/QQQ como ETF de sus índices de referencia y los perpetuos
   HIP-3 de spot FX o propiedad de acciones.
4. Mostrar por mercado: descubierto, suscrito, recibiendo, analizable,
   autorizado para paper, suspendido. Un catálogo no equivale a cobertura.
5. Mantener peticiones de diez FX pendientes de un inventario que las soporte.

**Termina cuando:** todos los mercados visibles tienen procedencia, tipo,
estado y cobertura comprobables; no hay capacidades anunciadas por inferencia.

### Paso 4 — Captura resistente y dataset reproducible

1. Recuperar del hlbot los controles de escritor único, replay, deduplicación,
   rotación y liveness por símbolo; adaptar rutas y contratos HIP-3.
2. Archivar BBO, trades, libro disponible y contexto/funding/oracle. Verificar
   qué canales son snapshots y cuáles incrementales antes de reconstruir libro.
3. Conservar reloj de exchange y recepción; usar reloj monotónico para duraciones
   locales. Medir sincronización antes de interpretar diferencias de relojes.
4. Hacer visibles silencios, errores, eventos fuera de orden y pérdidas. Si el
   proveedor no da secuencias, declarar lo que no puede detectarse.
5. Implementar cierre temporal de velas trade-driven y revisiones as-of; no
   inventar velas sin eventos. Generar 1m/5m/30m/1h/4h desde fuente declarada.
6. Comprimir, rotar y presupuestar retención a partir del crecimiento medido.

**Termina cuando:** reiniciar o desconectar no corrompe ni duplica datos y el
replay reproduce las mismas observaciones a partir de un archivo con hash.

### Paso 5 — Motor OCaml y benchmark de latencia

1. Separar feed, estrategia, riesgo, persistencia, ejecución y telemetría por
   colas acotadas, con comportamiento explícito ante saturación.
2. Medir antes de optimizar: recepción->normalización->features->decisión->
   riesgo->envío, y por separado envío->ack->fill. Conservar tamaños de muestra.
3. Sustituir procesos curl por transporte persistente si el perfil confirma
   su coste. Reconciliar por eventos y snapshots sin quitar garantías de riesgo.
4. Reducir asignaciones/copias; medir pausas GC y escrituras. Conservar el
   journal durable previo al envío y medir su coste, sin esconderlo del benchmark.
5. Publicar p50/p95/p99/máximo, throughput sostenido, backlog y pérdidas,
   hardware, commit, carga y dataset. Comparar versiones sobre la misma carga.

**Termina cuando:** cualquiera puede reproducir el benchmark offline y
entender la diferencia entre latencia local y red externa. No fijar objetivos
en microsegundos antes de medir la línea base ni llamar HFT a velas de 1m.

### Paso 6 — Replay de ejecución y OMS

1. Modelar estados: intención, envío pendiente, aceptada, parcial, cancelación
   pendiente, cancelada, ejecutada, rechazada y resultado desconocido.
2. Probar restart después de enviar pero antes de recibir ack, duplicados,
   cancel/fill en carrera, timeout y desconexión. Nunca reintentar a ciegas.
3. Añadir simulación con bid/ask y liquidez observada; diferenciar cola estimada
   de cola conocida. BBO/L2 no revela nuestra posición exacta en L3.
4. Versionar escenarios optimistas/conservadores y comparar con fills paper.

**Termina cuando:** cada orden tiene un estado reconciliable tras fallos y
ningún fill simulado se presenta como fill de broker. Alpaca paper no modela
cola, impacto ni deslizamiento por latencia, según su documentación.

### Paso 7 — Análisis técnico compartido

1. Extraer definiciones de Pattern Forge y crear fixtures comunes Python/
   TypeScript/OCaml. Verificar warm-up, huecos, revisiones y momento conocido.
2. Producir features de velas, tendencia, volatilidad, spread, imbalance y flujo
   según calidad real disponible. Separar marcos lentos de eventos rápidos.
3. Registrar por candidato qué observación lo activa y qué lo invalida.
4. Mantener Energy Monitor como contexto con fecha de publicación y revisiones;
   evaluar su relevancia antes de usarlo para predecir mercados intradía.

**Termina cuando:** una misma entrada produce features equivalentes y cada
feature estaba disponible antes de la decisión; no se confunde patrón con edge.

### Paso 8 — ML con una pregunta medible

1. Definir primero el objetivo: retorno ejecutable a un horizonte, riesgo de
   selección adversa tras fill, probabilidad de fill o volatilidad futura.
2. Empezar con baseline constante, modelo lineal/logístico y Markov; probar
   un modelo de árboles como candidato. Redes profundas solo si aportan mejora
   y hay suficientes datos para evaluarla.
3. Dividir cronológicamente por fecha, purgar etiquetas solapadas y fijar
   embargo según horizonte. Ajustar transformaciones solo en entrenamiento.
4. Congelar configuración antes del test; registrar cada intento y comparar
   controles, ablations por familia de features y estabilidad por mercado/régimen.
5. Medir Brier/log-loss y calibración si se publica probabilidad; intervalos de
   incertidumbre y resultados con costes, no solo accuracy o tasa de acierto.
6. Exportar modelo pequeño y versionado al motor; comprobar paridad de
   predicciones e instrumentar coste de inferencia y detección de deriva.

**Termina cuando:** existe evaluación reproducible sobre datos no usados para
seleccionar el modelo. Si no supera el baseline, el resultado se publica como
negativo y el modelo sigue sin autoridad. No prometer rentabilidad.

### Paso 9 — Riesgo, tamaño y testnet multiactivo

1. Mantener los límites paper actuales hasta tener presupuestos por estrategia,
   cartera, correlación, pérdida y liquidez explícitos.
2. Evaluar stop por invalidación/volatilidad y salida temporal en el mismo
   experimento que la entrada. Incluir gaps y la posibilidad de no ejecución.
3. Mapear $50/$100/$500 a una política documentada solo con calibración; un
   porcentaje de dirección favorable no determina por sí mismo el tamaño.
4. Construir un adaptador Hyperliquid testnet aislado con allowlist de origen,
   gestión de nonce/ID, cancelaciones, límites y conciliación.
5. Comprobar acceso a cartera testnet, fondos de prueba y contratos realmente
   disponibles. El feed mainnet no equivale a ejecución testnet.
6. Promover candidatos en shadow->simulador->paper/testnet con criterios fijados
   antes de mirar el resultado. La automatización revierte ante fallos medidos.

**Termina cuando:** se demuestra un ciclo completo y reconciliado en cada venue
paper anunciado. Sin cartera testnet verificada, Hyperliquid sigue en lectura.

### Paso 10 — Monitor público comprensible

1. Primera pantalla: estado, posición abierta, P&L realizado/no realizado,
   comisiones/funding, última operación y frescura de datos.
2. Tabla de operaciones cerradas con entrada/salida/resultado; tabla distinta
   para órdenes y parciales; filtros por venue, símbolo y versión de estrategia.
3. Inspector: gráfico con precio y fills, features al decidir, probabilidad si
   calibrada, motivo, rechazo/abstención, tamaño, stop y cadena de timestamps.
4. Radar multiactivo: cobertura, spread, marcos disponibles y estado operativo.
   Evitar mostrar cien instrumentos como si cien estuvieran siendo operados.
5. Página Engineering: arquitectura, benchmark, replay de un incidente, modelo
   y enlaces al commit/experimento. Detalles técnicos fuera de la vista operativa.
6. Publicar resumen firmado y minimizado; revisar derechos de redistribución
   antes de publicar datos crudos. Probar móvil, accesibilidad y estados vacíos.

**Termina cuando:** una persona puede localizar una operación, entender por
qué ocurrió y reconciliar su resultado sin leer logs privados.

### Paso 11 — Operación y fallos

1. Alertas accionables de feed atrasado, reloj, backlog, disco, reconciliación,
   pérdida de firma y modelo no válido; umbrales derivados de observaciones.
2. Probar restauración de backup y rollback de código/modelo.
3. Hacer una prueba prolongada y declarar duración, carga, fallos y recuperación;
   su duración se fija como requisito de prueba, no como evidencia estadística.
4. Perfilar memoria/CPU/I/O antes de ampliar capacidad. Usar Dublín para este
   proyecto; no ocupar Frankfurt mientras el otro agente trabaja en Fly Brain.

**Termina cuando:** los incidentes se detectan, las órdenes quedan reconciliadas
y el runbook permite recuperar el servicio sin depender del autor.

### Paso 12 — Paquete de presentación

1. README con problema, demo, arquitectura y un comando de replay offline.
2. Dataset pequeño redistribuible o sintético explícito, hashes y resultados
   esperados; instalación desde checkout limpio y CI sin secretos.
3. Informe de benchmark, model card, registro de experimentos y limitaciones.
4. Demo guiada: evento->features->decisión->riesgo->orden->fill->P&L, más un
   fallo recuperado. Video breve opcional, sin cifras de rendimiento inventadas.
5. Revisión de secretos, licencias, dependencias y afirmaciones públicas.
6. Release etiquetada; destacar contribución propia y explicar decisiones,
   incluida la evidencia que descartó estrategias.

**Termina cuando:** otra persona reproduce la demo y el benchmark, y todas las
afirmaciones del portfolio enlazan a evidencia comprobable.

## 5. Orden práctico y esfuerzo

Ruta crítica: 1->2->3->4->5->6->7->8->9->10->11->12. La UI puede diseñarse después
del ledger y cerrarse al estabilizar los modelos; la captura ya puede acumular
datos mientras se desarrolla el resto. El trabajo se realiza inline.

Estimación de planificación, no compromiso: ordenar fuentes, ledger y primera
UI clara puede ocupar varios días; replay/OMS/benchmark y ML evaluado pueden
requerir semanas. El tiempo necesario para evidencia forward no se obtiene
acelerando el reloj ni aumentando artificialmente el número de órdenes.

La primera entrega debe ser contabilidad reconciliada + historial explicable +
replay reproducible. La entrega HFT/ML posterior debe aportar mediciones de
microestructura, ejecución y modelos; la rentabilidad puede seguir sin aparecer.

## Verificación operativa — 28 de septiembre, 09:43 UTC

- Dublín volvió a comprobar los tres servicios: ejecutor Alpaca paper, captura
  Alpaca y captura Hyperliquid pública están activos. El ejecutor conserva el
  endpoint paper, la protección AAPL, conciliación de órdenes pendientes, la
  compra base de $100 y el tope BTC de $500.
- Snapshot de broker completo a las 09:37:25 UTC: 253 órdenes del bot, 408
  fills y BTC plana. Compras ejecutadas $4.136,980382580415, ventas
  $4.126,234075030758 y diferencia de efectivo −$10,746307549657 antes de
  actividades de fees. `CFEE`/`FEE` no mostraron filas; la diferencia de
  cantidad frente a compras fue 0,000123549 BTC. **No es P&L neto verificado**:
  las fees aún no se atribuyen por fill y los resultados son simulados.
- El ejecutor compilado añade al evento de decisión los dos pares bid/ask, el
  sentido del cruce y su margen en bps. Tests sintéticos cubren cruces alcistas,
  bajistas y ausencia de cruce. El exporter conserva estos campos y el inspector
  solo los muestra si existen en el registro; órdenes históricas incompletas
  continúan identificadas como tales.
- Un primer reinicio reveló que el calentamiento 1m intentaba parsear velas de
  todos los símbolos del archivo compartido como si fueran BTC. Se añadió un
  filtro explícito por `BTC/USD`, se probó y desplegó de nuevo. A las 09:42:18
  el servicio cargó 194 velas BTC contiguas y ya no reportó fallo. El primer
  muestreo posterior, a las 09:43:43, fue `candidate=false`; por tanto aún no se
  ha observado una orden real con la nueva traza de precios.
- El verificador de Hyperliquid detectó que el gzip de la hora actual sigue
  abierto. Ahora cuenta su prefijo escrito y lo enumera en
  `incompleteGzipFiles`; no lo confunde con un archivo cerrado ni afirma
  integridad de eventos que el proveedor no entregó. Se observaron cinco
  sesiones, 784.955 BBO, 82.035 actualizaciones de velas, 6.824 allMids,
  cero huecos de secuencia local y cero líneas JSON corruptas.
- Verificación local/remota: 21 pruebas Python, 8 pruebas web, TypeScript y
  build Next.js; Dune 3.24.2 compiló y pasó toda la suite OCaml. El proceso
  actual mantiene `quote_cross_30s_v1`, sin aumentar actividad ni cambiar
  tamaños; el monitor web aún requiere publicar/verificar la nueva interfaz.

## Actualización publicada — 28 de septiembre, 09:53 UTC

- El commit `85f7881` está publicado. El inspector web muestra cotizaciones
  concretas en registros nuevos y explica explícitamente cuando una orden
  histórica carece de traza. La compra paper de 09:39:27 se unió a su par de
  quotes y broker: cruce alcista 0,230050 bps; cinco fills parciales sumaron
  $70 y Alpaca canceló el resto. La venta de 09:52:03: cruce bajista
  1,184709 bps; cuatro fills sumaron $60 y se canceló el resto.
- El auditor independiente, leyendo los ficheros de captura del 27 y 28, enlazó
  230 de 230 órdenes con `HOT_SAMPLE` al par exacto de quotes y estado del
  broker; no dejó órdenes sin emparejar. Halló 101 estados `filled` y 129
  `canceled`, cruce entre 0,011831 y 12,000184 bps, mediana 1,529065. Esto
  caracteriza el disparador; no mide retorno posterior ni ventaja.
- A las 09:53:50, el reconciliador leyó 255 órdenes, 417 fills y BTC abierta
  por 0,000119779 ($9,91 marcada). La diferencia buy-minus-sell en efectivo
  era −$20,747935 antes de activities; el monitor mostró −$10,84 al sumar la
  marca BTC. Ambas magnitudes son orientativas y no reemplazan fees/lot ledger.
  `CFEE` y `FEE` no tenían filas y quedan 25 órdenes sin `HOT_SAMPLE`; el P&L
  neto sigue sin verificarse.
- Se corrigió el auditor para aceptar varias capturas diarias: las 78 filas que
  parecían ausentes procedían del 27 cuando la consulta solo leía el 28. La
  prueba de cruce entre ficheros diarios pasó. El monitor CI completó con éxito;
  ambos jobs de GitHub Actions completaron con éxito a las 09:48:21 UTC.

## Actualización de evidencia — 28 de septiembre, 10:10 UTC

- La auditoría completa actual registró 257 órdenes y 422 fills BTC del bot.
  Compras por $4.246,982078 frente a ventas por $4.236,121736 dan −$10,860342
  de flujo bruto antes de fees. No había BTC abierta. La cuenta tiene además
  10 acciones AAPL protegidas (valor $3.404,40 y P&L no realizado $1.457), que
  no pertenecen al bot. El equity de $101.434,50 no permite atribuir el P&L.
  `FEE`/`CFEE` devolvieron cero filas; falta reconciliar fees y ledger neto.
- En una consulta posterior, Alpaca devolvió 259 órdenes y 428 fills. La suma
  de `FILL.qty` fue 0,051141176 BTC en compras y 0,051013235 BTC en ventas,
  diferencia de 0,000127941 BTC (0,250172% de lo comprado), mientras el endpoint
  de posiciones reportó BTC plana. Es consistente con un fee de compra de
  0,25% cobrado en BTC recibido, pero todavía no es atribución confirmada.
  Alpaca documenta que `CFEE`/`FEE` puede publicarse al final del día. Con
  $4.271,02 vendidos, el fee de venta sería unos $10,68 si todo el volumen
  pertenece al primer tier y los fills IOC son taker; es una estimación, no
  un P&L neto observado. El flujo de fills fue −$10,95 antes de esa conciliación.
- El auditor exacto de pares cotizados enlazó 232 decisiones `HOT_SAMPLE`;
  102 órdenes acabaron `filled` y 130 `canceled`. La mediana del movimiento
  que activa la regla fue 1,510731 bps. Un análisis posterior de 389 fills en
  174 órdenes obtuvo respuestas direccionales medianas de +0,020714 bps,
  +0,040841 bps y +0,136072 bps en horizontes nominales de 1/5/30s. La
  cotización usada llegó tarde: mediana 2,600/3,028/3,015s tras cada objetivo
  y máximos de 84,964/80,964/75,940s. Se descarta interpretarlo como alpha;
  no incluye las actividades de fees y no es un backtest ejecutable.
- La evaluación cronológica read-only de Markov tiene 175 etiquetas forward:
  Brier 0,250335 contra 0,249947 del baseline constante congelado. El modelo
  no superó el baseline en esta muestra. Cero retornos de midpoint superaron
  el obstáculo nominal de 50 bps ida y vuelta por fee solamente. La muestra es
  corta y dependiente, y no usa bid/ask ni simula órdenes.
- La captura HIP-3 recibió 831.795 BBO y 86.816 actualizaciones de velas en
  14 contratos seleccionados; cada uno apareció en `allMids`. `xyz:EUR`
  emitió 152 actualizaciones de vela y `xyz:GBP` 26, evidencia de que no hay
  continuidad garantizada de velas por ese canal. El colector no tiene ruta de
  órdenes. Los 0 huecos de secuencia local solo se refieren a lo escrito.
- La política `quote_cross_30s_v1`, los límites paper y la arquitectura de
  solo lectura HIP-3 siguen sin cambios. La evaluación Markov no autoriza
  órdenes y los datos actuales no justifican llamar al sistema HFT ni cambiar
  tamaños. El auditor local pasó 24 pruebas; `e68e341` pasó GitHub Actions.
  La auditoría de markout se publicó después como `c88e3c0`.

## Estado operativo — 28 de septiembre, 10:29 UTC

- `c88e3c0` y `c147b25` ya están en `main`; monitor tests/typecheck/build,
  Dune build y suite OCaml pasaron en CI. El working tree quedó limpio.
- Snapshot firmado de 10:28:50 UTC: 199 órdenes BTC del bot con ejecución,
  435 fills y posición larga abierta de 0,000656018 BTC (marca $54,30). El
  flujo más inventario mostraba −$11,10 indicativo; el P&L neto cerrado sigue
  sin reconciliar.
- La venta de 10:28:03 se ejecutó parcialmente (0,000187863 BTC; 2 fills) y
  se canceló el resto. El broker no tenía órdenes abiertas, no quedaba diario
  durable pendiente y el servicio paper seguía activo sin reinicios.
- El inspector público mostró para esa orden quotes exactas, cruce bajista de
  1,805 bps, 8,971 ms de decisión, fills parciales y cancelación del remanente.
  El mercado de órdenes y las razones ya son visibles, aunque el balance sigue
  correctamente etiquetado como indicativo. La regla activa solo opera BTC en
  Alpaca paper; los 14 contratos HIP-3 continúan en captura read-only.

## Fuentes técnicas verificadas

- [Alpaca: límites de la simulación paper](https://docs.alpaca.markets/us/docs/paper-trading).
- [Alpaca: tasas crypto y registro diferido de fees](https://docs.alpaca.markets/us/docs/crypto-fees).
- [Hyperliquid: canales y formatos WebSocket](https://hyperliquid.gitbook.io/hyperliquid-docs/for-developers/api/websocket/subscriptions).
- [Hyperliquid: contratos HIP-3](https://hyperliquid.gitbook.io/hyperliquid-docs/hyperliquid-improvement-proposals-hips/hip-3-builder-deployed-perpetuals).

Los backtests antiguos se citan como registros históricos hasta reproducir sus
salidas. Paper/testnet y benchmarks locales no prueban rentabilidad live ni una
ventaja de latencia frente a participantes profesionales.

## Revisión del monitor y prioridad siguiente — 29 de septiembre de 2026

**Incidente observado:** a las 10:58 UTC el dashboard público conservaba una
foto del 28 de septiembre a las 12:47:29 UTC. El ejecutor y el feed Alpaca de
Dublín estaban activos, pero el timer de telemetría fallaba porque el JSON
firmado superaba 1 MiB. Por eso el visitante veía un sistema parado aunque el
paper bot y el colector seguían procesando el mercado.

**Actividad leída del broker, no inferida de la web:** el snapshot de solo
lectura de las 11:15 UTC contenía 148 órdenes BTC del bot enviadas desde las
00:00 UTC, 602 muestras quote-cross (149 candidatas, 453 no candidatas) y una
posición abierta de 0,001187307 BTC marcada a $99,72. La comprobación encontró
6 filas de órdenes repetidas en 635 filas descargadas; los IDs únicos eran
629. Por tanto, la lectura anterior de “no está haciendo trades” mezclaba dos
problemas reales: una UI congelada y un feed de actividad difícil de leer. El
conteo de candidatos no equivale al de órdenes ni al de fills.

**Cambio de producto publicado:** el commit `1a12f3b` se desplegó en `main` y
Vercel sirve la vista simplificada. El exporter compacto se instaló en Dublín y
se subió una foto firmada; la API pública devolvió `telemetryGeneratedAt`
`2026-09-29T11:30:48.873525Z` y `apiGeneratedAt` `2026-09-29T11:30:58.907Z`.
La pantalla mostró `FEED LIVE`, 630 IDs de órdenes BTC únicos, 1.079 fills,
192 eventos de journal retenidos, y ninguna equity global, posición AAPL ni
tabla de investigación. El journal indica que su ventana está incompleta. La
vista reportó -$25,94 como suma indicativa de cash de fills y marca abierta,
con el estado `P&L neto no conciliado`; no es P&L realizado ni después de fees.
El dato del snapshot, no vigente para una fecha posterior, mostraba 0,000710987
BTC y P&L no realizado del broker de +$0,03.

**Estado desplegado (29 sep 2026, 12:31 UTC):** `6c0d5e1` añade actividades
`CFEE`/`FEE` al resultado provisional; `846c39a` reduce el stale timeout de 20
a 10 minutos (dos heartbeats existentes) y mejora la lectura estrecha; `165bdb1`
corrige el monograma del encabezado. Verifiqué la versión pública y el API.
El snapshot de solo lectura `2026-09-29T12:31:21.917073Z` contiene 645 órdenes
del bot con historial completo, 1.095 fills, 996 fees `CFEE`, fees USD de
−$25,76 y −0,000281995 BTC en activo recibido. Las páginas están completas y
las fees se atribuyen al bot porque todo el historial crypto de la cuenta
corresponde a este bot. El flujo de cash de fills es −$26,100734; BTC marcado
es $0,00; el resultado provisional tras fees USD publicadas es −$51,860734.
La posición actual está plana, pero el inventario calculado desde fills y fees
difiere del broker en −0,000024511 BTC; el journal conserva una ventana
incompleta. No es P&L realizado ni conciliado.

**Alcance de la pantalla publicada:** muestra ese resultado y su desglose,
posición BTC, actividad de órdenes/fills y el motivo con las cotizaciones que
originaron la orden seleccionada. Quita equity/AAPL, activos ajenos, tarjetas
duplicadas de últimas operaciones, gráfico horario y tabla de velas de la
portada. El historial cuenta órdenes con fills, no rondas completas; hoy no
empareja entrada/salida ni enseña P&L neto realizado por ronda. Las velas,
Pattern Forge/Murphy y Markov siguen siendo contexto de investigación, no
motivo autorizado para enviar órdenes.

**Puertas antes de ampliar estrategia:**

1. Completar ledger de rondas por FIFO/posición, con fees en cada moneda,
   saldos iniciales y cada fill cronológico. Resolver el desfase actual de
   0,000024511 BTC. Hasta entonces, no anunciar P&L realizado/neto conciliado.
2. Medir por separado muestras elegibles, órdenes enviadas/aceptadas,
   cancelaciones, fills parciales/completos y marca temporal de cada decisión.
   El historial de órdenes no equivale a rondas cerradas.
3. Evaluar quote-cross, candles, Murphy y Markov con replay temporal causal,
   precios bid/ask que habrían sido ejecutables y fees observadas. Dejar la
   política actual inalterada hasta conocer los resultados netos.
4. Construir catálogo/cobertura multiactivo y replay HIP-3 como trabajo de
   captura aparte. No conectar acciones, FX-like, índices o energía al camino
   de órdenes mientras el adaptador, unidad y límites del contrato no estén
   validados.
5. Llamar al sistema HFT solo después de publicar un benchmark reproducible de
   throughput, pérdida de eventos, p50/p95/p99 y latencia de red/ack. El
   heartbeat de velas no es HFT y más órdenes paper no son evidencia de edge.

El paper bot continúa activo y ejecuta `quote_cross_30s_v1` solo en BTC/USD;
el nuevo monitor recibe telemetría firmada y fresca. Ya existe actividad
abundante para medir este disparador: más frecuencia/tamaño ahora amplía la
exposición al coste antes de demostrar edge. Añadir P&L realizado por ronda y
validar el replay after-cost va antes de más activos o autoridad de modelo.
