# Configuration Options
```yaml
apps: # Dictionary of application settings
  App1: # Name of the App
    prg: '<Path>\<To>\<App1.exe>' # Required - Path to application exe or startup script
    id: '<ProcController ID>' # Optional - declare which ProcController Implementation to use
    app_info: # Optional - Dictionary of informational attributes for this app. These will be forwarded when the status command is sent for this app
      endpoint: '<IP or URL>'
      password: '<App Password>'
    opts: # Optional - Dictionary for customizing behavior of the app
      new_console: <False | True> # Starts the app in a new terminal window
      upnp: # UPnP config
        ports: # dictionary <port: protocol> where port is an int and protocol is 'tcp' | 'udp' | 'both'
          2456: 'tcp'
          2457: 'udp'
          2458-2460: 'both'
        address: <IP Address> # this is only necessary if the address is different than the socket address

  # Minimum required info to control an app
  App2: # Name of another App
    prg: '<path>\<to>\<app2.exe>'
    
default_apps: [] # Optional - list of apps by name (i.e. [App1, App2]) to start automatically when the host turns on

# Socket information Required - discord bot communication - the discord bot config should be made to match these socket settings
address: localhost # localhost can be used if the bot is running on this host, otherwise use the hosts IP
port: 8888 # Socket will be opened at address:port (localhost:8888 in this example)
```
The yaml above is an example config file.

**apps** is a dictionary, any application that is controlled needs to be added to this dictionary. This example has two applications (or servers) **App1** and **App2**.\
**prg** is the only required attribute for an app, it is a string holding the path to an executable/script to start the application.\
**id** declares the application controller type. More info on custom controllers can be found [here](dgsm/controllers/implementations)\
**app_info** is a dictionary that is intended to hold static information about the application. This info is forwarded to users who request the status of the app. In this example, the endpoint and password to the server are sent back when App1 status is requested.\
**opts** is a dictionary that holds options for changing the behavior of the application controller.\
**new_console** is a boolean, a new console window will be opened to start the application if set to True.\
**upnp** is a dictionary for defining ports to be forwarded via Universal Plug and Play\
**ports** is a dictionary defining which ports and what protocols to forward. Keys are ports: either a single integer or a range (int-int) while values are one of 'tcp, 'udp', or 'both'.\
**address** is the address to forward ports to - this is only necessary if the address is different than the socket address declared at the bottom of the config. The socket address is used by default if this is omitted.\
In this example, TCP port 2456, UDP port 2457, and both TCP and UDP ports 2458, 2459, 2460 will be forwarded. Be aware that ports already manually forwarded in router settings may not be forwarded by UPnP.\
**default_apps** is a list declaring which apps to start immediately when DGSM starts. If an app is not in this list, the start command will need to be sent to start it.\
**address** and **port** declare where DGSM will open a socket to communicate with the Bot.

# Starting DGSM
When running DGSM as a module, it will automatically check the current directory for a config file (cfg_dgsm.yaml) as well as a directory named 'controllers' for [custom controllers](dgsm/controllers/implementations). These two paths can also be specified using the -c and -o options:
```console
python -m dgsm -c "path/to/cfg_dgsm.yaml" -o "path/to/custom_controllers"
```

The following example shows how DGSM can be started from a separate python script. Configuration can be stored as a dictionary and passed to the **DGSM_Coordinator**. Custom controllers can be added using the **update_controllers_from_path** function. **DGSM_Coordinator.start()** blocks until DGSM is stopped.
```python
from dgsm import DGSM_Coordinator
from dgsm.controllers import update_controllers_from_path

# config for DGSM as a dict
CONFIG = {
  'apps': {
    'MyMinecraftWorld': {
      'prg': "D:\minecraft\start_minecraft.bat"
    }
  },
  'address': 'localhost',
  'port': 8888
}

# this makes DGSM aware of all concrete implementations of ProcController at the specified path
update_controllers_from_path("path/to/custom_controllers")

DGSM_Coordinator(**CONFIG).start()

```

# Console Interface

The console interface mimics the Discord interface:
```console
start App1
stop App1
status App1
help App1
```
These commands will, respectively, start, stop, return status info, and return all available commands for App1

**help** without any arguments will return available commands for the DGSM console
```console
help
```

The console also allows "focussing" a specific application, which directs all console input to the app and all app output to the console. '--' is used to escape this mode:\
![focus](https://user-images.githubusercontent.com/35941942/205474546-9ce67bf0-7c1e-494e-badc-b3687904f676.png)

Now all input is directed to MyMinecraftWorld. Both **seed** and **status** are fed directly to MyMinecraftWorld and the Minecraft servers output is printed directly to the console:\
![focus_input](https://user-images.githubusercontent.com/35941942/205474550-d4272da6-79a9-41a9-818a-680e7d5199bf.png)

**--unfocus** is used to leave this mode:\
![unfocus](https://user-images.githubusercontent.com/35941942/205474553-defc27bf-f873-40cc-a374-a358eca2a2a9.png)
