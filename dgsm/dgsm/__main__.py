import argparse
from pathlib import Path
import os
import yaml
from dgsm.dgsm import DGSM_Coordinator
from dgsm.controllers import update_controllers_from_path


CFG_FILE_NAME = 'cfg_dgsm.yaml'
CONFIG = '''
apps: # Dictionary of application settings
  <AppName1>: # Name of the App
    prg: '<Path>\<To>\<App1.exe>' # Required - Path to application exe or startup script
    id: '<ProcController ID>' # Optional - declare which ProcController Implementation to use
    app_info: # Optional - Dictionary of informational attributes for this app. These will be forwarded to users who request app status info
      endpoint: '<IP or URL>' # will be passed to users who request app info
      password: '<App Password>' # will be passed to users who request app info
    opts: # Optional - Dictionary for customizing behavior of the app
      new_console: <False | True> # Starts the app in a new terminal window
      upnp: # UPnP config
        ports: # dictionary <port: protocol> where port is an int and protocol is 'tcp' | 'udp' | 'both'
          2456: 'both'
          2457: 'both'
          2458: 'both'
        address: <IP Address> # this is only necessary if the address is different than the socket address
  <AppName2>: # Name of another App
    prg: '<path>\<to>\<app2.exe>'
    # id wasn't supplied - App2 will use the Default ProcController Implementation
default_apps: [] # Optional - list of apps by name (i.e. [AppName1, AppName2]) to start automatically when the host turns on
# Socket information Required - discord bot communication - the discord bot config should be made to match these socket settings
address: localhost # localhost can be used if the bot is running on this host, otherwise use this hosts IP
port: 8888 # Socket will be opened at address:port (localhost:8888 in this example)
'''
CONTROLLER_PATHS = ['controllers', 'implementations']


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
        return cfg and isinstance(cfg.get('apps'), dict)

    # open file at path and return configuration as dictionary
    def load_cfg(path:Path) -> dict:
        print(f'Using {path} to configure this instance')
        with open(path) as cfg_file:
            return yaml.load(cfg_file, Loader=yaml.Loader)

    def main():
        parser = argparse.ArgumentParser()
        parser.add_argument('--cfg', '-c', help="path to config file", default ='', type=str)
        parser.add_argument('--con', '-o', help="path to custom ProcController implementations", default='', type=str)
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
            print(f"Config file must contain an 'apps' dictionary. Please reference the template file: '{CFG_FILE_NAME}'.")
            print(f"To generate a new template file, verify '{CFG_FILE_NAME}' is not in the current directory and re-run the command without arguments.")
            return 0
       
        if args.con:
            if path := verify_path(args.con):
                print(f"Including Controllers from {path}")
                update_controllers_from_path(path)
            else:
                print(f"Unable to locate '{args.con}'. No custom controllers will be added.")
        else:
            for p in CONTROLLER_PATHS:
                if (path := verify_path(p)) and path.is_dir():
                    print(f"Including Controllers from {path}")
                    update_controllers_from_path(path)
        
        DGSM_Coordinator(**config).start()

    main()

