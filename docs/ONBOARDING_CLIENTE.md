# Procedimiento: integrar telval en un cliente AsterVoIP nuevo

Runbook consolidado a partir de 3 integraciones reales (Ungar/
dycrecupero, Nexo, Resermap — detalle narrativo de cada una en
[PRUEBA_AGI_LXC1324.md](PRUEBA_AGI_LXC1324.md)). Usar **siempre** el
mecanismo dinámico (sección 3) salvo que el cliente tenga un solo trunk
confirmado y no valga la pena el trabajo extra — ver criterio en el
paso 2.

## 0. Acceso

- SSH al cliente: `soporte@<cliente>.centraltelefonica.com.ar:2022`
  (password, no key).
- Confirmar si `soporte` tiene `sudo` sin password (`sudo -n true`).
  - **Si sí** (Ungar, Nexo): se puede automatizar todo por SSH.
  - **Si no** (Resermap): no asumir que se puede agregar a sudoers — es
    una decisión del cliente/usuario, preguntar antes de tocar
    `/etc/sudoers.d/`. Si dice que no, el flujo pasa a ser
    colaborativo: el usuario abre su propia sesión `su -` y pega los
    comandos/resultados que se necesiten.
- Primer contacto con un host nuevo: `ssh-keyscan -p 2022 -t ed25519,rsa
  <host>`, mostrar el fingerprint SHA256 al usuario para confirmar antes
  de agregarlo a `known_hosts`.

## 1. Relevar el dialplan

```bash
grep -n "^\[macro-dialout" /etc/asterisk/partesextensions/macros.conf
grep -n "Macro(dialout" /etc/asterisk/pbx/permisos.conf
find /etc/asterisk -name "*.conf*" -mtime -30
```

- Ubicar el/los `Dial()` real(es) en `macro-dialout` y
  `macro-dialout-discadores` — son los puntos de inserción.
- El `find -mtime -30` es para pescar parches temporales de otra persona
  antes de tocar nada (pasó en Nexo — un colega había puesto un parche
  manual justo antes del `Dial()`, había que sacarlo primero).
- Anotar el mecanismo con el que `${Trunk}` llega al `Dial()` — en las
  3 integraciones hechas hasta ahora es
  `Set(Trunk=${CUT(AVAILORIGCHAN,,1)})` en el label `disponibilidad`,
  pero no asumir, confirmar con
  `asterisk -rx "dialplan show macro-dialout" | grep -n "Trunk=\|Dial("`.

## 2. Contar trunks reales

```bash
grep -n "Macro(dialout" /etc/asterisk/pbx/permisos.conf
```

Mirar el segundo argumento de cada `Macro(dialout,...)` (`cantTrunk`) **y**
cuántos trunks distintos (`SIP/X`) aparecen en total en el archivo, no
solo por línea:

- **Un solo trunk en todo el archivo** (Ungar, Nexo): el
  `provider_key` hardcodeado en el texto del dialplan es válido y más
  simple — saltar a la sección 4 (patrón hardcodeado).
- **Más de un trunk** (Resermap: Metrotel + FonoIP; o `cantTrunk` > 1 en
  algún patrón, failover real): hardcodear es **incorrecto** — un solo
  macro puede servir tráfico que no debe pasar por telval (ej. rutas a
  otro país) o que necesita un formato distinto según qué trunk se use
  en cada intento. Ir a la sección 3.

## 3. Patrón dinámico (recomendado, estándar desde Resermap)

### 3.1 Confirmar el formato real de cada trunk en alcance

Sin asumir por el nombre del carrier. Armar (o pedirle al cliente) un
dialplan de prueba tipo `_X.` que pase el número tal cual al trunk sin
transformarlo, y probar con números reales:

- Fijo AMBA, móvil AMBA, fijo interior, móvil interior — mínimo.
- Confirmar contra `providers.py`: ¿ya existe una key con ese formato
  exacto (`landline_format`/`mobile_format`)? Si sí, no crear una nueva
  — pero si el carrier es distinto al que la creó originalmente, sí
  crear una key nueva con el mismo formato (mismo criterio que
  `lineip`/`voximplant` y `metrotel`/`nexo`: no reusar por nombre,
  reusar por formato, pero con identidad propia).

### 3.2 Encontrar la tabla MySQL de trunks del cliente

```bash
mysql -u root -p -e "show databases;"
# la mas probable es "asterisk"; en cada db candidata:
mysql -u root -p -e "show tables like '%sip%'; show tables like '%trunk%'; show tables like '%troncal%'; show tables like '%prove%';" <db>
```

En Resermap fue `asterisk.id_proveedor` (columna `name` = nombre del
trunk sin `SIP/`, y ya tenía columnas reflejadas en AstDB —
`chanisavail`, `activo`, `ocupado` — buena señal de que es la tabla
correcta). Puede tener otro nombre en otro cliente.

### 3.3 Agregar la columna

```sql
ALTER TABLE <tabla> ADD COLUMN telval_provider VARCHAR(40) NOT NULL DEFAULT '';
UPDATE <tabla> SET telval_provider='<provider_key>' WHERE name='<NombreTrunk>';
```

Plantilla en [`agi-scripts/migration.sql.example`](../agi-scripts/migration.sql.example).
Default `''` = trunk sin asignar → el dialplan no consulta telval para
ese trunk, sigue directo al `Dial()` de siempre. Dejar sin asignar
cualquier trunk fuera de alcance (ej. rutas a otro país).

### 3.4 Instalar el script de lookup

Copiar [`agi-scripts/telvalTrunkProvider.agi`](../agi-scripts/telvalTrunkProvider.agi)
a `/var/lib/asterisk/agi-bin/pbx-ip/` en el cliente (mismo directorio
que usan los demás `.agi` de AsterVoIP, ej. `claveRuta.agi`). Ajustar el
`SELECT` si la tabla/columna del paso 3.2 tiene otro nombre.

```bash
chown asterisk:asterisk /var/lib/asterisk/agi-bin/pbx-ip/telvalTrunkProvider.agi
chmod 755 /var/lib/asterisk/agi-bin/pbx-ip/telvalTrunkProvider.agi
perl -c /var/lib/asterisk/agi-bin/pbx-ip/telvalTrunkProvider.agi   # valida sintaxis
```

El script reusa el helper de conexión a MySQL que ya usan los demás
`.agi` de la plataforma (`use lib("/var/www/pbx/Phps/Comunes"); use
dataDB; dameConfig()`) — no hace falta ver ni hardcodear la password.
Si el cliente no tiene ese módulo (`dataDB.pm`) en esa ruta, ubicar cómo
conectan a MySQL sus otros `.agi` y adaptar.

### 3.5 Insertar el bloque en el dialplan

Justo antes de cada `Dial(${Trunk}/${Prefix}${Numero},...)`
(`macro-dialout` y `macro-dialout-discadores`, label distinto en cada
uno):

```
same => n,AGI(pbx-ip/telvalTrunkProvider.agi,${Trunk})
same => n,GotoIf($["${TelvalProvider}" = ""]?telval_skip_dialout)
same => n,AGI(agi://telval.centraltelefonica.com.ar:4573/validate,${Prefix}${Numero},11,${TelvalProvider})
same => n,GotoIf($["${TELVAL_DIAL}" = ""]?telval_skip_dialout)
same => n,Verbose(1,TELVAL: ${Prefix}${Numero} -> ${TELVAL_DIAL} [${TELVAL_GEO} ${TELVAL_TIPO} ${TELVAL_MODALIDAD}])
same => n,Set(Prefix=)
same => n,Set(Numero=${TELVAL_DIAL})
same => n(telval_skip_dialout),Dial(${Trunk}/${Prefix}${Numero},${Tods},${Ods}M(${macroCRM}))
```

**Usar `${Prefix}${Numero}` como input, no `${NumeroReal}`** — salvo que
se confirme que no hay patrones de atajo local (tipo `_8XXXXXX.` en
Resermap) que dejen un dígito de ruteo pegado al número crudo. Motivo:
`${NumeroReal}` sin recortar puede hacer que el validador interprete
mal un atajo interno como un número real (probado localmente antes de
aplicar en Resermap — ver bitácora). `${Prefix}${Numero}` es lo que el
`permisos.conf` de cada patrón ya arma hoy, con esos dígitos de ruteo ya
sacados.

**Aplicar en 3 pasos** (cada uno con backup previo y diff mostrado antes
del siguiente):
1. Solo el `AGI(pbx-ip/telvalTrunkProvider.agi,...)` + un
   `NoOp(TELVAL: TelvalProvider=${TelvalProvider} para Trunk=${Trunk})`
   — sin tocar `Prefix`/`Numero` — y una llamada real para confirmar que
   el lookup resuelve bien.
2. El bloque completo en `macro-dialout`, probado con llamada real.
3. Mismo bloque en `macro-dialout-discadores`.

Para el reemplazo de texto exacto (`macros.conf` es de `asterisk:asterisk`,
normalmente no editable por `soporte`), usar un script chico (Perl si no
hay Python en el cliente) que cuenta ocurrencias del bloque ancla y
aborta si no es exactamente 1 — evita errores de escaping de `su -c
"..."` anidado y ediciones a ciegas. Ver ejemplos de estos scripts en el
historial de la bitácora.

## 4. Patrón hardcodeado (solo si un solo trunk confirmado)

```
same => n,AGI(agi://telval.centraltelefonica.com.ar:4573/validate,${Prefix}${Numero},11,<provider_key>)
same => n,GotoIf($["${TELVAL_DIAL}" != ""]?telval_ok)
same => n,Goto(telval_skip)
same => n(telval_ok),Set(Prefix=)
same => n,Set(Numero=${TELVAL_DIAL})
same => n(telval_skip),Dial(${Trunk}/${Prefix}${Numero},${Tods},${Ods}M(${macroCRM}))
```

Más simple, sin dependencias de MySQL — pero **si el cliente después
agrega un segundo trunk, hay que migrar a la sección 3**. Ungar y Nexo
quedaron con este patrón; migrarlos al dinámico es un pendiente propio
(no urgente, no bloquea nada).

## 5. Después de aplicar (ambos patrones)

- `asterisk -rx "dialplan reload"`, confirmar sin errores.
- Llamada real de prueba: fijo y móvil, AMBA e interior si el cliente
  tiene tráfico de interior.
- Actualizar `client_configs/<cliente>/README.md` (local, gitignored)
  con lo específico de ese cliente — trunks, formato confirmado, tabla
  MySQL usada, backups dejados en el server.
- Agregar una entrada nueva en [PRUEBA_AGI_LXC1324.md](PRUEBA_AGI_LXC1324.md)
  con el resumen (fecha, trunks, bugs encontrados si los hay).
