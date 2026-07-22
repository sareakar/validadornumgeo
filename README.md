# Validador Telefónico AR

Validador y normalizador de números telefónicos argentinos para discadores y centrales Asterisk.

Clasifica números como fijo o móvil (CPP) usando la base oficial de ENACOM y genera todos los formatos que requiere cada carrier/proveedor.

---

## Contenido

- [Arquitectura](#arquitectura)
- [Instalación](#instalación)
  - [Opción A — Python directo (LXC Asterisk)](#opción-a--python-directo-lxc-asterisk)
  - [Opción B — Docker (servidor dedicado)](#opción-b--docker-servidor-dedicado)
- [Puertos](#puertos)
- [Árbol de decisión](#árbol-de-decisión)
- [Formatos de entrada soportados](#formatos-de-entrada-soportados)
- [Formatos de salida generados](#formatos-de-salida-generados)
- [Modo 1 — CLI (batch)](#modo-1--cli-batch)
- [Modo 2 — FastAGI (Asterisk)](#modo-2--fastagi-asterisk)
- [Modo 3 — REST API](#modo-3--rest-api)
- [Proveedores disponibles](#proveedores-disponibles)
- [Base ENACOM](#base-enacom)
- [Actualizar la base ENACOM](#actualizar-la-base-enacom)

---

## Arquitectura

```
                        ┌─────────────────────────────────┐
                        │         validator.py             │
                        │   (motor de validación core)     │
                        │                                  │
                        │  1. Limpieza de prefijos         │
                        │  2. Clasificación AMBA/Interior  │
                        │  3. Completado a 10 dígitos      │
                        │  4. Lookup ENACOM → CPP/BASICA   │
                        │  5. Generación de formatos       │
                        └────────────┬────────────────────┘
                                     │
              ┌──────────────────────┼──────────────────────┐
              │                      │                      │
       ┌──────▼──────┐       ┌───────▼──────┐      ┌───────▼──────┐
       │   main.py   │       │  fastagi.py  │      │    api.py    │
       │  CLI batch  │       │  TCP :4573   │      │  HTTP :8080  │
       │             │       │  Asterisk    │      │  REST JSON   │
       └─────────────┘       └──────────────┘      └──────────────┘
```

**Archivos del proyecto:**

| Archivo | Función |
|---------|---------|
| `validator.py` | Motor principal: parseo, clasificación, formatos |
| `numgeo.py` | Lookup en base ENACOM (48.903 bloques en memoria) |
| `ar_numbering.py` | Fallback heurístico cuando ENACOM no cubre el número |
| `providers.py` | Definición de carriers y sus formatos |
| `main.py` | CLI para procesamiento batch de archivos |
| `fastagi.py` | Servidor FastAGI para Asterisk dialplan |
| `api.py` | Servidor REST HTTP |
| `server.py` | Arranca FastAGI + REST en paralelo |
| `data/numgeo_enacom.csv` | Base de numeración ENACOM exportada |

---

## Instalación

El servicio expone tres interfaces que conviven en la misma instalación:

| Puerto | Protocolo | Uso |
|--------|-----------|-----|
| `4573` | TCP | FastAGI — dialplan Asterisk |
| `8080` | HTTP | REST API + Web UI |

> Verificar disponibilidad antes de instalar:
> ```bash
> ss -tlnp | grep -E '4573|8080'
> ```
> Si alguno está ocupado, ajustar los puertos en `telval.service` o `docker-compose.yml`.

---

### Opción A — Python directo (LXC Asterisk)

Recomendado para LXC sin soporte de virtualización anidada. Ver [INSTALL.md](INSTALL.md) para instrucciones detalladas.

```bash
# 1. Clonar
git clone https://gitea.centraltelefonica.com.ar/jmazzini/validadornumgeo.git /opt/telval
cd /opt/telval

# 2. Instalar dependencias
python3 -m pip install -r requirements.txt

# 3. Instalar y arrancar el servicio
cp telval.service /etc/systemd/system/
systemctl daemon-reload
systemctl enable --now telval

# 4. Verificar
systemctl status telval
curl http://localhost:8080/health
```

---

### Opción B — Docker (servidor dedicado)

Recomendado para servidores con Docker disponible (ej: infra-apps). Ver [DEPLOY.md](DEPLOY.md) para instrucciones detalladas incluyendo Caddy como proxy inverso.

```bash
# 1. Clonar
git clone https://gitea.centraltelefonica.com.ar/jmazzini/validadornumgeo.git /opt/validadornumgeo
cd /opt/validadornumgeo

# 2. Levantar
docker compose up -d --build

# 3. Verificar
curl http://localhost:8181/health
```

El `docker-compose.yml` mapea el puerto `8181` del host al `8080` del contenedor para evitar conflictos. Ajustar si es necesario.

Para exponer con HTTPS agregar en el Caddyfile:
```caddy
telval.astervoip.com.ar {
    reverse_proxy localhost:8181
}
```

---

## Árbol de decisión

El validador procesa cada número en 5 pasos ordenados:

```
ENTRADA: número en cualquier formato
    │
    ▼
PASO 1 — LIMPIEZA
    Quita: espacios, guiones, paréntesis, puntos
    Quita: +54 / 54 / +549 / 549 / 0054 / 0 (troncal)
    Nota: +549 y 549 → hint=mobile | +54 y 54 → sin hint (ENACOM decide)
    │
    ▼
PASO 2 — CLASIFICACIÓN AMBA / INTERIOR
    ┌──────────────────────────────────────────────────────────────────────────┐
    │ Longitud │ Prefijo / patrón       │ Resultado                           │
    ├──────────────────────────────────────────────────────────────────────────┤
    │ 8 dig    │ cualquiera             │ AMBA (área 11 — única área 2-dig AR)│
    │ 10 dig   │ empieza "11"           │ AMBA (ya tiene área)                │
    │ 10 dig   │ empieza "15"           │ AMBA móvil (strip "15", prepende 11)│
    │ 12 dig   │ empieza "1115"         │ AMBA móvil (11+15+8dig)             │
    │ 12 dig   │ empieza "1511"         │ AMBA móvil (15+11+8dig)             │
    │ 12 dig   │ [área3]"15"[sub7]      │ Interior móvil (15 DESPUÉS del área)│
    │          │  ej: 351-15-6551221    │ → strip "15" del medio              │
    │ 12 dig   │ [área4]"15"[sub6]      │ Interior móvil (15 DESPUÉS del área)│
    │          │  ej: 2233-15-655122    │ → strip "15" del medio              │
    │ 12 dig   │ "15"[área3][sub7]      │ Interior móvil (15 ANTES del área)  │
    │          │  ej: 15-351-6551221    │ → strip "15" del frente             │
    │ 12 dig   │ "15"[área4][sub6]      │ Interior móvil (15 ANTES del área)  │
    │          │  ej: 15-2233-655122    │ → strip "15" del frente             │
    │ 7 dig    │ cualquiera             │ Interior (necesita --default-area)  │
    │ 10 dig   │ otros                  │ Interior (área 3 o 4 dígitos)       │
    └──────────────────────────────────────────────────────────────────────────┘

    Nota: el "0" troncal se quita siempre antes de este paso.
    "015[área][sub]" (13 dig) → strip 0 → "15[área][sub]" (12 dig) → caso interior
    "0[área]15[sub]" (13 dig) → strip 0 → "[área]15[sub]" (12 dig) → caso interior
    │
    ▼
PASO 3 — COMPLETADO A 10 DÍGITOS
    AMBA 8 dig              → prepende "11"
    AMBA 15+8               → quita "15", prepende "11", marca mobile
    Interior [área]15[sub]  → quita "15" del medio, marca mobile
    Interior 15[área][sub]  → quita "15" del frente, marca mobile
    Interior normal         → parsea área (3 o 4 dígitos)
    │
    ▼
PASO 4 — LOOKUP ENACOM (48.903 bloques)
    Prioridad: hint de formato > base ENACOM > heurística
    Resultado: CPP | MPP | BASICA + operador + localidad

    Desambiguación 3 vs 4 dígitos de área:
    En Argentina existen áreas de 3 dígitos (ej: 383) y áreas de 4 dígitos que
    empiezan con los mismos 3 dígitos (ej: 3832). Un número como 3832414526
    es ambiguo: podría ser área 383 + sub 2414526, o área 3832 + sub 414526.

    Resolución: si ENACOM no encuentra bloque con área de 3 dígitos,
    se reintenta con 4 dígitos. El que tenga cobertura en ENACOM gana.

    Ejemplo real:
      5493832414526 → strip 549 → 3832414526
      Intento 1: área 383, sub 2414526 → ENACOM: sin datos
      Intento 2: área 3832, sub 414526  → ENACOM: Claro CPP ✓
      fmt_con_0_15 correcto: 0383215414526
    │
    ▼
PASO 5 — GENERACIÓN DE FORMATOS
    Genera todos los formatos de salida según tipo de línea
```

---

## Formatos de entrada soportados

El validador acepta **cualquier formato** habitual en bases de datos argentinas:

| Formato entrada | Ejemplo | Interpretación |
|----------------|---------|----------------|
| 8 dígitos (AMBA local) | `65512215` | AMBA → `1165512215` |
| 10 dígitos completo | `1130032202` | AMBA directo |
| Con 0 troncal | `01130032202` | Quita el 0 |
| Con 0 + área + 15 (AMBA) | `011-15-6551-2215` | AMBA móvil |
| Con 1115 (redundante) | `1115-6551-2215` | AMBA móvil |
| Con 1511 (invertido) | `1511-1300-3220` | AMBA móvil |
| Interior fijo completo | `3514123456` | Interior (área 351) |
| Interior fijo con 0 | `03514123456` | Interior (quita 0) |
| Interior móvil área+15+sub | `0351-15-6551221` | Interior móvil → `3516551221` |
| Interior móvil área+15+sub | `351-15-6551221` | Interior móvil → `3516551221` |
| Interior móvil 15+área+sub | `15-351-6551221` | Interior móvil → `3516551221` |
| Interior móvil 015+área+sub | `015-351-6551221` | Interior móvil → `3516551221` |
| Área 4 dig ambigua | `5493832414526` | strip 549 → `3832414526`, ENACOM resuelve área 3832 vs 383 |
| E.164 con + | `+541130032202` | Sin hint (ENACOM decide) |
| E.164 móvil | `+5491130032202` | Móvil (hint por 9) |
| Sin + con 54 | `541130032202` | Sin hint (ENACOM decide) |
| Sin + con 549 | `5491130032202` | Móvil (hint por 9) |
| Con separadores | `011 1234-5678` | Normalizado |
| Con 0054 | `00541143219876` | Internacional |

---

## Formatos de salida generados

Para cada número válido el sistema genera **9 formatos simultáneos**:

| Campo | Descripción | Ejemplo (móvil AMBA) | Ejemplo (fijo AMBA) |
|-------|-------------|---------------------|---------------------|
| `fmt_10dig` | 10 dígitos nacionales | `1165512215` | `1143219876` |
| `fmt_con_0` | Con 0 troncal (11 dig) | `01165512215` | `01143219876` |
| `fmt_con_0_15` | Con 0+área+15 (CPP) | `0111565512215` | `01143219876` |
| `fmt_con_9` | Con 9 de móvil | `91165512215` | `1143219876` |
| `fmt_e164` | E.164 estándar | `+541165512215` | `+541143219876` |
| `fmt_e164_movil` | E.164 con 9 de móvil | `+5491165512215` | `+541143219876` |
| `fmt_intl` | Internacional sin + | `541165512215` | `541143219876` |
| `fmt_intl_movil` | Internacional sin + con 9 | `5491165512215` | `541143219876` |
| `fmt_asterisk` | Para dialplan (=10dig) | `1165512215` | `1143219876` |

> Los formatos marcados como "CPP" solo se populan cuando ENACOM confirma modalidad CPP o MPP. Para BASICA (fijo), `fmt_con_0_15` devuelve el mismo valor que `fmt_con_0`.

---

## Modo 1 — CLI (batch)

Procesar archivos CSV, TXT o Excel con listas de números.

### Uso básico

```bash
cd /opt/telval

# Validar números sueltos
python3 main.py validate 1130032202 65512215 02234513883

# Ver todos los formatos de un número
python3 main.py validate 1130032202 --all-formats

# Procesar archivo CSV (salida completa con todos los campos)
python3 main.py file lista.csv --output salida.csv

# Exportar listo para importar en un carrier/discador específico
python3 main.py export lista.csv simvoz           # → lista_simvoz.csv
python3 main.py export lista.csv vicidial         # → lista_vicidial.csv
python3 main.py export lista.csv astervoip        # → lista_astervoip.csv
python3 main.py export lista.csv personal --only-valid -o para_personal.csv

# Ver carriers y discadores disponibles
python3 main.py providers

# Ver estado de la base ENACOM
python3 main.py stats
```

### Subcomando `export` — exportación lista para carrier o discador

El subcomando `export` genera un CSV con la estructura exacta que espera cada sistema:

```bash
python3 main.py export <archivo> <carrier_o_discador> [opciones]

  --column / -c         Columna donde está el número
  --output / -o         Archivo de salida (default: <entrada>_<provider>.csv)
  --only-valid          Omitir inválidos (default: se incluyen como fila vacía)
  --default-area / -a   Área para números incompletos (default: 11)
```

| Carrier/Discador | Columna del número | Columnas extra incluidas |
|-----------------|-------------------|--------------------------|
| `simvoz` | `numero` (+549...) | tipo, modalidad, operador |
| `claro` | `numero` (0...) | tipo, modalidad, operador, localidad |
| `personal` | `numero` (0+área+15 móvil) | tipo, modalidad, operador, localidad |
| `movistar` | `numero` (+549 móvil) | tipo, modalidad, operador, localidad |
| `astervoip` | `telefono` | tipo, modalidad, operador, localidad, nombre, apellido, campana, agente, extra1, extra2 |
| `vicidial` | `phone_number` | 20 columnas estándar Vicidial (list_id, first_name…, status=NEW, called_count=0) |
| `goautodial` | `phone_number` | 18 columnas GoAutodial |

### Opciones

| Opción | Descripción | Default |
|--------|-------------|---------|
| `--provider` / `-p` | Carrier de salida (agrega columna con formato del carrier) | ninguno |
| `--column` / `-c` | Columna del número en CSV/Excel (nombre o índice) | primera columna |
| `--output` / `-o` | Archivo CSV de salida (si no se especifica: pantalla) | pantalla |
| `--only-valid` | Excluir números inválidos del CSV de salida | no |
| `--all-formats` / `-f` | Mostrar/incluir todos los formatos | no |
| `--default-area` / `-a` | Área a asumir para números de 7 dígitos (interior) | `11` |

### Columnas del CSV de salida

```
original, valido, geografia, tipo, modalidad, area, abonado, provincia, ciudad,
operador, servicio, fuente, reparado, nota_reparacion, error,
fmt_10dig, fmt_con_0, fmt_con_0_15, fmt_con_9,
fmt_e164, fmt_e164_movil, fmt_intl, fmt_intl_movil, fmt_asterisk
```

---

## Modo 2 — FastAGI (Asterisk)

El servidor FastAGI permite que el dialplan valide números en tiempo real.

### Iniciar el servidor

```bash
# Ambos servicios (FastAGI + REST)
python3 server.py

# Solo FastAGI
python3 server.py --only-agi

# Para acceso externo (desde otro servidor Asterisk)
python3 server.py --agi-host 0.0.0.0

# Con systemd (recomendado)
systemctl start telval
```

### Integración en el dialplan

```
; Llamada mínima — valida ${EXTEN} asumiendo área 11 para números cortos
exten => _X.,1,AGI(agi://127.0.0.1:4573/validate,${EXTEN})
 same => n,GotoIf($["${TELVAL_VALID}" != "1"]?invalido)
 same => n,GotoIf($["${TELVAL_MODALIDAD}" = "CPP"]?cpp)
 same => n,GotoIf($["${TELVAL_MODALIDAD}" = "MPP"]?cpp)
 ; Fijo
 same => n,Dial(SIP/${TELVAL_CON0}@trunk_fijo)
 same => n,Hangup()
 ; Móvil CPP/MPP
 same => n(cpp),Dial(SIP/${TELVAL_CON015}@trunk_movil)
 same => n,Hangup()
 ; Inválido
 same => n(invalido),Hangup()

; Para números de interior con área 351 (Córdoba) como default
exten => _X.,1,AGI(agi://127.0.0.1:4573/validate,${EXTEN},351)
```

### Variables que devuelve el AGI

| Variable | Valores | Descripción |
|----------|---------|-------------|
| `TELVAL_VALID` | `1` / `0` | Si el número es válido |
| `TELVAL_GEO` | `AMBA` / `Interior` | Zona geográfica |
| `TELVAL_TIPO` | `mobile` / `landline` / `unknown` | Tipo de línea |
| `TELVAL_MODALIDAD` | `CPP` / `MPP` / `BASICA` / `` | Modalidad ENACOM |
| `TELVAL_OPERADOR` | `Movistar` / `Claro` / `Personal` / `Telecom` / ... | Operador |
| `TELVAL_AREA` | `11` / `351` / ... | Código de área |
| `TELVAL_10DIG` | `1130032202` | Formato 10 dígitos |
| `TELVAL_CON0` | `01130032202` | Con 0 troncal |
| `TELVAL_CON015` | `0111530032202` | Con 0+área+15 (solo CPP/MPP) |
| `TELVAL_E164` | `+541130032202` | E.164 estándar |
| `TELVAL_E164MOV` | `+5491130032202` | E.164 con 9 de móvil (solo CPP/MPP) |
| `TELVAL_CON9` | `91130032202` | Con 9 de móvil (solo CPP/MPP) |
| `TELVAL_SOURCE` | `enacom_db` / `hint` / `heuristica` | Fuente de clasificación |
| `TELVAL_ERROR` | `formato_invalido` / ... | Descripción del error (si VALID=0) |

### Pasar a modo externo

Cuando el validador corre en un servidor dedicado, solo hay que:

1. En el servidor validador: `python3 server.py --agi-host 0.0.0.0`
2. En el dialplan de Asterisk: cambiar `127.0.0.1` por la IP del servidor
   ```
   AGI(agi://192.168.1.100:4573/validate,${EXTEN})
   ```

---

## Modo 3 — REST API

Permite integración desde cualquier sistema vía HTTP.

### Iniciar

```bash
python3 server.py --only-api    # solo REST en :8080
python3 server.py               # REST + FastAGI juntos
```

### Endpoints

#### `GET /validate` — Validar un número

```bash
curl "http://localhost:8080/validate?number=1130032202&provider=simvoz"
```

Parámetros:
- `number` *(requerido)* — número a validar (cualquier formato)
- `provider` *(opcional)* — carrier para formato específico (ver `/providers`)
- `default_area` *(opcional, default: `11`)* — área para números incompletos

Respuesta:
```json
{
  "valid": true,
  "original": "1130032202",
  "geografia": "AMBA",
  "tipo": "mobile",
  "modalidad": "CPP",
  "operador": "Telecom",
  "area": "11",
  "localidad": "AMBA",
  "source": "enacom_db",
  "repaired": false,
  "error": null,
  "formats": {
    "fmt_10dig":      "1130032202",
    "fmt_con_0":      "01130032202",
    "fmt_con_0_15":   "0111530032202",
    "fmt_con_9":      "91130032202",
    "fmt_e164":       "+541130032202",
    "fmt_e164_movil": "+5491130032202",
    "fmt_intl":       "541130032202",
    "fmt_intl_movil": "5491130032202",
    "fmt_asterisk":   "1130032202"
  },
  "fmt_provider": "+5491130032202"
}
```

#### `POST /validate/batch` — Validar lista de números

```bash
curl -X POST http://localhost:8080/validate/batch \
  -H "Content-Type: application/json" \
  -d '{"numbers": ["1130032202", "65512215", "1234"], "provider": "simvoz"}'
```

Body JSON:
- `numbers` *(requerido)* — lista de números (máx. 10.000)
- `provider` *(opcional)* — carrier de salida
- `default_area` *(opcional, default: `11`)*

Respuesta:
```json
{
  "total": 3,
  "valid": 2,
  "invalid": 1,
  "results": [ ... ]
}
```

#### `GET /providers` — Lista de carriers disponibles

```bash
curl http://localhost:8080/providers
```

#### `GET /stats` — Estado de la base ENACOM

```bash
curl http://localhost:8080/stats
# {"total_bloques": 48903, "indicativos": 300, "movil": 35246, "fijo": 13604}
```

#### `GET /health` — Health check

```bash
curl http://localhost:8080/health
# {"status": "ok", "enacom_db": true}
```

---

## Proveedores disponibles

| Clave | Carrier | Fijo usa | Móvil (CPP) usa |
|-------|---------|----------|-----------------|
| `simvoz` | Simvoz | `fmt_e164` | `fmt_e164_movil` (+549) |
| `claro` | Claro AR | `fmt_con_0` | `fmt_con_0` (0+10dig) |
| `personal` | Personal/Telecom | `fmt_con_0` | `fmt_con_0_15` (0+área+15) |
| `movistar` | Movistar AR | `fmt_con_0` | `fmt_e164_movil` (+549) |
| `iplan` | IPLAN | `fmt_10dig` | `fmt_10dig` |
| `twilio` | Twilio | `fmt_e164` | `fmt_e164_movil` |
| `voxbone` | Voxbone/Bandwidth | `fmt_e164` | `fmt_e164_movil` |
| `voximplant` | Voximplant | `fmt_intl` | `fmt_intl_movil` |
| `asterisk_local` | Asterisk genérico | `fmt_asterisk` | `fmt_asterisk` |
| `issabel` | Issabel/FreePBX | `fmt_con_0` | `fmt_con_0` |
| `netvoip` | Net2Phone | `fmt_e164` | `fmt_e164_movil` |
| `generico_10` | Genérico 10 dígitos | `fmt_10dig` | `fmt_10dig` |
| `generico_e164` | Genérico E.164 | `fmt_e164` | `fmt_e164_movil` |

Para agregar un carrier nuevo, editar `providers.py` y agregar una entrada al dict `PROVIDERS`.

---

## Base ENACOM

La clasificación fijo/móvil se resuelve consultando la base oficial de ENACOM (Plan Nacional de Numeración).

**Fuente de datos:** `data/numgeo_enacom.csv` — exportado de *Numeración Geográfica.xls* descargado de [enacom.gob.ar](https://www.enacom.gob.ar/numeracion_p5.html).

**Cobertura actual:**
- 48.903 bloques de numeración
- 300 códigos de área
- 35.246 bloques móvil (CPP/MPP)
- 13.604 bloques fijo (BASICA)

**Prioridad de clasificación:**

| Prioridad | Fuente | Cuándo aplica |
|-----------|--------|---------------|
| 1 | Hint de formato (`hint`) | El número vino con `+549`, `549`, prefijo `15`, o `1115` |
| 2 | Base ENACOM (`enacom_db`) | Se encontró el bloque en el CSV |
| 3 | Heurística (`heuristica`) | Bloque no está en ENACOM (base desactualizada) |

La columna `fuente` en la salida indica cuál se usó.

## Actualizar la base ENACOM

Cuando ENACOM publique una versión nueva del archivo XLS:

```bash
# 1. Descargar el nuevo XLS de enacom.gob.ar y copiarlo al servidor
cp "Numeración Geográfica.xls" /opt/telval/data/numgeo_enacom_nuevo.xls

# 2. Convertir a CSV con el script Node.js
cd /workspace/xlsconv
# Editar convert.js para apuntar al nuevo archivo
node convert.js

# 3. Reemplazar el CSV y reiniciar el servicio
cp /workspace/validadortelefonico/data/numgeo_enacom.csv /opt/telval/data/
systemctl restart telval
```
