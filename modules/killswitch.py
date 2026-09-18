"""
killswitch.py
---------------
Kill switch opcional (o usuario decide se ativa ou nao).

O que ele faz:
  1. Roda um "heartbeat" em background, checando periodicamente se o
     trafego realmente esta saindo pelo Tor (via check.torproject.org).
  2. Se a checagem falhar, mostra um POPUP NATIVO do Windows avisando
     "TOR nao conectado, erro..." e aplica regras temporarias no
     Firewall do Windows para reduzir o risco de vazamento de trafego
     fora do Tor enquanto o problema nao e resolvido.
  3. Quando o Tor volta a responder normalmente, remove as regras e
     (opcionalmente) avisa que a conexao foi normalizada.

LIMITACAO IMPORTANTE (leia isso antes de confiar cegamente no kill switch):
  O Firewall do Windows, por padrao, da PRIORIDADE a regras de bloqueio
  sobre regras de liberacao quando ambas combinam com o mesmo trafego.
  Isso significa que a combinacao "permitir tor.exe" + "bloquear tudo"
  usada aqui e uma protecao BEST-EFFORT, nao uma garantia absoluta em
  nivel de kernel (isso exigiria um driver WFP dedicado, fora do escopo
  desta ferramenta). Para a maioria dos usos (evitar que o navegador
  volte a navegar "exposto" apos uma queda do Tor) ela e suficiente,
  mas nao trate isso como uma garantia de anonimato a prova de falhas.
"""

import sys
import time
import ctypes
import threading
import subprocess

IS_WINDOWS = sys.platform.startswith("win")

RULE_ALLOW_TOR = "TorShift_Allow_Tor"
RULE_ALLOW_LOOPBACK = "TorShift_Allow_Loopback"
RULE_BLOCK_ALL = "TorShift_KillSwitch_Block"

MB_ICONWARNING = 0x30
MB_OK = 0x0


class KillSwitch:
    def __init__(self, tor_controller, tor_exe_path="", check_interval=10,
                 logger=None, notify_on_recovery=True):
        self.tor_controller = tor_controller
        self.tor_exe_path = tor_exe_path
        self.check_interval = check_interval
        self.logger = logger
        self.notify_on_recovery = notify_on_recovery

        self._thread = None
        self._stop_event = threading.Event()
        self._blocked = False

    # ------------------------------------------------------------------
    def start(self):
        if not IS_WINDOWS:
            print("[Kill Switch] Aviso: bloqueio via firewall so e suportado no Windows. "
                  "O monitoramento vai rodar, mas sem aplicar regras de bloqueio.")
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._heartbeat_loop, daemon=True)
        self._thread.start()

    def stop(self):
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=5)
        if self._blocked:
            self._deactivate_block()

    # ------------------------------------------------------------------
    def _heartbeat_loop(self):
        while not self._stop_event.is_set():
            tor_ok = self._check_tor()

            if not tor_ok and not self._blocked:
                self._show_popup(
                    "TorShift - Alerta",
                    "TOR nao conectado, erro na conexao. Verifique o servico Tor.\n\n"
                    "O TorShift vai tentar restringir o trafego de saida ate a conexao normalizar."
                )
                if self.logger:
                    self.logger.log_killswitch_event(True, "Falha na verificacao IsTor")
                self._activate_block()

            elif tor_ok and self._blocked:
                self._deactivate_block()
                if self.logger:
                    self.logger.log_killswitch_event(False)
                if self.notify_on_recovery:
                    self._show_popup(
                        "TorShift - Reconectado",
                        "TOR reconectado com sucesso. Trafego liberado normalmente."
                    )

            self._stop_event.wait(self.check_interval)

    # ------------------------------------------------------------------
    def _check_tor(self) -> bool:
        try:
            status = self.tor_controller.get_current_ip(timeout=8)
            return bool(status.get("is_tor"))
        except Exception:
            return False

    # ------------------------------------------------------------------
    def _show_popup(self, title: str, message: str):
        if not IS_WINDOWS:
            print(f"[POPUP SIMULADO] {title}: {message}")
            return
        try:
            ctypes.windll.user32.MessageBoxW(0, message, title, MB_OK | MB_ICONWARNING)
        except Exception as e:
            print(f"[Kill Switch] Falha ao exibir popup: {e}")

    # ------------------------------------------------------------------
    def _run_netsh(self, args):
        try:
            subprocess.run(
                ["netsh"] + args,
                check=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            return True
        except Exception as e:
            print(f"[Kill Switch] Falha ao executar regra de firewall: {e}")
            return False

    def _activate_block(self):
        if not IS_WINDOWS:
            self._blocked = True
            return

        # Libera trafego local (loopback)
        self._run_netsh([
            "advfirewall", "firewall", "add", "rule",
            f"name={RULE_ALLOW_LOOPBACK}", "dir=out", "action=allow",
            "remoteip=127.0.0.1",
        ])

        # Libera o processo do proprio Tor, para que ele consiga se recuperar sozinho
        if self.tor_exe_path:
            self._run_netsh([
                "advfirewall", "firewall", "add", "rule",
                f"name={RULE_ALLOW_TOR}", "dir=out", "action=allow",
                f"program={self.tor_exe_path}",
            ])

        # Bloqueia o restante do trafego de saida (best-effort, ver docstring do modulo)
        self._run_netsh([
            "advfirewall", "firewall", "add", "rule",
            f"name={RULE_BLOCK_ALL}", "dir=out", "action=block",
        ])

        self._blocked = True

    def _deactivate_block(self):
        if IS_WINDOWS:
            for rule_name in (RULE_BLOCK_ALL, RULE_ALLOW_TOR, RULE_ALLOW_LOOPBACK):
                self._run_netsh([
                    "advfirewall", "firewall", "delete", "rule", f"name={rule_name}"
                ])
        self._blocked = False
