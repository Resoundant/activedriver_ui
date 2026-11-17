"""Active Driver API commands shared by transport implementations."""

from abc import ABC, abstractmethod
import re
import socket
import time


class ActiveDriverApi(ABC):
    """Device commands using the transport's _command and QueryValue methods."""

    ip: str
    port: int

    @abstractmethod
    def _command(self, cmd: str) -> str:
        """Send a command through the transport and return its response."""
        raise NotImplementedError

    @abstractmethod
    def QueryValue(self, cmd: str, timeout_s: float = 0.5) -> list[str]:
        """Query the transport and return its response messages."""
        raise NotImplementedError

    # Setting Profile Information

    def SetProfile(self, val: int) -> str:
        return self._command("+P" + str(val))

    def SetFrequency(self, val: float) -> str:
        return self._command("+F" + str(val))

    def SendCmdToSocket(self, cmd: str, sock: socket.socket, float_delay_s=0.01):
        sock.sendto(cmd.encode("ascii"), (self.ip, self.port))
        time.sleep(float_delay_s)

    def SetAmplitude(self, val: float) -> str:
        return self._command("+A" + str(val))

    def SetDuration(self, val: int) -> str:
        return self._command("+D" + str(int(val)))

    def SetWaveformType(self, val: int) -> str:
        # 0 sine, 1 custom
        return self._command("+S" + str(int(val)))

    def SetPhase(self, val: float) -> str:
        return self._command("+p" + str(val))

    def SetWaveformInverted(self, val: int) -> str:
        # 0 standard, 1 inverted
        return self._command("+I" + str(int(val)))

    # Getting profile information

    def QueryProfile(self) -> str:
        return self.QueryValue("?P")[0]

    def QueryFrequency(self) -> str:
        return self.QueryValue("?F")[0]

    def QueryAmplitude(self) -> str:
        return self.QueryValue("?A")[0]

    def QuerySoftStart(self) -> str:
        return self.QueryValue("?R")[0]

    def QuerySoftStartSec(self) -> str:
        return self.QueryValue("?r")[0]

    def QueryDuration(self) -> str:
        return self.QueryValue("?D")[0]

    def QueryWaveformType(self) -> str:
        return self.QueryValue("?S")[0]

    def QueryPhase(self) -> str:
        return self.QueryValue("?p")[0]

    def QueryWaveformInverted(self) -> str:
        return self.QueryValue("?I")[0]

    def QuerySleepTimer(self) -> str:
        return self.QueryValue("?Z")[0]

    def QueryTimeUntilSleep(self) -> str:
        return self.QueryValue("?U")[0]

    # System parameters

    def Login(self) -> str:
        return self._command('+Lresoundant')

    def Logout(self) -> str:
        return self._command('*L')

    def QueryVersoion(self):
        return self.QueryVersion_smart()

    def QueryVersion_legacy(self) -> str:
        """Return the full legacy version banner using ?v."""
        return self.QueryValue("?v")[0]

    def QueryVersion_v2(self) -> str:
        """Query the numerical version using ?V (firmware 30.xx and later)."""
        return self.QueryValue("?V")[0]

    def QueryVersion_smart(self) -> str:
        version = self.QueryVersion_v2()
        if not version:
            return "0.0"
        try:
            float(version)
            return version
        except ValueError:
            pass
        if version.startswith("ERR"):
            version = self.QueryVersion_legacy()
        # Accept both legacy banners and development suffixes (e.g. 30.01a).
        match = re.search(r"[0-9]+(?:\.[0-9]+)?", version)
        return match.group(0) if match and not version.startswith("ERR") else "0.0"

    def QueryVersion_raw(self) -> str:
        """Return the raw version, falling back to ?v for ERR099."""
        msg_tmp = self.QueryVersion_v2()
        if msg_tmp == '':
            return '0.0'
        if msg_tmp != 'ERR099':
            return msg_tmp
        return self.QueryVersion_legacy()

    def QueryCycleCount(self) -> str:
        return self.QueryValue("?C")[0]

    def SetTriggerLevel(self, val: float) -> str:
        return self._command('+T' + str(val))

    def SetTriggerPolarity(self, val) -> str:
        return self._command('+t' + str(int(val)))

    def SetTriggerSource(self, val: int) -> str:
        # 0 = none, 1 = BNC, 2 = fiber, 3 = Aux1
        return self._command("+s" + str(int(val)))

    def SetAddOkToQuery(self, val: int) -> str:
        # false = no ok, true = add ok
        return self._command("+Q" + str(int(val)))

    def SetSleepTimer(self, seconds: int):
        return self._command("+Z" + str(int(seconds)))

    def ManualTrigger(self):
        return self.SoftwareTrigger()

    def SoftwareTrigger(self) -> str:
        return self._command("*G")

    def QueryTriggerLevel(self) -> str:
        return self._command("?T")

    def QueryTriggerPolarity(self) -> str:
        return self._command("?t")

    def QueryTriggerSource(self) -> str:
        return self.QueryValue("?s")[0]

    def GoToSleep(self) -> str:
        return self._command("*Z")

    def Wakeup(self) -> str:
        return self._command("*U")

    def SetSoftStart(self, val: int) -> str:
        # legacy method - set ramp count
        return self._command("+R" + str(int(val)))

    def SetSoftStartSec(self, val: float) -> str:
        return self._command("+r" + str(val))

