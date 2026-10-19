# Imagen de Ansible para correr vía Podman, mismo criterio que la
# imagen "astervoip-terraform" ya en uso (ver la función `tf()` en
# .bashrc). Base igual (python:3.11-slim) para consistencia.
#
# A diferencia de Terraform (un solo binario, ENTRYPOINT fijo), Ansible
# tiene varios (ansible, ansible-playbook, ansible-vault, ansible-galaxy)
# -- no se fija ENTRYPOINT, el wrapper de bash pasa el binario como
# primer argumento.
#
# sshpass es necesario porque los clientes de AsterVoIP usan auth por
# password, no claves SSH (ver ansible_password en el inventario).

FROM python:3.11-slim

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
       openssh-client \
       sshpass \
    && rm -rf /var/lib/apt/lists/*

# Sin version fijada todavia -- primer build para tener algo andando.
# Pendiente (ver docs/ANSIBLE_PROCEDIMIENTO.md): pinnear una version
# exacta de ansible-core una vez que el playbook este estable, para
# reproducibilidad entre esta maquina e infra-apps.
RUN pip install --no-cache-dir ansible-core

WORKDIR /app
