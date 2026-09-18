"""
proxy_manager.py
------------------
Ajusta o proxy do SISTEMA no Windows (Configuracoes de Internet), fazendo
com que TODOS os navegadores e aplicativos que respeitam essa configuracao
(Chrome, Brave, Edge, etc.) passem a rotear seu trafego pelo SOCKS5 do Tor.

Guarda os valores originais do registro para restaurar tudo ao sair,
mesmo em caso de fechamento inesperado (ver torshift.py / atexit).
"""

import sys
import ctypes

IS_WINDOWS = sys.platform.startswith("win")

if IS_WINDOWS:
    import winreg

INTERNET_SETTINGS_PATH = r"Software\Microsoft\Windows\CurrentVersion\Internet Settings"

# Constantes usadas para avisar o Windows que as configuracoes de internet mudaram
INTERNET_OPTION_SETTINGS_CHANGED = 39
INTERNET_OPTION_REFRESH = 37


class ProxyManagerError(Exception):
    pass


class ProxyManager:
    def __init__(self):
        if not IS_WINDOWS:
            raise ProxyManagerError(
                "O gerenciamento de proxy do sistema so e suportado no Windows."
            )
        self._original = {}
        self._active = False

    # ------------------------------------------------------------------
    def _open_key(self, write=False):
        access = winreg.KEY_SET_VALUE | winreg.KEY_QUERY_VALUE if write else winreg.KEY_QUERY_VALUE
        return winreg.OpenKey(winreg.HKEY_CURRENT_USER, INTERNET_SETTINGS_PATH, 0, access)

    def _backup_current_settings(self):
        """Guarda o estado atual do proxy para poder restaurar depois."""
        try:
            with self._open_key() as key:
                try:
                    self._original["ProxyEnable"], _ = winreg.QueryValueEx(key, "ProxyEnable")
                except FileNotFoundError:
                    self._original["ProxyEnable"] = 0
                try:
                    self._original["ProxyServer"], _ = winreg.QueryValueEx(key, "ProxyServer")
                except FileNotFoundError:
                    self._original["ProxyServer"] = ""
        except OSError as e:
            raise ProxyManagerError(f"Nao foi possivel ler as configuracoes de proxy atuais: {e}")

    def _refresh_system(self):
        """Forca o Windows a recarregar as configuracoes de internet imediatamente."""
        internet_set_option = ctypes.windll.Wininet.InternetSetOptionW
        internet_set_option(0, INTERNET_OPTION_SETTINGS_CHANGED, 0, 0)
        internet_set_option(0, INTERNET_OPTION_REFRESH, 0, 0)

    # ------------------------------------------------------------------
    def enable_socks_proxy(self, host="127.0.0.1", port=9050):
        self._backup_current_settings()
        try:
            with self._open_key(write=True) as key:
                winreg.SetValueEx(key, "ProxyEnable", 0, winreg.REG_DWORD, 1)
                winreg.SetValueEx(key, "ProxyServer", 0, winreg.REG_SZ, f"socks={host}:{port}")
        except OSError as e:
            raise ProxyManagerError(f"Falha ao aplicar proxy do sistema: {e}")

        self._refresh_system()
        self._active = True

    # ------------------------------------------------------------------
    def disable_proxy(self):
        """Restaura o proxy do sistema para o estado anterior ao uso do TorShift."""
        if not self._original:
            return  # nada para restaurar

        try:
            with self._open_key(write=True) as key:
                winreg.SetValueEx(key, "ProxyEnable", 0, winreg.REG_DWORD,
                                   self._original.get("ProxyEnable", 0))
                winreg.SetValueEx(key, "ProxyServer", 0, winreg.REG_SZ,
                                   self._original.get("ProxyServer", ""))
        except OSError as e:
            raise ProxyManagerError(f"Falha ao restaurar proxy original: {e}")

        self._refresh_system()
        self._active = False

    @property
    def is_active(self):
        return self._active
