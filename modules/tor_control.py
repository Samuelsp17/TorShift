"""
tor_control.py
----------------
Comunicacao direta com o ControlPort do Tor (protocolo texto, sem depender
da biblioteca 'stem', para manter a ferramenta leve e transparente).

Responsavel por:
  - Autenticar no ControlPort usando a senha configurada no torrc
  - Solicitar uma nova identidade (SIGNAL NEWNYM)
  - Consultar o IP de saida atual usando o proxy SOCKS5 do Tor
"""

import socket
import requests


class TorControlError(Exception):
    pass


class TorController:
    def __init__(self, control_host="127.0.0.1", control_port=9051,
                 control_password="", socks_host="127.0.0.1", socks_port=9050):
        self.control_host = control_host
        self.control_port = control_port
        self.control_password = control_password
        self.socks_host = socks_host
        self.socks_port = socks_port
        self._sock = None

    # ------------------------------------------------------------------
    def connect(self):
        try:
            self._sock = socket.create_connection(
                (self.control_host, self.control_port), timeout=10
            )
        except OSError as e:
            raise TorControlError(
                f"Nao foi possivel conectar ao ControlPort "
                f"({self.control_host}:{self.control_port}). "
                f"O Tor esta rodando? Detalhe: {e}"
            )

        auth_cmd = f'AUTHENTICATE "{self.control_password}"\r\n'
        response = self._send(auth_cmd)

        if not response.startswith("250"):
            raise TorControlError(
                "Falha na autenticacao do ControlPort. Verifique se "
                "'control_password' no config.json bate com o "
                "HashedControlPassword configurado no torrc."
            )

    # ------------------------------------------------------------------
    def _send(self, command: str) -> str:
        if self._sock is None:
            raise TorControlError("Tentativa de uso do ControlPort sem conexao ativa.")
        self._sock.sendall(command.encode("utf-8"))
        data = self._sock.recv(4096)
        return data.decode("utf-8", errors="ignore")

    # ------------------------------------------------------------------
    def new_identity(self):
        response = self._send("SIGNAL NEWNYM\r\n")
        if not response.startswith("250"):
            raise TorControlError(f"Falha ao solicitar novo circuito: {response.strip()}")

    # ------------------------------------------------------------------
    def get_current_ip(self, timeout=15) -> dict:
        """
        Consulta o IP de saida atual atraves do proxy SOCKS5 do Tor.
        Retorna dict: {"ip": str, "is_tor": bool}
        """
        proxies = {
            "http": f"socks5h://{self.socks_host}:{self.socks_port}",
            "https": f"socks5h://{self.socks_host}:{self.socks_port}",
        }
        try:
            resp = requests.get(
                "https://check.torproject.org/api/ip",
                proxies=proxies,
                timeout=timeout,
            )
            data = resp.json()
            return {"ip": data.get("IP"), "is_tor": bool(data.get("IsTor"))}
        except Exception as e:
            raise TorControlError(f"Falha ao consultar IP de saida: {e}")

    # ------------------------------------------------------------------
    def get_country(self, ip: str, timeout=10):
        """Lookup opcional de geolocalizacao (best-effort, nao critico)."""
        proxies = {
            "http": f"socks5h://{self.socks_host}:{self.socks_port}",
            "https": f"socks5h://{self.socks_host}:{self.socks_port}",
        }
        try:
            resp = requests.get(f"https://ipapi.co/{ip}/country_name/",
                                 proxies=proxies, timeout=timeout)
            country = resp.text.strip()
            return country if resp.status_code == 200 and country else None
        except Exception:
            return None

    # ------------------------------------------------------------------
    def close(self):
        if self._sock:
            try:
                self._sock.sendall(b"QUIT\r\n")
                self._sock.close()
            except OSError:
                pass
            self._sock = None
