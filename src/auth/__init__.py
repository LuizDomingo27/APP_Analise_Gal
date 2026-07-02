# -*- coding: utf-8 -*-
"""
Camada de autenticação — isolada do restante da aplicação.

Responsável por: tabela `usuarios`, hashing de senha (PBKDF2-HMAC-SHA256),
CRUD de usuários, reset de senha por pergunta de segurança e controle de
sessão/login no Streamlit.
"""
