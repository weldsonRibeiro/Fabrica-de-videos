"""Custo parcial de uma etapa interrompida.

Se a etapa gasta (ex.: 7 de 12 imagens) e então bate no limite, o gasto não pode sumir.
Fica num arquivo ao lado da saída e é somado quando a etapa finalmente termina — mesmo que
o `tick` rode como um processo novo a cada minuto.
"""
from __future__ import annotations

import json
from pathlib import Path


class CustoPendente:
    def __init__(self, pasta: Path):
        self._arquivo = pasta / "custo_pendente.json"

    def somar(self, valor: float) -> None:
        self._arquivo.parent.mkdir(parents=True, exist_ok=True)
        atual = self._ler()
        self._arquivo.write_text(json.dumps({"valor": round(atual + valor, 6)}), encoding="utf-8")

    def descarregar(self) -> float:
        """Devolve o acumulado e zera."""
        valor = self._ler()
        if self._arquivo.exists():
            self._arquivo.unlink()
        return valor

    def _ler(self) -> float:
        if not self._arquivo.exists():
            return 0.0
        return float(json.loads(self._arquivo.read_text(encoding="utf-8")).get("valor", 0.0))
