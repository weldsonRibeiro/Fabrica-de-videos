"""Carrega um arquivo .env (CHAVE=valor) sem sobrescrever o que já está no ambiente."""
from __future__ import annotations

import os
from pathlib import Path


def carregar_env(caminho: Path | str = ".env") -> list[str]:
    """Devolve os nomes das variáveis que definiu."""
    arquivo = Path(caminho)
    if not arquivo.is_file():
        return []
    definidas = []
    for linha in arquivo.read_text(encoding="utf-8").splitlines():
        linha = linha.strip()
        if not linha or linha.startswith("#") or "=" not in linha:
            continue
        nome, _, valor = linha.partition("=")
        nome = nome.strip().removeprefix("export ").strip()
        valor = valor.strip()
        if len(valor) >= 2 and valor[0] == valor[-1] and valor[0] in "\"'":
            valor = valor[1:-1]
        elif " #" in valor:
            valor = valor.split(" #", 1)[0].strip()
        if nome and valor and nome not in os.environ:  # vazio = "não definido" (como no .env.example)
            os.environ[nome] = valor
            definidas.append(nome)
    return definidas
