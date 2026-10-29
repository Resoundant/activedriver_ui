"""Active Driver UDP client and a small hardware demonstration.

Use ActiveDriverUdp as a context manager to close its receiver reliably.
QueryValue uses a 0.5-second timeout and returns [''] on timeout;
query helpers return the first response as a string;
setters and explicitly blocking methods wait until a response arrives.
A client should be used by one command caller at a time.
"""
import ipaddress
import re
import socket
import subprocess
import threading
import time

import netifaces as ni

if __package__:
    from .api import ActiveDriverApi
else:
    from api import ActiveDriverApi

UDP_MESSAGE_DELAY = 0.01


class UdpReceiver:
    """Receive datagrams in the background and buffer them in arrival order."""

    def __init__(self, ip: str, port: int, echo: bool = False):
        self.ip = ip
        self.port = port
        self.echo = echo
        self.msgBuf = []
        self._messages = threading.Condition()
        self.receiver_open = False
        self.listener_thread = None
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self.sock.settimeout(0.5)
            self.sock.bind((ip, port))
        except OSError:
            self.sock.close()
            raise
        self.StartUdpServer()

    def Listener(self):
        # Keep a local reference so shutdown cannot replace it during recvfrom.
        sock = self.sock
        if sock is None:
            return
        try:
            while self.receiver_open:
                try:
                    data, addr = sock.recvfrom(1024)
                except socket.timeout:
                    continue
                except OSError:
                    break
                if self.echo:
                    print(f"received from {addr} : {data.decode(errors='ignore')}")
                with self._messages:
                    if not self.receiver_open:
                        break
                    self.msgBuf.append(data)
                    self._messages.notify_all()
        finally:
            with self._messages:
                self.receiver_open = False
                self._messages.notify_all()

    def StartUdpServer(self):
        if self.receiver_open:
            return
        if self.sock is None:
            raise RuntimeError("A closed UDP receiver cannot be restarted")
        self.receiver_open = True
        self.listener_thread = threading.Thread(target=self.Listener, daemon=True)
        self.listener_thread.start()

    def StopUdpServer(self):
        with self._messages:
            self.receiver_open = False
            self._messages.notify_all()
        if self.sock is not None:
            self.sock.close()
        if self.listener_thread is not None:
            if threading.current_thread() is not self.listener_thread:
                self.listener_thread.join()
            self.listener_thread = None
        self.sock = None
        self.ClearBuffer()

    def MessageWaiting(self):
        with self._messages:
            return bool(self.msgBuf)

    def GetMessage(self, timeout_s: float) -> list:
        """Wait for replies; 0 waits indefinitely, > 0 sets a timeout."""
        return self._wait_for_messages(timeout_s)

    def _wait_for_messages(self, timeout_s: float):
        if timeout_s is None:
            raise TypeError("timeout_s must be a float; use 0 to wait indefinitely")
        with self._messages:
            self._messages.wait_for(
                lambda: bool(self.msgBuf) or not self.receiver_open,
                timeout=None if timeout_s == 0 else timeout_s,
            )
            if self.msgBuf:
                messages = [data.decode() for data in self.msgBuf]
                self.msgBuf.clear()
                return messages
            if not self.receiver_open:
                raise RuntimeError("UDP receiver is closed")
            return [""]

    def ClearBuffer(self):
        with self._messages:
            self.msgBuf.clear()


class ActiveDriverUdp(ActiveDriverApi):
    """Send device commands while receiving replies on a fixed host port."""

    def __init__(self, ad_ip, ad_port, host_ip, host_port):
        self.ip = ad_ip
        self.port = ad_port
        self.udp_receiver = UdpReceiver(host_ip, host_port)
        self.clear_rxbuffer_before_send = True
        self.send_verbose = False
        try:
            self.version: str = self.QueryVersion_smart()
        except Exception:
            self.close()
            raise

    def __del__(self):
        try:
            self.close()
        except Exception:
            pass

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        self.close()
        return False

    def close(self):
        if self.udp_receiver == None:
            return
        if getattr(self, "udp_receiver", None) is not None:
            self.udp_receiver.StopUdpServer()
            self.udp_receiver = None

    def mac_address(self) -> str:
        result = subprocess.run(
            ["arp", self.ip], capture_output=True, text=True, check=False
        )
        match = re.search(r"\b(?:[0-9A-Fa-f]{2}[:-]){5}[0-9A-Fa-f]{2}\b", result.stdout)
        return match.group(0) if match else "NO_MAC"

    def status_ok(self) -> bool:
        try:
            return float(self.QueryVersion_smart()) > 0
        except ValueError:
            return False

    # Utilities

    def GetIp(self):
        return self.ip

    def _command(self, cmd: str) -> str:
        """Send a command and wait for its acknowledgement."""
        self.SendCmd(cmd)
        return self.GetUdpResponse(timeout_s=0.5)[0]

    def SendCmd(self, cmd, empty_buffer=False):
        if empty_buffer or self.clear_rxbuffer_before_send:
            self.ClearRxBuffer()
        data = cmd.encode("ascii")
        if self.send_verbose:
            print(f"{data} to {self.ip}:{self.port}")
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.sendto(data, (self.ip, self.port))
        # time.sleep(UDP_MESSAGE_DELAY)  # Pause between commands (only require for old active drivers)

    def ClearRxBuffer(self):
        if self.udp_receiver:
            self.udp_receiver.ClearBuffer()

    def SetFactoryDefaults(self):
        """Reset device settings; this changes the connected hardware."""
        self.SetAddOkToQuery(0)
        self.SetProfile(0)
        self.SetFrequency(60.0)
        self.SetAmplitude(40.0)
        self.SetPhase(0)
        self.SetDuration(3)
        self.SetTriggerLevel(2.5)
        self.SetTriggerPolarity(1)
        self.ClearRxBuffer()

    def SetFactoryDefaults_bela(self):
        """Reset device settings; this changes the connected hardware."""
        self.SetAddOkToQuery(0)
        self.SetProfile(0)
        self.SetFrequency(60.0)
        self.SetAmplitude(40.0)
        self.SetPhase(0)
        self.SetDuration(3)
        self.SetTriggerSource(1)
        self.SetTriggerLevel(2.5)
        self.SetTriggerPolarity(1)
        self.SetSleepTimer(3600)
        self.ClearRxBuffer()

    def IsOk(self, msg):
        return msg.startswith("OK")

    def GetUdpResponse(self, timeout_s: float = 0.5) -> list:
        """Return replies or [''] on timeout; 0 waits indefinitely."""
        if self.udp_receiver == None:
            raise RuntimeError("UDP receiver is not initialized")
        messages = self.udp_receiver.GetMessage(timeout_s)
        return [msg.rstrip("\x00") for msg in messages]

    def QueryValue(self, cmd, timeout_s: float = 0.5) -> list:
        self.SendCmd(cmd, empty_buffer=True)
        return self.GetUdpResponse(timeout_s=timeout_s)


def find_adapter_for_ip(target_ip: str):
    """Return (interface, IPv4 address, netmask) on the target subnet."""
    target_ip = ipaddress.ip_address(target_ip)
    for iface in ni.interfaces():
        addrs = ni.ifaddresses(iface)
        for addr in addrs.get(ni.AF_INET, []):
            ip = addr.get('addr')
            netmask = addr.get('netmask')
            if ip and netmask:
                iface_net = ipaddress.ip_interface(f"{ip}/{netmask}")
                if target_ip in iface_net.network:
                    return iface, ip, netmask
    return None, None, None


def test_ad_udp_rx():
    """Run a hardware demonstration that changes frequency, amplitude and duration."""
    AD_IP = "192.168.6.2"
    AD_PORT = 2000

    iface, ip, _ = find_adapter_for_ip(target_ip=AD_IP)
    if iface is None:
        print(f'Could not resolve a network device for {AD_IP}')
        return
    print(f'Looking for {AD_IP} on interface {iface}')
    HOST_IP = ip
    HOST_PORT = 2000

    with ActiveDriverUdp(AD_IP, AD_PORT, HOST_IP, HOST_PORT) as ad:
        ad.udp_receiver.echo = True
        ad.send_verbose = True
        ad.SendCmd("+F60.0")
        ad.SendCmd("+A45")
        ad.SendCmd("+D40")
        msg = ad.QueryTriggerPolarity()
        print(f" Message from last command: {msg}")

        num_msgs = len(ad.udp_receiver.msgBuf)
        print("messages waiting: " + str(num_msgs))
        while ad.udp_receiver.MessageWaiting():
            for message in ad.udp_receiver.GetMessage(timeout_s=0.5):
                print(message)


if __name__ == "__main__":
    test_ad_udp_rx()
