"""Indicador de progresso do pipeline.

Em terminal: barras do `rich` (com spinner quando o total é desconhecido).
Fora de terminal (log em arquivo, cron): linhas com horário no início e no fim
de cada tarefa e nos marcos de 25/50/75%, para o log nunca ficar mudo.

Tarefas são identificadas por uma chave de texto, o que permite que processos
filhos informem o progresso por uma fila (`Progresso.fila()` + `ProgressoRemoto`).
"""
import queue
import sys
import threading
import time
from datetime import datetime

MARCOS = (25, 50, 75)


def _duracao(segundos):
    m, s = divmod(int(segundos), 60)
    h, m = divmod(m, 60)
    return f"{h}h{m:02d}m{s:02d}s" if h else f"{m}m{s:02d}s" if m else f"{s}s"


class Progresso:
    def __init__(self, visual=None):
        self.visual = sys.stdout.isatty() if visual is None else visual
        self._trava = threading.RLock()
        self._tarefas = {}  # chave -> dict(desc, total, feito, inicio, marco, id_rich)
        self._fila = None
        self._ouvinte = None
        self._rich = None
        self._gerente = None

    # --- ciclo de vida ---------------------------------------------------
    def __enter__(self):
        if self.visual:
            from rich.progress import (BarColumn, Progress, SpinnerColumn, TaskProgressColumn,
                                       TextColumn, TimeElapsedColumn)
            self._rich = Progress(SpinnerColumn(), TextColumn("{task.description}"), BarColumn(),
                                  TaskProgressColumn(), TimeElapsedColumn(), redirect_stdout=True,
                                  redirect_stderr=True, refresh_per_second=4)
            self._rich.start()
        return self

    def __exit__(self, *exc):
        if self._fila is not None:
            self._fila.put(None)
            self._ouvinte.join()
            self._gerente.shutdown()
        if self._rich is not None:
            self._rich.stop()

    def fila(self):
        """Fila que pode ser passada a processos filhos (ProcessPoolExecutor)."""
        if self._fila is None:
            import multiprocessing
            self._gerente = multiprocessing.Manager()
            self._fila = self._gerente.Queue()
            self._ouvinte = threading.Thread(target=self._ouvir, daemon=True)
            self._ouvinte.start()
        return self._fila

    def _ouvir(self):
        while True:
            try:
                msg = self._fila.get()
            except (EOFError, OSError, queue.Empty):
                return
            if msg is None:
                return
            metodo, args, kwargs = msg
            getattr(self, metodo)(*args, **kwargs)

    # --- API ----------------------------------------------------------------
    def log(self, mensagem):
        with self._trava:
            linha = f"[{datetime.now():%H:%M:%S}] {mensagem}"
            if self._rich is not None:
                self._rich.console.print(linha, markup=False, highlight=False)
            else:
                print(linha, flush=True)

    def inicio(self, chave, descricao, total=None, silencioso=False):
        with self._trava:
            t = {"desc": descricao, "total": total, "feito": 0, "inicio": time.monotonic(), "marco": 0}
            if self._rich is not None:
                t["id"] = self._rich.add_task(descricao, total=total)
            elif not silencioso:
                self.log(f"▶ {descricao}" + (f" ({total:,})" if total else ""))
            self._tarefas[chave] = t

    def avanco(self, chave, feito=None, total=None, passo=None, descricao=None):
        with self._trava:
            t = self._tarefas.get(chave)
            if t is None:
                return
            if total is not None:
                t["total"] = total
            if passo is not None:
                t["feito"] += passo
            if feito is not None:
                t["feito"] = feito
            if descricao is not None:
                t["desc"] = descricao
            if self._rich is not None:
                self._rich.update(t["id"], completed=t["feito"], total=t["total"], description=t["desc"])
            elif t["total"]:
                pct = 100 * t["feito"] / t["total"]
                for m in MARCOS:
                    if pct >= m > t["marco"]:
                        t["marco"] = m
                        self.log(f"  {t['desc']}: {m}%")

    def fim(self, chave, mensagem=None, erro=False):
        with self._trava:
            t = self._tarefas.pop(chave, None)
            if t is None:
                return
            texto = f"{'✖' if erro else '✔'} {mensagem or t['desc']} ({_duracao(time.monotonic() - t['inicio'])})"
            if self._rich is not None:
                self._rich.remove_task(t["id"])
            self.log(texto)


class ProgressoRemoto:
    """Mesma API de `Progresso`, para uso dentro de processos filhos."""

    def __init__(self, fila):
        self._fila = fila

    def __getattr__(self, metodo):
        if metodo not in ("log", "inicio", "avanco", "fim"):
            raise AttributeError(metodo)
        return lambda *a, **k: self._fila.put((metodo, a, k))


class Nulo:
    """Progresso que não faz nada (scripts executados isoladamente sem indicador)."""

    def log(self, mensagem):
        print(mensagem, flush=True)

    def inicio(self, *a, **k):
        pass

    def avanco(self, *a, **k):
        pass

    def fim(self, *a, **k):
        pass
