# Instalación en LXC Asterisk

Instalación directa con Python, sin Docker. Aplica a contenedores LXC Debian/Ubuntu con Asterisk ya instalado.

---

## Requisitos

- Python 3.9 o superior (`python3 --version`)
- pip (`python3 -m pip --version`)
- Git
- Usuario `asterisk` existente (creado por la instalación de Asterisk)

---

## 1. Clonar el repositorio

```bash
git clone https://gitea.centraltelefonica.com.ar/jmazzini/validadornumgeo.git /opt/telval
cd /opt/telval
```

---

## 2. Instalar dependencias

```bash
python3 -m pip install -r requirements.txt
```

Dependencias instaladas:
- `phonenumbers` — validación de formato adicional
- `openpyxl` — lectura de archivos Excel
- `pandas` — procesamiento de archivos en CLI
- `click`, `rich` — interfaz CLI

> Si el LXC no tiene pip: `apt install python3-pip` (Debian/Ubuntu)

---

## 3. Verificar que funciona

```bash
cd /opt/telval
python3 main.py stats
```

Resultado esperado:
```
Base ENACOM cargada:
  Bloques totales : 48.903
  Indicativos     : 300
  Móvil           : 35.246
  Fijo            : 13.604
```

---

## 4. Instalar como servicio systemd

```bash
cp /opt/telval/telval.service /etc/systemd/system/
systemctl daemon-reload
systemctl enable --now telval
systemctl status telval
```

El servicio levanta dos puertos:
- `4573` — FastAGI (para el dialplan de Asterisk)
- `8080` — REST API + Web UI

---

## 5. Verificar el servicio

```bash
# Estado
systemctl status telval

# Logs en tiempo real
journalctl -u telval -f

# Health check
curl http://localhost:8080/health
# Esperado: {"status": "ok", "enacom_db": true}
```

---

## 6. Integrar en el dialplan de Asterisk

Editar `/etc/asterisk/extensions.conf` (o el contexto correspondiente):

```
; Validación local (validador en el mismo LXC)
exten => _X.,1,AGI(agi://127.0.0.1:4573/validate,${EXTEN})
 same => n,GotoIf($["${TELVAL_VALID}" != "1"]?invalido)
 same => n,GotoIf($["${TELVAL_MODALIDAD}" = "CPP"]?movil)
 same => n,GotoIf($["${TELVAL_MODALIDAD}" = "MPP"]?movil)
 ; Fijo
 same => n,Dial(SIP/${TELVAL_CON0}@trunk_fijo)
 same => n,Hangup()
 ; Móvil CPP/MPP
 same => n(movil),Dial(SIP/${TELVAL_CON015}@trunk_movil)
 same => n,Hangup()
 ; Inválido
 same => n(invalido),Hangup()
```

Recargar dialplan:
```bash
asterisk -rx "dialplan reload"
```

---

## Modo externo (validador en servidor dedicado)

Si el validador corre en un servidor central y los LXC de Asterisk se conectan a él remotamente, cambiar el servicio para escuchar en todas las interfaces:

Editar `/etc/systemd/system/telval.service`, reemplazar la línea `ExecStart`:

```ini
ExecStart=/usr/bin/python3 /opt/telval/server.py --agi-host 0.0.0.0 --agi-port 4573 --api-port 8080
```

Recargar:
```bash
systemctl daemon-reload
systemctl restart telval
```

En el dialplan de cada LXC cliente, apuntar a la IP del servidor central:
```
AGI(agi://IP_SERVIDOR_CENTRAL:4573/validate,${EXTEN})
```

---

## Actualizar

```bash
cd /opt/telval
git pull
systemctl restart telval
```

---

## Actualizar la base ENACOM

Cuando ENACOM publique una versión nueva del archivo XLS:

```bash
# Copiar el nuevo XLS al servidor y convertirlo a CSV
# (ver sección "Actualizar la base ENACOM" en README.md)

# Reemplazar el CSV y reiniciar
cp numgeo_enacom_nuevo.csv /opt/telval/data/numgeo_enacom.csv
systemctl restart telval
```

---

## Comandos útiles

```bash
# Validar un número manualmente
python3 /opt/telval/main.py validate 1130032202

# Procesar una lista
python3 /opt/telval/main.py export lista.csv simvoz

# Ver carriers disponibles
python3 /opt/telval/main.py providers

# Reiniciar el servicio
systemctl restart telval

# Ver logs
journalctl -u telval -f --since "1 hour ago"
```
