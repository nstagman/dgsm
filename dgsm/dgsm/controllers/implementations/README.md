# Customizing Controllers
Custom interactions with game servers can be created by implementing the AppController interface. The abstract class method, ID, must be implemented. This method simply returns a string indicating the application type.

## Server Output Monitoring
Below is the implementation used for monitoring output of a minecraft server. 

```python
import re
from dgsm.controllers import AppController, cmd, stdout_handler


class MineCraftController(AppController):
    VERSION    = re.compile(r'(?:Starting minecraft server version )([\w.]+)', re.IGNORECASE)
    ONLINE     = re.compile(r'(Done \([\w.]+s\)!)', re.IGNORECASE)
    CONNECT    = re.compile(r'([\w]+)(?: joined the game)', re.IGNORECASE)
    DISCONNECT = re.compile(r'([\w]+)(?: left the game)', re.IGNORECASE)
    def __init__(self, name:str, **kwargs) -> None:
        super().__init__(name, **kwargs)

    @classmethod
    def ID(cls) -> str: return 'minecraft'

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
```

The implementation above has defined four regex patterns and then decorated methods with each of the patterns using the **stdout_hander** decorator. If a pattern matches the server output, then the decorated method will be called with the match object as the only argument. This server output matching will continue as long as the server is running.

For example: if the server outputs 'Nick joined the game' then the **_hande_connect** method will be called because the pattern **CONNECT** matches the output. The implementation above uses the default behavior defined in the AppController class which simply adds the name 'Nick' to the list of current players.

```python
# AppController definition
def _handle_connect(self, match:re.Match) -> None:
    self._app_attrs['players'].append(match.group(1))
```

 It is also expected that AppController implementations set the future **_start_comp** to True when the server has completely started. This can be done by calling **super()._handle_online()** once startup has been detected, this is done in the **_handle_online** method above.

## Custom Commands
Adding a command is done by simply decorating a method with the **cmd** decorator. The command will automatically be available to users by the name given to the decorator argument. The following shows adding an 'echo' command to the MineCraftController:

```python
@cmd('echo')
async def _echo(self, *args) -> None:
    """
    Echo a message back to the user
    """
    if args: await self.message_coordinator(' '.join(arg for arg in args))
    else: await self.message_coordinator('nothing but silence')
```

All custom commands are automatically accessible as an extended command (/ext). The example above is all that is required to make 'echo' available to 'minecraft' apps:

echo is now an available command:\
![select_echo](https://user-images.githubusercontent.com/35941942/205474483-264caa03-cd6e-493d-a36d-bf305d92b8f5.png)

entering 'echo this' as an argument:\
![echo_cmd](https://user-images.githubusercontent.com/35941942/205474486-252c4c89-db3e-4c36-9905-bf5d44f154f5.png)

'echo this' is echoed back:\
![echo_response](https://user-images.githubusercontent.com/35941942/205474492-364b375c-dcd8-4ca8-bed9-6a8557947222.png)

The docstring of a command method is automatically returned as-is when a user requests the help message for an app:\
![help_response](https://user-images.githubusercontent.com/35941942/205474495-7afff4b2-2e28-4eed-9bd8-502c2a4a948d.png)

### Interacting With a Server Instance
A custom command will most likely need to interact with a server instance. This would require sending input to the server, then possibly waiting for its response. The following shows a simple interaction with a minecraft server using the custom command 'seed':

```python
@cmd('seed')
async def _seed(self, *args) -> None:
    """
    Returns the seed of the server
    """
    waiter = self.output_waiter(pattern=re.compile(r'(?:Seed: \[)(-?\d+)(?:\])', re.IGNORECASE))
    if not waiter: return
    await self.message_app('seed')
    match = await waiter()
    await self.message_coordinator(f'{self.name} Seed: {match.group(1)}')
```

**output_waiter** is an overloaded method that creates a server output monitoring worker and returns an awaitable to wait for the desired output. In this case, a regex pattern is specified, so the **waiter** coroutine will return a match object if a pattern match is found. **message_app** is used to send 'seed' to the minecraft server. **waiter** will return a match object when a match is found, or None if a timeout occurs. The formatted message with the seed value is then sent back to the interface that originated the command using **message_coordinator**

seed command usage:\
![seed_cmd](https://user-images.githubusercontent.com/35941942/205474500-083c6593-c953-4e31-86c0-56ccc94b04de.png)

seed command response:\
![seed_cmd_response](https://user-images.githubusercontent.com/35941942/205474501-2eff93e7-70b4-44c6-9bc2-bc370f21fded.png)

```python
@cmd('input')
async def _input(self, *args) -> None:
    """
    Sends input directly to the app
    """
    if not args: return
    waiter = self.output_waiter(wait_time=1.0)
    if not waiter: return
    await self.message_app(' '.join(arg for arg in args))
    output = await waiter()
    await self.message_coordinator(output)
```

This command is very similar to seed except it sends user supplied arguments to the server. This time **output_waiter** is given a float, not a regex pattern. **waiter** will aggregate all server output for 1.0 seconds after it is awaited, then return the all received output as a string. This effectively creates a generic interface with the server instance without having to know what the output will look like ahead of time .

input 'seed' to MyMinecraftWorld:\
![input_seed](https://user-images.githubusercontent.com/35941942/205474507-a13eed69-6622-4129-b055-beba1130ea62.png)

'seed' response:\
![input_response_seed](https://user-images.githubusercontent.com/35941942/205474512-22088648-a0e4-4515-9dd5-3f95f5fea936.png)

input 'ban' to MyMinecraftWorld:\
![input_ban](https://user-images.githubusercontent.com/35941942/205474515-08b3bb8a-3653-4ab5-8bd7-ec9e78513a20.png)

'ban' response:\
![input_response_ban](https://user-images.githubusercontent.com/35941942/205474516-65f5a9a7-f713-43fd-b548-d6d3ecf5be5b.png)

Output Waiters:
```python
@overload
def output_waiter(self, output_count:int, return_partial=True, timeout:float=3.0) -> Coroutine[Any, Any, str]:
    # Aggregate output until server responds 'output_count' number of times. If return_partial is True, then return current aggregated output even if timeout occurs

@overload
def output_waiter(self, wait_time:float) -> Coroutine[Any, Any, str]:
    # Aggregate all output for wait_time seconds then return

@overload
def output_waiter(self, sub_string:str, aggregate=False, return_partial=False, timeout:float=3.0) -> Coroutine[Any, Any, str]:
    # Wait until sub_string is found in output. If aggregate is True, then aggregate all output until sub_string is found, otherwise only return the response containing sub_string

@overload
def output_waiter(self, pattern:re.Pattern, timeout:float=3.0) -> Coroutine[Any, Any, re.Match]:
    # Wait until pattern is found then return match object.
```
