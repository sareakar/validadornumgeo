# Despliegue — ValidadorNumGeo

Servidor: `docs.astervoip.com.ar` (infra-apps)
URL final: `https://telval.astervoip.com.ar`

---

## Requisitos previos

- Docker y Docker Compose instalados en el servidor
- Caddy corriendo como proxy inverso en el host
- DNS `telval.astervoip.com.ar` apuntando a la IP del servidor (`51.222.92.27`)

---

## 1. Subir el código al servidor

Desde tu máquina local:

```bash
scp -r /ruta/local/validadortelefonico/ devops@docs.astervoip.com.ar:/opt/validadornumgeo/
```

O clonar desde Gitea directamente en el servidor:

```bash
ssh devops@docs.astervoip.com.ar
git clone https://gitea.centraltelefonica.com.ar/jmazzini/validadornumgeo.git /opt/validadornumgeo
```

---

## 2. Levantar el contenedor

```bash
ssh devops@docs.astervoip.com.ar

cd /opt/validadornumgeo
docker compose up -d --build

# Verificar que levantó
docker compose ps
docker compose logs -f
```

El servicio queda escuchando en `localhost:8181`.

---

## 3. Configurar Caddy

Agregar al Caddyfile (`/etc/caddy/Caddyfile`):

```caddy
telval.astervoip.com.ar {
    reverse_proxy localhost:8181
}
```

Recargar Caddy:

```bash
sudo systemctl reload caddy
```

Caddy obtiene el certificado TLS automáticamente.

---

## 4. Verificar

```bash
# Contenedor corriendo
docker compose -f /opt/validadornumgeo/docker-compose.yml ps

# API responde
curl http://localhost:8181/health

# HTTPS desde afuera
curl https://telval.astervoip.com.ar/health
# Esperado: {"status": "ok", "enacom_db": true}
```

---

## Actualizar a una nueva versión

```bash
ssh devops@docs.astervoip.com.ar
cd /opt/validadornumgeo

git pull
docker compose up -d --build
```

---

## Actualizar la base ENACOM

La carpeta `data/` está montada como volumen — se puede reemplazar el CSV sin reconstruir la imagen:

```bash
# Copiar el nuevo CSV al servidor
scp numgeo_enacom.csv devops@docs.astervoip.com.ar:/opt/validadornumgeo/data/

# Reiniciar el contenedor para que lo cargue
docker compose restart validadornumgeo
```

---

## Comandos útiles

```bash
# Ver logs en tiempo real
docker compose logs -f validadornumgeo

# Reiniciar
docker compose restart validadornumgeo

# Detener
docker compose down

# Reconstruir imagen (tras cambios en el código)
docker compose up -d --build
```
