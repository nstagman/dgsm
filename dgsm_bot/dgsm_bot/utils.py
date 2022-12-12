from ping3 import ping
import socket
from textwrap import wrap

# attempt to ping an ip address
# returns True if device responds to ping
def is_online(ip: str, timeout: float=0.1) -> bool:
    res = not not ping(ip, timeout=timeout)
    for i in range(4):
        if res: break
        res = res or not not ping(ip, timeout=timeout)
    return res

# generates and sends magic packet for mac
# ip defaults to broadcast address and port defaults to wake-on-lan port
# returns True when the magic packet is successfully sent
def wol(mac: str, ip: str='255.255.255.255', port: int=9) -> bool:
    if len(mac) == 17: mac = mac.replace(mac[2], '')
    if len(mac) != 12: return False
    packet = bytes.fromhex('F'*12 + mac*16)
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        sock.connect((ip, port))
        sock.send(packet)
    return True

# generator to split a message into chunks of 'size'
def message_chunks(message:str, size:int):
        for sub in wrap(message, size, replace_whitespace=False, drop_whitespace=False):
            yield sub