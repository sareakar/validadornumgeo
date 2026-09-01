# Integración FastAGI — contrato de la API

> Referencia técnica para el equipo que integra el dialplan de AsterVoIP
> con el validador telefónico centralizado (`telval`). Para el contexto
> completo del piloto (Ungar/`dycrecupero`) y las decisiones de
> arquitectura, ver [PRUEBA_AGI_LXC1324.md](PRUEBA_AGI_LXC1324.md).

---

## Servidor

| | |
|---|---|
| Host | `telval.centraltelefonica.com.ar` |
| Puerto | `4573/tcp` (FastAGI — protocolo AGI estándar de Asterisk, no HTTP) |
| Autenticación | Ninguna a nivel protocolo. Acceso hoy abierto a cualquier IP a nivel Docker — hardening de firewall pendiente (ver bitácora, sección "Hardening pendiente") |

---

## Cómo se invoca

Desde el dialplan, antes del `Dial()`:

```
AGI(agi://telval.centraltelefonica.com.ar:4573/validate,${ARG1},${ARG2},${ARG3},${ARG4})
```

| Arg | Nombre | Obligatorio | Descripción |
|-----|--------|:---:|--------------|
| `ARG1` | número | **sí** | El número a validar, en cualquier formato de entrada habitual (con o sin 0, con o sin 15, con o sin código de país, etc. — no hace falta limpiarlo antes) |
| `ARG2` | área por defecto | no (sin default) | Solo aplica a números de 7/6 dígitos (interior sin código de área). Un 7 dígitos **nunca puede ser AMBA**, así que no hay default sensato — sin `ARG2`, esos números salen inválidos en vez de asumir cualquier cosa |
| `ARG3` | `provider_key` | no | Clave de formato de salida — identifica qué formato final espera ESE trunk/proveedor (tabla abajo). Si se omite, el AGI se comporta igual que sin esta extensión (retrocompatible) |
| `ARG4` | `prefix` | no | String que se antepone literal al resultado final, por si el trunk necesita algo extra además del formato del `provider_key` |

---

## Qué devuelve (variables seteadas en el canal, vía `SET VARIABLE`)

| Variable | Ejemplo | Cuándo aparece |
|----------|---------|-----------------|
| `TELVAL_VALID` | `1` / `0` | siempre |
| `TELVAL_GEO` | `AMBA` / `Interior` | siempre (vacío si inválido) |
| `TELVAL_TIPO` | `mobile` / `landline` / `unknown` | siempre |
| `TELVAL_MODALIDAD` | `CPP` / `MPP` / `BASICA` | siempre |
| `TELVAL_OPERADOR` | `Movistar`, `Claro`, `Personal`, `Telecom`... | siempre |
| `TELVAL_AREA` | `11`, `351`... | siempre |
| `TELVAL_10DIG` | `1130032202` | siempre |
| `TELVAL_CON0` | `01130032202` | siempre |
| `TELVAL_CON015` | `0111530032202` | solo CPP/MPP |
| `TELVAL_E164` | `+541130032202` | siempre |
| `TELVAL_E164MOV` | `+5491130032202` | solo CPP/MPP |
| `TELVAL_CON9` | `91130032202` | solo CPP/MPP |
| `TELVAL_SOURCE` | `enacom_db` / `hint` / `heuristica` | siempre |
| `TELVAL_ERROR` | `formato_invalido` | solo si `TELVAL_VALID=0` |
| **`TELVAL_DIAL`** | `+5491130032202` | **solo si se mandó `ARG3`** — string final `prefix + formato_del_provider`, listo para pegar directo en `Dial()` |
| **`TELVAL_DIAL_ERROR`** | `` / `numero_invalido` / `provider_desconocido` | solo si se mandó `ARG3` |

---

## `provider_key` disponibles

Definidos en [providers.py](../providers.py) (`GET /providers` en la REST para consultarlos en caliente):

| `provider_key` | Fijo | Móvil | Notas |
|---|---|---|---|
| `simvoz` | `fmt_e164` | `fmt_e164_movil` | +54 fijo, +549 móvil |
| `claro` | `fmt_con_0` | `fmt_con_0` | 0 + 10 dígitos |
| `personal` | `fmt_con_0` | `fmt_con_0_15` | Fijo con 0, móvil 0+área+15 |
| `movistar` | `fmt_con_0` | `fmt_e164_movil` | Fijo con 0, móvil E.164 con 9 |
| `iplan` | `fmt_10dig` | `fmt_10dig` | 10 dígitos sin 0 ni + |
| `twilio` | `fmt_e164` | `fmt_e164_movil` | E.164 estándar |
| `voxbone` | `fmt_e164` | `fmt_e164_movil` | E.164 estándar |
| `voximplant` | `fmt_intl` | `fmt_intl_movil` | Sin +, con código de país |
| **`lineip`** | `fmt_intl` | `fmt_intl_movil` | **Agregado para el piloto Ungar** — fijo `54`+códLDN+número, móvil `549`+códLDN+número. Mismo formato que `voximplant` |
| `asterisk_local` | `fmt_asterisk` | `fmt_asterisk` | 10 dígitos, sin prefijo |
| `issabel` | `fmt_con_0` | `fmt_con_0` | 11 dígitos con 0 |
| `netvoip` | `fmt_e164` | `fmt_e164_movil` | E.164 |
| `generico_10` | `fmt_10dig` | `fmt_10dig` | 10 dígitos |
| `generico_e164` | `fmt_e164` | `fmt_e164_movil` | E.164 con +549 móvil |

---

## Ejemplo real (`lineip`)

```
$ echo '1130032202' | AGI ARG3=lineip
TELVAL_VALID      = 1
TELVAL_MODALIDAD  = CPP
TELVAL_OPERADOR   = Telecom
TELVAL_DIAL       = 5491130032202     ; móvil AMBA → 549 + 11 + 30032202
TELVAL_DIAL_ERROR = (vacío)
```

Fijo, mismo trunk: `1143219876` → `TELVAL_DIAL = 541143219876` (`54` + `11` + `43219876`, sin el `9` de móvil).

---

## Punto abierto para el equipo de arquitectura

El dialplan necesita saber, para cada trunk, **qué `provider_key` pasarle**
en `ARG3` (y opcionalmente qué `prefix` en `ARG4`). Hoy `macro-dialout`
(en `partesextensions/macros.conf` de cada cliente) ya lee por AstDB
campos como `${DB(${Trunk}/troncalActivo)}` y `${DB(${Trunk}/outCID)}`,
family = nombre literal del trunk (ej. `SIP/LineIP`).

Propuesta: sumar `${DB(${Trunk}/provider)}` al mismo lugar (mismo patrón,
sin tocar el schema de MySQL del panel). Como el panel web (`/pbx/` en
cada cliente) guarda la config de troncales en MySQL y no encontramos
todavía el paso que sincroniza esos campos hacia AstDB, queda a criterio
del equipo que conoce esa arquitectura decidir si:

- (a) se escribe directo en AstDB para probar (rápido, no toca el panel), o
- (b) se agrega `provider` como columna en la tabla de troncales del panel
  + el paso de sync correspondiente (más trabajo, pero queda administrable
  desde la UI para todos los clientes a futuro).
