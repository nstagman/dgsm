import re
from dgsm.controllers import AppController, cmd, stdout_handler


# Factorio Game Server reseats its stdin handle to the console that executed it (at least on windows)
# Discussion here: https://forums.factorio.com/viewtopic.php?t=75627
# This affects the console interface since Factorio will attempt to read from the terminal
# Setting new_console to True in the config file (in 'opts' dict) is the only current workaround for this scenario

class FactorioController(AppController):
    VERSION    = re.compile(r'(?:Factorio )([\w.]+)(?: \(build)', re.IGNORECASE)
    ONLINE     = re.compile(r'(Hosting game at IP ADDR)', re.IGNORECASE)
    CONNECT    = re.compile(r'(?:\[JOIN\] )(\w+)(?: joined the game)', re.IGNORECASE)
    DISCONNECT = re.compile(r'(?:\[LEAVE\] )(\w+)(?: left the game)', re.IGNORECASE)
    def __init__(self, name:str, **kwargs) -> None:
        super().__init__(name, **kwargs)

    @classmethod
    def ID(cls) -> str: return 'factorio'

    # Tag the four methods for handling app output with this apps regex patterns
    @stdout_handler(VERSION)
    def _handle_version(self, match: re.Match) -> None:
        return super()._handle_version(match)
    
    @stdout_handler(ONLINE)
    def _handle_online(self, match: re.Match) -> None:
        return super()._handle_online(match)
    
    @stdout_handler(CONNECT)
    def _handle_connect(self, match: re.Match) -> None:
        return super()._handle_connect(match)
    
    @stdout_handler(DISCONNECT)
    def _handle_disconnect(self, match: re.Match) -> None:
        return super()._handle_disconnect(match)
