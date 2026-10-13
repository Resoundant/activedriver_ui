"""
res_ad_udp.py
Interface for active driver API over UDP
"""
import time
import socket
import threading
import re
import subprocess
# below used for API test
import netifaces as ni
import ipaddress
from datetime import datetime

UDP_MESSAGE_DELAY = 0.01

# AD_IP = "10.0.1.30"
# AD_PORT = 2000
# #Hack - vm only has one wired interface, really I should find the interface
# # whose subnet includes a route to AD_IP
# #HOST_IP = "127.0.0.1"
# #ni.ifaddresses('enp0s3')
# HOST_IP = ni.ifaddresses('enp0s3')[ni.AF_INET][0]['addr']
# HOST_UDP_PORT = 2000

#receiver
class UdpReceiver:
    def __init__(self, ip:str, port:int, echo:bool=False):
        self.ip = ip
        self.port = port
        self.msgBuf = []
        self.sock = socket.socket(
            socket.AF_INET, # Internets
            socket.SOCK_DGRAM) # UDP
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)  # allow rebinding
        self.sock.settimeout(0.5)  # allow Listener to check receiver_open regularly
        self.sock.bind((self.ip, self.port))
        self.echo:bool = echo
        self.listener_thread = -99
        self.receiver_open = False
        self.StartUdpServer()
        return
    def Listener(self):
        while self.receiver_open: 
            try:
                data, addr = self.sock.recvfrom(1024)
            except socket.timeout:
                continue
            except OSError:
                break  # socket closed
            if self.echo:
                msg = data.decode(errors="ignore")  # safe decode
                print(f"received from {addr} : {msg}")
            self.msgBuf.append(data)
        return
    def StartUdpServer(self):
        self.receiver_open = True
        self.listener_thread = threading.Thread(target=self.Listener, daemon=True)
        self.listener_thread.start()
        return
    def StopUdpServer(self):
        if not self.receiver_open:
            return
        self.receiver_open = False
        if self.sock:
            try:
                self.sock.close()  # unblock recvfrom on Windows
            except OSError:
                pass
            self.sock = None
        if self.listener_thread != -99:
            if threading.current_thread() is not self.listener_thread:
                self.listener_thread.join()
            self.listener_thread = -99
        self.ClearBuffer()
        return
    def MessageWaiting(self):
        if len(self.msgBuf) > 0:
            return True
        return False
    def GetMessage(self):
        if len(self.msgBuf) > 0:
            return self.msgBuf.pop(0).decode()
        return ''
    def GetMessageAsList(self):
        msglist = []
        while len(self.msgBuf) > 0:
            msglist.append(self.msgBuf.pop(0).decode())
        return msglist
    def GetMessageAsListWithTimeout(self, timeout_s:float) -> list:
        # returns msg_lst if message received within timeout_s
        # returns ['timeout'] if message takes too long.
        # use with caution - could be racey if messages come in slowly
        tm = time.time()
        while (not self.MessageWaiting()) and (time.time() <= tm+timeout_s):
            pass
        if (time.time() >= tm+timeout_s):
            return ['']
        else:
            return self.GetMessageAsList()
    def ClearBuffer(self):
        self.msgBuf.clear()




class ActiveDriverUdp:
    def __init__(self, ad_ip, ad_port, host_ip, host_port):
        self.ip = ad_ip
        self.port = ad_port
        self.udp_receiver = UdpReceiver(host_ip, host_port)
        self.test_simulation_active = False
        self.clear_rxbuffer_before_send = True
        self.send_verbose = False
        self.version:str = self.QueryVersion_smart()
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
        if self.udp_receiver: # perotect against double close
            self.udp_receiver.StopUdpServer()
            self.udp_receiver = None
    def mac_address(self) -> str: 
        if self.test_simulation_active:
            return '001122AABBCC'
        ''' MAC format todo: define here'''
        arp_cmd = f"arp {self.ip}"
        arp_out = subprocess.run(arp_cmd, shell=True, capture_output=True, text=True).stdout
        parts = re.split(r'\s+', arp_out)
        if len(parts)>8:
            return parts[8]
        else:
            return 'NO_MAC'
    def status_ok(self) -> bool:
        version = self.QueryVersion_smart()
        try:
            if (float(version) > 0 ):
                return True
        except:
            pass
        return False


# "Setting Profile Information"
    def SetProfile(self, val: int) -> str:
        cmd = "+P"+str(val)
        self.SendCmd(cmd)
        return self.GetUdpResponse()

    def SetFrequency(self, val: float) -> str:
        cmd = "+F"+str(val)
        self.SendCmd(cmd)
        return self.GetUdpResponse()

    def SendCmdToSocket(self, cmd:str, sock:socket.socket, float_delay_s=0.01):
        sock.sendto(cmd.encode("ascii"), (self.ip, self.port))
        time.sleep(float_delay_s)

    def SetAmplitude(self, val: float) -> str:
        cmd = "+A"+str(val)
        self.SendCmd(cmd)
        return self.GetUdpResponse()

    def SetDuration(self, val: int) -> str:
        val = int(val)
        cmd = "+D"+str(val)
        self.SendCmd(cmd)
        return self.GetUdpResponse()
    
    def SetWaveformType(self, val: int) -> str:
        # 0 sine, 1 custom
        val = int(val)
        cmd = "+S"+str(val)
        self.SendCmd(cmd)
        return self.GetUdpResponse()

    def SetPhase(self, val: float) -> str:
        cmd = "+p"+str(val)
        self.SendCmd(cmd)  
        return self.GetUdpResponse()

    def SetWaveformInverted(self, val: int) -> str:
        # 0 standard, 1 inverted # TODO CHECK SRC
        val = int(val)
        cmd = "+I"+str(val)
        self.SendCmd(cmd)
        return self.GetUdpResponse()


# "Getting profile information"
    def QueryProfile(self) -> str:
        return self.QueryValue("?P")

    def QueryFrequency(self) -> str:
        return self.QueryValue("?F") 

    def QueryAmplitude(self) -> str:
        return self.QueryValue("?A")
    
    def QuerySoftStart(self) -> str:
        return self.QueryValue("?R")
    def QuerySoftStartSec(self) -> str:
        return self.QueryValue("?r")

    def QueryDuration(self) -> str:
        return self.QueryValue("?D") 

    def QueryWaveformType(self) -> str:
        return self.QueryValue("?S")

    def QueryPhase(self) -> str:
        return self.QueryValue("?p") 

    def QueryWaveformInverted(self) -> str:
        return self.QueryValue("?I")
    
    def QuerySleepTimer(self) -> str:
        return self.QueryValue("?Z")

    def QueryTimeUntilSleep(self) -> str:
        return self.QueryValue("?U")

# "System parameters"
    def Login(self) -> str:
        cmd = '+Lresoundant'
        self.SendCmd(cmd)
        return self.GetUdpResponse()

    def Logout(self) -> str:
        cmd = '*L'
        self.SendCmd(cmd)
        return self.GetUdpResponse()

    def QueryVersion_legacy(self) -> str:
        ''' Uses ?v, returns entire string of version.  Use QueryVersion'''
        return self.QueryValue("?v") # msg_tmp = 'Ver 22.00 blah blah blah'
    def QueryVersion_v2(self) -> str:
        ''' Uses ?V, valid for 30.xx and later, numerical only result'''
        return self.QueryValue("?V") # msg_tmp = '30.00'
    def QueryVersion_smart(self) -> str:
        msg_tmp = self.QueryVersion_v2() 
        try:
            float(msg_tmp)
            return msg_tmp
        except:
            pass
        if msg_tmp == '':
            return '0.0'
        if msg_tmp.startswith('ERR'):
            msg_tmp = self.QueryVersion_legacy()
            msg = msg_tmp.split(' ')[1] # grab second field (number after 'Version')
            return msg
        else: # must be a dev, like 30.01a
            print(f"Version is oddly formatted, stripping non-numerals from: {msg_tmp}")
            msg = ''.join(ch for ch in msg_tmp if ch == '.' or '0' <= ch <= '9')
            return msg

    def QueryVersion_raw(self) -> str:
        ''' Return the full/raw string of ?V or ?v, if ?V returns ERR099 '''
        msg_tmp = self.QueryVersion_v2() 
        if msg_tmp == '':
            return '0.0'
        if msg_tmp != 'ERR099':
            return msg_tmp
        msg_tmp = self.QueryVersion_legacy()
        return msg_tmp


    def QueryCycleCount(self):
        return self.QueryValue("?C") 

    # cycle count reset +C # TODO

    def SetTriggerLevel(self, val:float) -> str:
        cmd = '+T'+str(val)
        self.SendCmd(cmd)
        return self.GetUdpResponse()

    def SetTriggerPolarity(self, val) -> str:
        val = int(val)
        cmd = '+t'+str(val)
        self.SendCmd(cmd)
        return self.GetUdpResponse()
    
    def SetTriggerSource(self, val: int) -> str:
        # 0 = none, 1 = BNC, 2 = fiber, 3 = Aux1
        cmd = "+s"+str(int(val))
        self.SendCmd(cmd)
        return self.GetUdpResponse()
    
    def SetAddOkToQuery(self, val: int) -> str:
        # false = no ok, true = add ok
        cmd = "+Q"+str(int(val))
        self.SendCmd(cmd)
        return self.GetUdpResponse()
    
    def SetSleepTimer(self, seconds: int):
        cmd = "+Z"+str(int(seconds))
        self.SendCmd(cmd)
        return self.GetUdpResponse()

    def ManualTrigger(self):
        return self.SoftwareTrigger()

    def SoftwareTrigger(self) -> str:
        cmd = "*G"
        self.SendCmd(cmd)
        return self.GetUdpResponse()   

    def QueryTriggerLevel(self) -> str:
        cmd = "?T"
        self.SendCmd(cmd)
        return self.GetUdpResponse() 

    def QueryTriggerPolarity(self) -> str:
        cmd = "?t"
        self.SendCmd(cmd)
        return self.GetUdpResponse()

    def QueryTriggerSource(self) -> str:
        return self.QueryValue("?s")

    def GoToSleep(self) -> str:
        cmd = "*Z"
        self.SendCmd(cmd)
        return self.GetUdpResponse()
    
    def Wakeup(self) -> str:
        cmd = "*U"
        self.SendCmd(cmd)
        return self.GetUdpResponse()

    def SetSoftStart(self, val: int) -> str:
        # legacy method - set ramp count
        cmd = "+R" + str(int(val))
        self.SendCmd(cmd)
        return self.GetUdpResponse()

    def SetSoftStartSec(self, val: float) -> str:
        cmd = "+r" + str(val)
        self.SendCmd(cmd)
        return self.GetUdpResponse()



# utilities
    def GetIp(self):
        return self.ip

    def SendCmd(self, cmd, empty_buffer=False):
        if empty_buffer:
            self.ClearRxBuffer()
        elif self.clear_rxbuffer_before_send:
            self.ClearRxBuffer()
        if self.send_verbose:
            print(f"{cmd.encode("ascii")} to {self.ip}:{self.port}")
        sock = socket.socket(socket.AF_INET, # Internet
                            socket.SOCK_DGRAM) # UDP
        sock.sendto(cmd.encode("ascii"), (self.ip, self.port))
        sock.close()
        time.sleep(UDP_MESSAGE_DELAY) #force delay so we can't spam the AD

    def ClearRxBuffer(self):
        self.udp_receiver.ClearBuffer()

    def SetFactoryDefaults(self):
        #don't use this for testing, only use it as a reset
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
        #don't use this for testing, only use it as a reset
        if self.test_simulation_active:
            return
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
        if msg.startswith('OK'):
            return True
        else:
            return False

    def GetUdpResponse(self) -> str:
        msg_lst = self.GetUdpResponseAsList()
        return msg_lst[0]
    def GetUdpResponseAsList(self) -> list:
        while (not self.udp_receiver.MessageWaiting()): pass
        msg_raw = self.udp_receiver.GetMessageAsList()
        msg_list = []
        for m in msg_raw:
            msg_list.append(m.rstrip('\x00'))
        return msg_list
    def GetUdpResponse_withTimeout(self, timeout_s=0.5) -> list:
        msg_raw = self.udp_receiver.GetMessageAsListWithTimeout(timeout_s)
        msg_list = []
        for m in msg_raw:
            msg_list.append(m.rstrip('\x00'))
        return msg_list

    def QueryValue(self, cmd):
        self.ClearRxBuffer()
        self.SendCmd(cmd)
        msg_list = self.GetUdpResponse_withTimeout()
        return msg_list[0]
    def QueryValue_blocking(self, cmd):
        self.ClearRxBuffer()
        self.SendCmd(cmd)
        msg_list = self.GetUdpResponse()
        return msg_list[0]
    def QueryValue_ReturnList(self, cmd):
        self.ClearRxBuffer()
        self.SendCmd(cmd)
        msg_list = self.GetUdpResponse_withTimeout()
        return msg_list
    def QueryValue_ReturnList_blocking(self, cmd):
        self.ClearRxBuffer()
        self.SendCmd(cmd)
        msg_list = self.GetUdpResponseAsList()
        return msg_list


def find_adapter_for_ip(target_ip: str):
    target_ip = ipaddress.ip_address(target_ip)
    for iface in ni.interfaces():
        addrs = ni.ifaddresses(iface)
        if ni.AF_INET in addrs:
            for addr in addrs[ni.AF_INET]:
                ip = addr['addr']
                netmask = addr.get('netmask')
                if ip and netmask:
                    iface_net = ipaddress.ip_interface(f"{ip}/{netmask}")
                    if target_ip in iface_net.network:
                        return iface, ip, netmask
    return None, None, None



def test_ad_udp_rx():
    # System setup
    #AD_IP = "10.0.1.30"
    AD_IP = "192.168.6.2"
    AD_PORT = 2000

    # HOST_IP = "192.168.1.157"
    iface, ip, netmask = find_adapter_for_ip(target_ip=AD_IP)
    if iface is None:
        print(f'Could not resolve a network device for {AD_IP}')
        return
    print(f'Looking for {AD_IP} on interface {iface}')
    HOST_IP = ni.ifaddresses(iface)[ni.AF_INET][0]['addr']
    HOST_PORT = 2000

    with ActiveDriverUdp(AD_IP, AD_PORT, HOST_IP, HOST_PORT) as ad:
        if ad is None or ad.udp_receiver is None:
            print(f"Error creating receiver interface for Active Driver")
            return
        ad.udp_receiver.echo = True
        ad.send_verbose = True
        ad.SendCmd("+F60.0")
        ad.SendCmd("+A45")
        ad.SendCmd("+D40")
        msg = ad.QueryTriggerPolarity()
        print(f" Message from last command: {msg}")

        # uncomment to test receiver from external client
        num_msgs = len(ad.udp_receiver.msgBuf)
        print("messages waiting: " + str(num_msgs))
        while(ad.udp_receiver.MessageWaiting()):
            print(ad.udp_receiver.GetMessage())
    return

if __name__ == "__main__":
    test_ad_udp_rx()

    exit()

