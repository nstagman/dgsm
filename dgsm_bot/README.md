# Configuration Options
```yaml
token: <private-discord-bot-token>  #Required - discord bot token
prefix: $  #Optional - message command prefix character
mac: <MAC Address of DGSMHost>  #Optional - If DGSM is on a separate host, allows this bot to wake-on-lan the DGSM Host
address: localhost
port: 8888  #Socket will be opened at address:port (localhost:8888 in this example)
```

**token** is a Discord Bot token. [This guide](https://discordpy.readthedocs.io/en/stable/discord.html) walks through the steps of creating a Bot and getting a token. The token is copied in step 7 of the guide.\
**prefix** is the character that will preceed a message-based command in Discord\
**mac** is the MAC address of the host running DGSM. This enables the Bot to [Wake-on-LAN](https://en.wikipedia.org/wiki/Wake-on-LAN) the DGSM host. This option only works if the Bot is running on a different machine than DGSM. **wake** and **sleep** commands are added to the Bot to turn on and off the DGSM host if **mac** is supplied.\
**address** and **port** declare where DGSM will open a socket to communicate with DGSM. These two values should match the DGSM config.