import argparse
from pathlib import Path
import os
import yaml
from dgsm_bot.dbot import create_dbot


CFG_FILE_NAME = 'cfg_dbot.yaml'
CONFIG = '''
token: <private-discord-bot-token>  #Required - discord bot token
prefix: $  #Optional - sets prefix for your discord bot to interpret message content
mac: <MAC Address of DGSM Host>  #Optional - If DGSM is on a separate host, allows this bot to wake-on-lan the DGSMHost
#Socket information Required - DGSM communication - this should be identical to the DGSM socket information
address: localhost  #local host can be used if this bot is running on the same host as the DGSM, otherwise use DGSM host IP
port: 8888  #Socket will be opened at address:port (localhost:8888 in this example)
'''

if __name__ == '__main__':
    # returns absolute path of 'path' if it exists, otherwise return None
    def verify_path(path:str) -> Path:
        p = Path(path)
        return p.resolve() if p.exists() else None
   
    # create a template configuration file at path
    def create_cfg(path:Path) -> None:
        with open(path, 'w+') as f:
            f.write(CONFIG)
   
    # return True if cfg contains required attributes for configuration
    def verify_cfg(cfg:dict) -> bool:
        return cfg and isinstance(cfg.get('token'), str)
    
    # open file at path and return configuration as dictionary
    def load_cfg(path:Path) -> dict:
        print(f'Using {path} to configure this instance')
        with open(path) as cfg_file:
            return yaml.load(cfg_file, Loader=yaml.Loader)

    def main():
        parser = argparse.ArgumentParser()
        parser.add_argument('--cfg', '-c', help="path to config file", default ='', type=str)
        args = parser.parse_args()
    
        if args.cfg:
            path = verify_path(args.cfg)
            if not path or not path.is_file():
                print(f"Unable to locate config file: '{args.cfg}'")
                return 0
        else:
            path = verify_path(os.path.join(os.getcwd(), CFG_FILE_NAME))
            if not path:
                create_cfg(Path(os.path.join(os.getcwd(), CFG_FILE_NAME)));
                print(f"Unable to locate a config file. Template config file created at {os.path.join(os.getcwd(), CFG_FILE_NAME)}")
                return 0
        
        config = load_cfg(path)
        if not verify_cfg(config):
            print(f"Config file must contain an 'token' attribute. Please reference the template file: '{CFG_FILE_NAME}'.")
            print(f"To generate a new template file, verify '{CFG_FILE_NAME}' is not in the current directory and re-run the command without arguments.")
            return 0

        create_dbot(**config).main_loop()
    
    main()