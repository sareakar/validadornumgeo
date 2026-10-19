# Ansible — instructivo y procedimiento (documento vivo)

> Primera vez usando Ansible en este proyecto (2026-10-19). Este
> documento se va completando a medida que avanzamos — no es un
> procedimiento cerrado todavía. Pensado para alguien sin experiencia
> previa en Ansible, explicado en términos de lo que ya veníamos
> haciendo a mano (SSH + scp + sudo) en todo este proyecto.

## Por qué Ansible acá

Hasta ahora, cada cambio en un cliente (instalar un script, editar
`macros.conf`, agregar un cron) se hizo a mano: `scp` el archivo,
`ssh` + `sudo` para moverlo/aplicarlo, un script Perl para el
reemplazo de texto exacto con chequeo de unicidad, mostrar el diff,
pedir aprobación. Funciona bien para un cliente a la vez con
revisión humana en cada paso — que es exactamente lo que se quiere
seguir haciendo. Ansible no cambia ese criterio, solo lo hace
repetible sin rearmar los mismos comandos SSH/scp a mano cada vez, y
agrega dry-run (`--check --diff`) nativo en vez de tener que armar un
script de conteo de anchor para cada caso.

## Conceptos, mapeados a lo que ya hacíamos

| Lo que hacíamos a mano | Equivalente en Ansible |
|---|---|
| Lista mental de hosts (dyktel, medimas, resermap + user/puerto/password) | **Inventario** (`inventory.yml`) |
| Diferencias entre clientes (DB migrada en Dyktel, sin sudo en Resermap) | **Variables por host** (`host_vars/`) — mismo playbook, se adapta solo |
| `scp script host:/tmp/` + `ssh host "sudo mv && chown && chmod"` | Módulo `copy` (un paso declara destino, dueño y permisos) |
| `sudo` adelante de un comando | `become: yes` en la tarea |
| Mostrar el diff antes de aplicar, pedir el "sí" | `--check --diff` — nativo, sin armar nada a medida |
| `cp archivo archivo.bak_$(date)` antes de editar | `backup: yes` en el módulo que edita — backup automático con timestamp |
| Probar en un cliente antes que en todos | `--limit <host>` |

Un **playbook** es un archivo YAML con una lista de "tareas", cada una
usando un **módulo** (acción reutilizable: copiar archivo, asegurar
una línea de cron, correr un comando, etc.). Se invoca así:

```bash
# Dry-run -- muestra que cambiaria, no toca nada
ansible-playbook -i inventory.yml deploy-trunk-sync.yml --limit medimas --check --diff

# Aplicar de verdad, un solo host
ansible-playbook -i inventory.yml deploy-trunk-sync.yml --limit medimas

# Aplicar a todos los hosts del inventario
ansible-playbook -i inventory.yml deploy-trunk-sync.yml
```

**Resermap no entra en el inventario** (o entra marcado "manual
solamente") — no tiene sudo y no se va a tocar esa decisión, así que
ningún tooling cambia ese flujo colaborativo.

## Dónde corre Ansible (el "control node")

Importante: Ansible **no se instala en los clientes** (dyktel, medimas)
— se instala en la máquina desde la que vos lo *ejecutás* (el "control
node"), y desde ahí se conecta por SSH a los clientes, igual que
hacíamos nosotros a mano. Por eso se puede correr desde infra-apps, tu
laptop, o cualquier otra máquina con acceso SSH a los clientes — el
playbook vive en el repo y es portable.

### Opciones de instalación del control node

| Opción | Cómo | Cuándo conviene |
|---|---|---|
| **pip/pipx en un venv del repo** (recomendado) | `python3 -m venv .venv && .venv/bin/pip install -r ansible/requirements.txt` | Versión fijada y reproducible en cualquier máquina (infra-apps, laptop, donde sea) — mismo resultado siempre. No necesita sudo/root. |
| **Paquete del sistema** | Fedora: `sudo dnf install ansible-core` · Debian/Ubuntu: `sudo apt install ansible` | Más simple si no importa la versión exacta. Ojo: la versión de los repos de la distro suele ir rezagada (relevante si infra-apps es Debian estable). |
| **Contenedor (Docker/Podman)** | Imagen con Ansible fijado a una versión, repo montado como volumen | Garantiza "corre igual en cualquier lado" sin instalar nada en el host — a costa de necesitar Docker/Podman disponible. |

**Recomendación**: pip en un venv, con `ansible/requirements.txt`
committeado al repo (versión de `ansible-core` fijada) — así
`infra-apps`, tu laptop, o cualquier otra máquina corren exactamente
la misma versión sin pensar en qué distro es cada una. Separado del
`requirements.txt` del validador (son dependencias de cosas distintas).

**Pendiente de confirmar**: qué SO corre `infra-apps` hoy, para decidir
si además documentamos el paso de paquete del sistema como alternativa.

## Credenciales

Ansible no quiere passwords en texto plano en el inventario — para eso
existe **Ansible Vault** (encripta esos valores dentro del mismo
archivo/repo, se desencriptan solo al ejecutar con una clave). Lo vamos
a definir cuando lleguemos a esa parte — por ahora, mismo criterio que
toda la sesión: la password no se persiste en ningún archivo sin
encriptar.

## Estructura de archivos planeada en el repo

```
ansible/
  requirements.txt       # pip: ansible-core==X.Y.Z (a definir)
  inventory.yml           # hosts + variables por cliente
  deploy-trunk-sync.yml   # el playbook de esta tarea (cron + AstDB)
  files/                  # copia de los scripts que se despliegan
                          #   (o referencian directo a agi-scripts/)
```

## Plan para el primer playbook (sync cron + AstDB)

Replica lo ya validado a mano en Medimas (ver `docs/PRUEBA_AGI_LXC1324.md`,
sección "Quinto cliente — Medimas", y `docs/ONBOARDING_CLIENTE.md`
sección 3.6):

1. `copy` → `agi-scripts/telvalTrunkSync.pl` a `/usr/local/bin/` (owner root, mode 0750).
2. `command` → `perl -c` sobre el script, falla el playbook si no compila.
3. `cron` (módulo nativo, con `cron_file:` para escribir en
   `/etc/cron.d/telval-trunk-sync` sin tocar ningún crontab existente).
4. `command` → correr el script una vez a mano, confirmar con
   `database get` antes de confiar en el cron.
5. `replace`/`blockinfile` con `backup: yes` → el cambio de una línea
   en `macros.conf` (AGI de lookup → `Set(DB(...))`), con la misma
   exigencia de "debe matchear exactamente una vez" que usábamos en los
   scripts Perl.
6. `command` → `asterisk -rx "dialplan reload"`.
7. `copy` → `agi-scripts/telval-trunk-sync.logrotate` a
   `/etc/logrotate.d/telval-trunk-sync` (encontrado en Medimas: sin
   esto el log crece sin límite, los LXC de AsterVoIP tienen
   filesystems chicos).

## Control node elegido: Podman, mismo patrón que `tf()`

Se confirmó que la función `tf()` ya en `.bashrc` (Terraform vía Podman)
monta `$HOME/.ssh` dentro del container — resuelve de entrada el
problema de credenciales SSH para Ansible también. Se armó
[`ansible/Dockerfile`](../ansible/Dockerfile): misma base
(`python:3.11-slim`) que la imagen `astervoip-terraform`, con
`openssh-client`+`sshpass` agregados (los clientes de AsterVoIP usan
password, no clave). A diferencia de Terraform (un solo binario,
`ENTRYPOINT` fijo), Ansible tiene varios (`ansible`,
`ansible-playbook`, `ansible-vault`) — sin `ENTRYPOINT` fijo, el
wrapper de bash pasa el binario como primer argumento.

Build local ya probado: `podman build -t astervoip-ansible ansible/`
→ `ansible-core 2.19.14` (sin pinnear todavía, ver pendiente abajo).

Falta sumar al `.bashrc` la función equivalente a `tf()` (propuesta,
sin aplicar todavía):

```bash
ans() {
    podman run --rm -it \
        -v "$(pwd):/app" \
        -v "$HOME/.ssh:/root/.ssh" \
        -w /app \
        --security-opt label=disable \
        astervoip-ansible "$@"
}
```

Uso: `ans ansible-playbook -i inventory.yml deploy-trunk-sync.yml --check --diff`.

## Estado actual

- [x] Decidir dónde se instala el control node primero → local, vía Podman (mismo patrón que `tf()`)
- [x] Instalar Ansible → imagen `astervoip-ansible` buildeada (`ansible/Dockerfile`, ansible-core 2.19.14)
- [ ] Agregar la función `ans()` al `.bashrc` (propuesta arriba, pendiente de aplicar)
- [ ] Pinnear versión exacta de `ansible-core` en el Dockerfile (hoy instala "latest" al build)
- [ ] Replicar la instalación en `infra-apps` (confirmar SO primero)
- [ ] Armar `ansible/inventory.yml` (dyktel, medimas)
- [ ] Armar `ansible/deploy-trunk-sync.yml`
- [ ] Resolver manejo de credenciales (Ansible Vault)
- [ ] Probar con `--check --diff` contra Medimas (ya tiene el cambio aplicado — sirve para confirmar que Ansible lo detecta como "sin cambios")
- [ ] Aplicar contra Dyktel
- [ ] Documentar cómo se agregan clientes nuevos al inventario a futuro
