"""
logger.py
----------
Responsavel por:
  - Criar um arquivo de log unico para a sessao atual (logs/session_<timestamp>.log)
  - Guardar em memoria (set) todos os IPs de saida do Tor ja vistos nesta sessao
  - Fornecer metodos simples para registrar eventos e checar duplicidade de IP
"""

import os
from datetime import datetime


class SessionLogger:
    def __init__(self, log_dir="logs"):
        self.log_dir = log_dir
        os.makedirs(self.log_dir, exist_ok=True)

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.log_path = os.path.join(self.log_dir, f"session_{timestamp}.log")

        # Historico de IPs vistos NESTA sessao (reseta a cada execucao, por design)
        self.seen_ips = set()
        self.total_rotations = 0
        self.total_duplicates_skipped = 0

        self._write_raw(f"=== Sessao TorShift iniciada em {timestamp} ===")

    # ------------------------------------------------------------------
    def _write_raw(self, line: str):
        with open(self.log_path, "a", encoding="utf-8") as f:
            f.write(line + "\n")

    def log_event(self, message: str):
        ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self._write_raw(f"[{ts}] {message}")

    # ------------------------------------------------------------------
    def is_duplicate(self, ip: str) -> bool:
        return ip in self.seen_ips

    def register_ip(self, ip: str, country: str = None, duplicate: bool = False):
        if duplicate:
            self.total_duplicates_skipped += 1
            self.log_event(f"IP repetido detectado e descartado -> {ip}")
            return

        self.seen_ips.add(ip)
        self.total_rotations += 1
        pais = f" ({country})" if country else ""
        self.log_event(f"Nova identidade Tor -> IP: {ip}{pais}")

    def log_killswitch_event(self, active: bool, reason: str = ""):
        if active:
            self.log_event(f"[KILLSWITCH] ATIVADO - {reason}")
        else:
            self.log_event(f"[KILLSWITCH] Desativado - conexao Tor normalizada")

    def summary(self) -> str:
        return (
            f"IPs unicos utilizados: {len(self.seen_ips)} | "
            f"Rotacoes bem-sucedidas: {self.total_rotations} | "
            f"Duplicatas evitadas: {self.total_duplicates_skipped}"
        )

    def close(self):
        self._write_raw(f"=== Sessao encerrada | {self.summary()} ===")
