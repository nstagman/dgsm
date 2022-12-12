import upnpclient
import netifaces
import logging


# networked devices with malformed upnp attributes fill the console with warnings...
# stop this from happening
logging.getLogger('ssdp').disabled = True


# fallback for getting local ip
def _get_local_ip() -> str:
    interfaces = netifaces.interfaces()
    for i in interfaces:
        if i == 'lo': continue
        iface = netifaces.ifaddresses(i).get(netifaces.AF_INET)
        if iface != None: return iface[0]['addr']
        return ''

# return upnp router object
# returns first object discovered that contains the WANIPConn1 attribute
def get_router():
    devices = upnpclient.discover()
    router = None
    for device in devices:
        if getattr(device, 'WANIPConn1', None):
            router = device
            break
    return router

def open_ports(desc:str, port_start:int, port_end:int=0, proto:str='both', addr:str='', router=None):
    if not router: router = get_router()
    if not router: return False
    if not addr: addr = _get_local_ip()
    if not addr: return False
    if not port_end: port_end = port_start
    
    def map_port(desc:str, proto:str, port:int, addr:str):
        def add_port_mapping(protocol):
            try:
                router.WANIPConn1.AddPortMapping(
                    NewRemoteHost='',
                    NewExternalPort=port,
                    NewProtocol=protocol,
                    NewInternalPort=port,
                    NewInternalClient=addr,
                    NewEnabled='1',
                    NewPortMappingDescription=desc,
                    NewLeaseDuration=0 #linksys needs this to be 0 - have not tested other routers...
                )
            except BaseException as e:
                print(f'Error occured when mapping {port} for {desc}. {port} will not be open')
        
        match proto.casefold():
            case 'tcp':
                add_port_mapping('TCP')
            case 'udp':
                add_port_mapping('UDP')
            case 'both':
                add_port_mapping('TCP')
                add_port_mapping('UDP')
            case _:
                print(f'Unable to map {port} for {desc}. The specified protocol does not exist')
    
    for port in range(port_start, port_end+1):
        map_port(desc, proto, port, addr)
    
    return True
