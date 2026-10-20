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

# Version fijada por COMPATIBILIDAD, no solo por reproducibilidad:
# ansible-core 2.19 (ultima al momento de armar esto) ya usa sintaxis
# de Python 3.8+ (parametros solo-posicionales) en su propio
# module_utils, y falla con SyntaxError en el nodo remoto si el Python3
# ahi es mas viejo. Los clientes de AsterVoIP corren Debian 10, que
# trae Python 3.7.3 de fabrica -- confirmado con un SyntaxError real
# contra medimas.centraltelefonica.com.ar antes de este pin. <2.16
# evita el corte de compatibilidad (no se identifico la version exacta
# donde ansible-core subio el Python minimo del nodo administrado a
# 3.8 -- <2.16 da margen de sobra, verificado empiricamente).
RUN pip install --no-cache-dir "ansible-core<2.16"

WORKDIR /app
