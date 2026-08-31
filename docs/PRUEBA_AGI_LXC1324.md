# Bitácora — Prueba de integración AGI en LXC cliente (1324)

> **Actualización 2026-08-31**: el piloto real se corre directo sobre el
> cliente **Ungar** (`dycrecupero.centraltelefonica.com.ar`, puerto 2022,
> user `soporte`), **en producción**, con un interno de pruebas aislado —
> no sobre un clon local del LXC 1324. Se mantiene este documento (mismo
> proyecto, mismo objetivo) en vez de abrir uno nuevo; ver sección
> "Piloto Ungar" más abajo para el estado vigente.

> Documento vivo. Objetivo: validar el validador telefónico (`telval`) contra
> un dialplan real de Asterisk en un entorno de pruebas, para después
> reproducir el mismo cambio en el dialplan de producción del cliente.
> Cada paso se documenta a medida que se ejecuta, con fecha y resultado.

---

## Objetivo

1. Clonar/restaurar el LXC de Asterisk del cliente (**ID 1324**) en un entorno
   de pruebas dentro del cluster Proxmox propio (no en un LXC de cliente en
   producción, no en la red doméstica — IP dinámica descartada).
2. Apuntar el dialplan de ese clon a la instancia **ya desplegada** del
   validador (no se instala una nueva) para probar FastAGI en modo externo.
3. Validar las variables `TELVAL_*` que devuelve el AGI contra números reales
   del cliente.
4. Documentar cada cambio (firewall, dialplan, config) para poder aplicarlo
   después en el LXC de producción del cliente.

---

## Arquitectura decidida

**FastAGI centralizado ("modo externo"), no instalación local por LXC, no REST.**

Motivo (ya documentado en [README.md](../README.md#pasar-a-modo-externo) /
[INSTALL.md](../INSTALL.md#modo-externo-validador-en-servidor-dedicado)):

- El dialplan ya habla AGI nativo (`AGI(agi://host:4573/validate,${EXTEN})`),
  sin necesidad de `System()`/`CURL()` + parseo JSON en el dialplan.
- Hay decenas de LXC de clientes (ver `~/.ssh/config`: astervoip, hfa, balat,
  muller, farmacity, etc.). Un único servicio centralizado evita reinstalar y
  mantener la base ENACOM actualizada en cada uno.

## Estado del deploy centralizado (verificado — 2026-08-27)

- Host: `docs.astervoip.com.ar` (IP pública `51.222.92.27`), usuario `devops`.
- Contenedor `validadornumgeo` corriendo vía `docker compose`, **healthy**,
  commit `a882b4a` (falta solo el último commit local, `.gitignore` de
  `.claude/`, sin impacto funcional).
- Puertos publicados por Docker directo al host (ver
  [docker-compose.yml](../docker-compose.yml)):
  - `8181:8080` — REST API + Web UI, **detrás de Caddy**.
  - `4573:4573` — FastAGI, **expuesto directo del contenedor al host**, sin
    pasar por Caddy.
- DNS: **`telval.centraltelefonica.com.ar`** → `51.222.92.27` (URL real a
  usar; `telval.astervoip.com.ar` que menciona [DEPLOY.md](../DEPLOY.md) está
  desactualizado, hay que corregirlo cuando cerremos este procedimiento).
- Caddy ya tiene `basicauth` configurado para
  `telval.centraltelefonica.com.ar` (usuarios `admin` y `soporte`) — cubre el
  acceso al REST/Web UI. **No cubre el puerto 4573**, que no pasa por Caddy.
- El host **no tiene VPN/Tailscale/Wireguard**, solo la IP pública. `ufw` está
  activo y en su configuración actual **rechaza conexiones externas al 4573**
  (el servicio escucha en `0.0.0.0:4573` puertas adentro, pero no hay regla
  `ufw allow` para ese puerto).

## Seguridad del puerto AGI (4573) — pendiente de definir

El protocolo AGI (TCP crudo que abre Asterisk hacia `telval`) no tiene
autenticación nativa. Decisiones:

- **`docs.astervoip.com.ar` es un KVM standalone** en el nodo Proxmox
  `nodo4` — no está en cluster, pero comparte las mismas vnets SDN que el
  resto del DC (incluido `proxmox2`).
- **Se descartó exponer el AGI por vnet privada compartida** entre `nodo4`
  y `proxmox2`, a pesar de ser viable técnicamente: hay otro cluster que
  podría consumir el servicio y clientes on-prem, que no comparten esa
  vnet. Se optó por **exposición vía IP pública**, con allowlist por
  bloque CIDR, para cubrir todos los consumidores por igual.
- [ ] **Firewall**: allowlist por bloque CIDR hacia el puerto 4573, con
      casos especiales (IP suelta) para clientes on-prem que no caigan en
      ningún bloque. Dos mecanismos posibles, a elegir según acceso
      disponible al momento de aplicarlo:
      - **Proxmox Datacenter/VM Firewall + IPSet** en `nodo4` (recomendado:
        declarativo, versionado en `/etc/pve/firewall/`, reusable si se
        centralizan más servicios). Requiere acceso a `nodo4` — agente sin
        acceso todavía.
      - **`ufw allow from <CIDR> to any port 4573 proto tcp`** dentro de la
        VM `docs.astervoip.com.ar` (ya tenemos acceso SSH `devops@`, pero
        `sudo` pide contraseña interactiva no disponible para el agente).
      - Pendiente: los bloques CIDR a precargar (cluster propio, el otro
        cluster que podría usar el servicio, y la lista de IPs de
        clientes on-prem como casos especiales sueltos).
- [ ] **Secreto compartido** (hardening antes de escalar a más clientes):
      pasar un token como argumento extra en `AGI()`
      (`AGI(agi://telval.centraltelefonica.com.ar:4573/validate,${EXTEN},${TELVAL_TOKEN})`)
      y validarlo en `fastagi.py` antes de procesar. Pendiente de
      implementar — no bloquea la prueba a pequeña escala, se hace antes del
      rollout a más clientes en PRD.
- Se descartó exponer 4573 a `0.0.0.0/0` sin restricción.
- Se descartó depender de una IP dinámica doméstica (motivo del cambio de
  plan: clonar el LXC dentro del cluster Proxmox propio en vez de en casa).

## Entorno de pruebas — LXC 1324

- Origen: LXC **1324** del cliente, en el Proxmox del cliente.
- Restauración: el usuario está trayendo el dump (`vzdump`) y restaurándolo
  manualmente en un LXC nuevo dentro de **su propio cluster Proxmox**
  (`proxmox2` / `scale-i1-ceph2.centraltelefonica.com.ar`), con una IP libre
  dentro del cluster — evita el problema de IP dinámica y mantiene el tráfico
  AGI dentro de infraestructura propia.
- **Nota de acceso**: el agente no tiene clave autorizada como `root` en
  `proxmox2` (probado 2026-08-27, `Permission denied (publickey,password)`
  con la única clave del agente, `id_ed25519 / juanpablo@mazzini.com.ar`).
  El usuario hace la restauración manualmente y luego comparte acceso al
  contenedor resultante.
- **Pendiente**: IP/host del LXC restaurado, credenciales de acceso, y
  confirmación de que el dialplan de ese clon puede modificarse en un
  contexto/extensión de prueba aislado (sin tocar rutas de producción reales
  del cliente, aunque sea una copia).

---

## Mejora de diseño — AGI debe devolver PREFIX+número listo para `Dial()` por trunk

> Discutido 2026-08-28, **no implementado todavía** (pendiente de que el
> usuario revise `macrodialout` y la BD actual antes de tocar código).

### Problema

El dialplan necesita pasarle al AGI, además del número: **qué trunk** se va
a usar y **qué prefijo** (si aplica) exige ese trunk — y que el AGI devuelva
el string completo ya armado (`PREFIX + número normalizado en el formato
que espera ese proveedor`), listo para `Dial()`.

Los clientes hacen **round robin entre varios trunks**, y cada trunk puede
requerir un formato distinto → **hay que pegarle al AGI una vez por cada
trunk candidato** antes de armar el `Dial()` combinado, no una sola vez por
llamada. Confirmado que esto no es un problema de escala: el AGI ya es sin
estado y multihilo (ver sección de arquitectura arriba).

### Por qué NO resolver "nombre de trunk → proveedor" adentro de telval

El nombre del trunk es arbitrario por cliente (el cliente le puede poner
cualquier nombre al proveedor) — intentar adivinar el proveedor a partir de
ese string, o mantener una tabla trunk→proveedor por cliente/IP adentro de
telval, reintroduce el problema que se evitó centralizando el servicio
(una tabla más para mantener sincronizada por cliente).

### Diseño propuesto

1. **El dialplan pasa el `provider_key` explícito** (una de las claves ya
   existentes en [providers.py](../providers.py) — `movistar`, `personal`,
   `claro`, etc., o una nueva si hace falta agregarla) como argumento del
   AGI, no el nombre del trunk. Quien da de alta el trunk decide una vez
   qué `provider_key` le corresponde.
2. **`fastagi.py` se extiende** para aceptar `agi_arg_3=provider_key` y
   `agi_arg_4=prefix`, reusando `format_for_provider()`
   ([providers.py:284-289](../providers.py#L284-L289)) que ya existe — sin
   heurística de matching de nombres, cero lógica nueva de resolución.
3. **Devuelve una variable nueva**, `TELVAL_DIAL` = `prefix + fmt_provider`,
   el string completo listo para `Dial(SIP/${TELVAL_DIAL}@${TRUNK})`.
4. **Retrocompatible**: si `provider_key` viene vacío, se comporta como hoy
   (solo los `TELVAL_*` sueltos, sin `TELVAL_DIAL`) — no rompe los
   dialplans existentes ni lo documentado en INSTALL.md/README.
5. Si `provider_key` es desconocido: `TELVAL_DIAL_ERROR=provider_desconocido`
   en vez de fallar silencioso.

### Dónde vive `provider_key` / `prefix` por trunk

- **Descartado**: campo custom en `pjsip.conf` (`set_var` en el endpoint).
  Motivo: `set_var` de un endpoint solo puebla el canal cuando ESE canal se
  crea, es decir, en el momento del `Dial()` — demasiado tarde, porque el
  AGI (y el string a pasarle a `Dial()`) hay que armarlo ANTES del `Dial()`.
- **Opción A — variables de dialplan / globals** (mismo lugar donde ya
  viven `${TRUNK}` y `${PREFIJO}` hoy): simple, versionable en git, sin
  piezas nuevas. Ideal si la tabla de trunks por cliente se define una vez
  al alta y casi no cambia.
- **Opción B — AstDB** (`database put trunk/<nombre> provider ...`, leído
  con `${DB(trunk/${TRUNK}/provider)}`): mejor si la lista de trunks o sus
  prefijos cambian seguido en operación, sin querer tocar `extensions.conf`
  ni hacer `dialplan reload`.
- **Pendiente de decidir**: el usuario va a revisar primero cómo
  `macrodialout` (macro ya existente) arma hoy esta información y de qué
  tabla/BD la saca, para no crear una pieza nueva si ya hay una
  convención existente que conviene reusar.

---

## Pendientes fuera de este repo (pasar a Todoist — proyecto "sareak")

> No hay integración de Todoist en esta sesión, quedan anotados acá hasta
> que se carguen a mano.

- [ ] **Push Mirror de Gitea → GitHub** (repo `validadornumgeo`): sincronizar
  `gitea.centraltelefonica.com.ar/jmazzini/validadornumgeo` con
  `github.com/sareakar/validadornumgeo` vía Settings → Repository → Push
  Mirrors (token de GitHub con permiso `repo`). Descartado por ahora
  (2026-08-31) porque ambos repos son del mismo dueño — no es urgente, pero
  queda pendiente para cuando sume otro colaborador. Mientras tanto,
  `origin` en este clon local ya tiene push-url doble (gitea + github)
  como solución parcial (ver `git remote -v`).

---

## Piloto Ungar (`dycrecupero.centraltelefonica.com.ar`) — EN PRODUCCIÓN

> Cliente real, en producción. Cualquier cambio va en un interno/contexto de
> prueba aislado — no se toca el enrutamiento real de llamadas del cliente
> hasta validar y decidir aplicarlo.

### Acceso

- SSH: `soporte@dycrecupero.centraltelefonica.com.ar:2022`. Sin clave
  pública autorizada para el agente (mismo caso que `proxmox2`) — acceso
  actual vía password (compartida por el usuario en el chat, no
  persistida en este repo). Auth por password, no por key.
- Plataforma: **AsterVoIP propio** (no FreePBX/Issabel) — Debian 10,
  Asterisk 16. Dialplan modular vía `#include` en
  `/etc/asterisk/extensions.conf` → `/etc/asterisk/partesextensions/*.conf`
  y `/etc/asterisk/pbx/*.conf`.
- IP pública saliente del cliente: **`66.70.167.11`** (mismo /24 que
  `dockerovh` = `66.70.167.10` en `~/.ssh/config` — probablemente mismo
  datacenter/bloque OVH; candidato a bloque CIDR para el allowlist en vez
  de IP suelta, a confirmar).
- **Confirmado: puerto 4573 de `telval.centraltelefonica.com.ar` rechazado
  desde este cliente** (`Connection refused`) — sigue pendiente el punto
  de firewall de la sección de arriba, ahora con una IP real para probar.

### Hallazgos del dialplan real (relevamiento de solo lectura, 2026-08-31)

- **`macrodialout` = `[macro-dialout]`** en
  `/etc/asterisk/partesextensions/macros.conf`. Recibe por cada trunk
  candidato un grupo de 4 args: `Trunk` (string de canal, ej. `SIP/750`),
  `Prefix` (prefijo internacional hardcodeado: `54`/`549`/`54911`...),
  `Numero` (número recortado a mano con `${FNUMBER:N}`), `NumeroReal`.
  Dialea con `Dial(${Trunk}/${Prefix}${Numero},...)`.
- **La lógica ad hoc de formato NO vive en `macro-dialout`**, vive en quien
  lo llama — `/etc/asterisk/pbx/permisos.conf` arma `Prefix`/`Numero` a
  mano por cada condición de longitud/formato de `${FNUMBER}` antes de
  invocar `Macro(dialout,...)`. Ese es el punto de integración: reemplazar
  ese heurístico por una llamada al AGI, sin tocar `macro-dialout` (que es
  compartido por todo el discado) — blast radius chico.
- **Ya usan AstDB por trunk**: `${DB(${Trunk}/troncalActivo)}`,
  `${DB(${Trunk}/outCID)}`, `${DB(${Trunk}/troncalOcupado)}`,
  `${DB(${Trunk}/chanIsAvail)}`, todas bajo family = el string de canal
  literal (`${Trunk}`). **Esto resuelve la pregunta de diseño pendiente**:
  agregar `${DB(${Trunk}/provider)}` con el mismo criterio — no globals de
  dialplan, no tabla nueva, mismo patrón que ya usan.
- **"Prefix" en su sistema = prefijo internacional** (54/549/54911), que
  es exactamente lo que `provider_key` → `format_for_provider()` ya
  resuelve adentro de telval. Conclusión: **probablemente no hace falta
  el argumento `prefix` separado** que se había diseñado — `TELVAL_DIAL`
  con `provider_key` solo alcanza, y se pasaría como `Numero` (con
  `Prefix=""`) al `Macro(dialout,...)` existente, sin modificarlo.
- Ya usan AGI clásico (no FastAGI) en otro lado del dialplan
  (`AGI(pbx-ip/claveRuta.agi,...)`, `AGI(pbx-ip/internoExiste.agi,...)`,
  comentado) — el patrón AGI ya es familiar en esta plataforma, no es un
  concepto nuevo para el equipo de soporte.
- `asterisk` (CLI) no está en el PATH del usuario `soporte` sin sudo/ruta
  completa — pendiente de resolver para poder hacer `dialplan reload` más
  adelante.

### Pendiente / próximo paso

- [x] **Implementado `provider_key`/`prefix` → `TELVAL_DIAL` en
      `fastagi.py`** (2026-08-31), con tests en `tests/test_fastagi.py` (7
      secciones, todas pasan) y documentado en README.md. Se implementó
      completo (no la versión recortada solo-Ungar) a pedido del usuario:
      "lo que desarrollemos para conectar Ungar debe quedar para el resto".
      `build_vars()`/`_dial_vars()` son funciones de módulo en
      `fastagi.py` (no métodos), reusa `format_for_provider()` de
      `providers.py` sin lógica nueva de matching. Retrocompatible: sin
      `provider_key` en la llamada AGI, comportamiento idéntico a antes.
- [x] **Regla `ufw` agregada** (2026-08-31): `allow from 66.70.167.11 to
      any port 4573 proto tcp` en `docs.astervoip.com.ar` (acceso: SSH
      `devops@` por key + `su` a `root` con password compartida por el
      usuario, no persistida en este repo). **No resolvió el problema** —
      ver hallazgo abajo.
- [ ] **BLOQUEANTE actual, fuera de este VM**: `ufw` no tiene ningún
      efecto sobre el puerto 4573 porque Docker maneja `iptables` por su
      cuenta — la chain `DOCKER` ya tiene `ACCEPT` **sin restricción de
      IP** (`0.0.0.0/0 → 172.23.0.2:4573`) para ese puerto, evaluada en
      `FORWARD` antes de que el tráfico llegue a las reglas de `ufw`
      (que solo aplican a `INPUT`). Confirmado con `iptables -t nat -L`,
      `iptables -L DOCKER -n`, `iptables -L ufw-user-input -n` en
      `docs.astervoip.com.ar` como root.
      **A pesar de eso, sigue "Connection refused" desde Ungar Y desde
      una IP no relacionada** (probado igual) — el bloqueo real está
      **río arriba de este VM**: firewall del hypervisor Proxmox
      (`nodo4`) a nivel de interfaz de red de la VM, o firewall de red
      de OVH a nivel de panel. El agente no tiene acceso a ninguno de
      los dos — pendiente de que el usuario lo revise o dé acceso.
- [ ] **Hardening pendiente (una vez destrabado lo anterior)**: el 4573
      está hoy abierto a todo Internet a nivel Docker, sin restricción
      real por IP (el `ufw allow` de arriba no restringe nada). Hay que
      agregar la restricción en la chain **`DOCKER-USER`** (Docker no la
      sobreescribe), no en `ufw`:
      ```
      iptables -I DOCKER-USER -p tcp --dport 4573 -s 66.70.167.11 -j ACCEPT
      iptables -I DOCKER-USER -p tcp --dport 4573 -j DROP
      ```
      (persistir con `iptables-persistent`/`netfilter-persistent` o
      equivalente para que sobreviva un reinicio — a definir cómo
      persisten reglas en este servidor).
- [ ] Definir el interno/contexto de prueba aislado en Ungar — **lo crea
      el usuario desde el front** (no el agente), junto con un
      `macro-dialout-qa` en un include aparte para probar. Queda para
      cuando el 4573 esté abierto.
- [ ] Cargar `${DB(${Trunk}/provider)}` (y `prefix` si aplica) en AstDB
      para el/los trunk(s) reales de Ungar, siguiendo el mismo patrón que
      `troncalActivo`/`outCID` ya usan en `macro-dialout`.

---

## Próximos pasos (una vez con acceso al LXC restaurado) — plan original, supersedido por el piloto Ungar de arriba

1. Verificar conectividad de red: `curl` o test TCP desde el LXC hacia
   `telval.centraltelefonica.com.ar:4573` y `:443` (una vez resuelto el
   punto de firewall arriba).
2. Ubicar `extensions.conf` (o el archivo de contexto correspondiente) y
   agregar una extensión/contexto de prueba aislado que invoque
   `AGI(agi://telval.centraltelefonica.com.ar:4573/validate,${EXTEN})`
   — sin tocar los contextos de producción reales, aunque sea una copia.
3. Probar con números reales del cliente (fijos, móviles AMBA, interior) y
   verificar las variables `TELVAL_*` (ver tabla en
   [README.md](../README.md#variables-que-devuelve-el-agi)).
4. Documentar acá cada cambio de dialplan (diff completo) y su resultado.
5. Una vez validado: aplicar el mismo cambio de dialplan al LXC de
   producción del cliente, y decidir si el hardening con token (arriba) se
   implementa antes de ese paso.

---

## Bitácora

- **2026-08-27** — Definida arquitectura (FastAGI centralizado). Verificado
  estado del deploy en `docs.astervoip.com.ar` (container OK, puerto 4573
  bloqueado externamente por `ufw`). Confirmado dominio real
  `telval.centraltelefonica.com.ar` con basicauth ya activo para REST.
  Descartado plan de restaurar el LXC 1324 en casa (IP dinámica). Usuario
  procede a restaurar LXC 1324 en `proxmox2` (cluster propio) manualmente;
  agente sin acceso `root` a `proxmox2` con la clave actual.
- **2026-08-27** — Confirmada la decisión de AGI centralizado (no uno por
  LXC) usando como precedente el mismo esquema ya usado en producción para
  vosk (un servicio central, múltiples dialplans de cliente pegándole por
  red). Motivo técnico de por qué escala: `fastagi.py` usa
  `ThreadingMixIn` (un thread por llamada, sin cola compartida) y
  `validate()` no tiene estado ni I/O externo (lookup en dict en memoria) —
  el costo por request es despreciable frente al handshake TCP. El único
  trade-off real es disponibilidad (si el central cae, cae para todos los
  clientes a la vez); pendiente evaluar si el dialplan de PRD debe manejar
  `AGISTATUS=FAILURE` con un fallback en vez de colgar la llamada.
  Se actualizó [dialplan_example.conf](../dialplan_example.conf) para no
  hardcodear `127.0.0.1` (eso correspondía a instalación local, no al modo
  centralizado decidido) — ahora usa `${TELVAL_HOST}` / `${TELVAL_PORT}`
  definidos una sola vez en `[globals]`, para que cambiar de entorno
  (prueba → producción) sea una edición en un solo lugar y no un grep por
  cada `extensions.conf` de cliente.
