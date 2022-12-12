# Discord Game Server Manager (DGSM)
Start, stop, and interact with game server instances through Discord. No programming is necessary for basic functionality. Point DGSM at server executables and supply a private Discord bot token for the Bot to get started.

## Getting Started
DGSM and its Bot are ran as two separate python processes. The Bot is intended to be ran on a different host than the game servers, such as a raspberry pi. This enables the Bot to power on and off the game server host, but is not required. It's possible to run the Bot and DGSM on the same machine, which is shown in the following simplified example.

Install DGSM:
```console
python -m pip install git+https://github.com/nstagman/dgsm.git#subdirectory=dgsm
```
Install the Bot:
```console
python -m pip install git+https://github.com/nstagman/dgsm.git#subdirectory=dgsm_bot
```

A private Discord Bot token is required to run the dgsm_bot. This [short guide](https://discordpy.readthedocs.io/en/stable/discord.html) walks through the steps to create one. The token will be the code that is copied in step 7.

**Note:** in step 6, the guide suggests enabling 'Public Bot'. This should be disabled so you retain complete control over what servers the Bot is added to. The 'Message Content Intent' should also be enabled in this step.

When inviting the Bot to a server, 'Send Messages', 'Manage Messages', 'Read Message History', and 'Use Slash Commands' are the only permissions required.

After following the guide, the bot should now be offline but visible in the server it was invited to

## A Simple Example
Running the dgsm package for the first time will generate a template yaml file to be filled out for configuration
```console
python -m dgsm
```

#### **simple dgsm configuration example:**
```yaml
apps:
  MyMinecraftWorld:
    prg: 'D:\minecraft\start_minecraft.bat'
address: localhost
port: 8888
```
This example config has one server named **MyMinecraftWorld** and its startup file is located at **D:\minecraft\start_minecraft.bat**. A socket will be opened at **localhost:8888** to communicate with the Bot.

For more details on other configuration options, such as enabling UPnP for a server or declaring a custom server controller with specific server interactions, click [here](dgsm#configuration-options).

\
After the config file has been populated, running the dgsm package again will start start the game server manager with the configuration
```console
python -m dgsm
```
**MyMinecraftWorld** can now be started and stopped through the console interface:
```console
start MyMinecraftWorld
stop MyMinecraftWorld
status MyMinecraftWorld
```
More details on using the console interface can be found [here](dgsm#console-interface)

\
The dgms_bot package supplies the Discord integration. Similarly, running the dgsm_bot package for the first time will generate a template yaml file to configure the Bot
```console
python -m dgsm_bot
```

#### **bot configuration example:**
```yaml
token: '<long-private-discord-bot-token>'
prefix: $
address: localhost
port: 8888
```
**token** is the code that was attained when creating a Discord Bot in the previous section

A socket will be opened at **localhost:8888** to communicate with DGSM (**address** and **port** should be the same in both config files). **$** is the prefix for message-based Discord commands (Slash Commands are the preffered method of interaction and are automatically supported).

For more details on the Bot configuration options click [here](dgsm_bot)

Running the dgsm_bot package with the token will start the Bot
```console
python -m dgsm_bot
```
The Bot should now appear online in the Discord Server

Bring up commands by pressing '/':

![slash_cmds](https://user-images.githubusercontent.com/35941942/205474325-50a615d2-7c36-4d22-a850-4b896fa737e5.png)

After a command is selected, any possible arguments will be suggested by the Bot:

![auto_complete](https://user-images.githubusercontent.com/35941942/205474334-124dbb51-beac-4c6a-b013-8deb60d78cbc.png)

Selecting MyMinecraftWorld and pressing 'Enter' will start the MyMinecraftWorld server.

## Customised App Controllers
The above example uses default configuration for controlling the server instance. **id** can be added to the config file to let DGSM know the type of server that will be running.

```yaml
apps:
  MyMinecraftWorld:
    prg: 'D:\minecraft\start_minecraft.bat'
    id: 'minecraft'
    app_info:
      endpoint: '192.168.1.10' # in reality this would be the public IP of the game server (noip, duckdns, etc.)
      password: 'open_sesame'
address: localhost
port: 8888
```
If an implementation exists for the declared **id**, DGSM will use that implementation control the server instance. DGSM has handles to the server input and output which allows it to directly interact with the server as well as monitor the servers state. For example, the following regular expressions are used to monitor and collect server state:
```python
VERSION    = re.compile(r'(?:Starting minecraft server version )([\w.]+)', re.IGNORECASE)
ONLINE     = re.compile(r'(Done \([\w.]+s\)!)', re.IGNORECASE)
CONNECT    = re.compile(r'([\w]+)(?: joined the game)', re.IGNORECASE)
DISCONNECT = re.compile(r'([\w]+)(?: left the game)', re.IGNORECASE)
```
The minecraft server output is checked against these regular expressions which determine the version of the server, exactly when the server is fully started, and when a player connects or disconnects. Now DGSM has more knowledge about the server:

![status_cmd](https://user-images.githubusercontent.com/35941942/205474342-c543a4de-b127-44c0-91f5-50edff663d16.png)

![status_response](https://user-images.githubusercontent.com/35941942/205474347-dc7b7d0a-d126-45fa-8d2a-beba55174d82.png)

More details on creating custom commands and interactions can be found [here](dgsm/dgsm/controllers/implementations)
