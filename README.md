# Websocket_test environment

# install dependendencies
- requires python 3
- `pip install -r requirements.txt`
 
# Configuration
rename `local_settings.template.py` to `local_settings.py`
adjust log level in `ws_client.py`

check `local_settings.py` urls are identical to configuration in `login_server.py` and `ws_server.py` 

# Run
## Use `ws_server.py` as WS server
`python ws_server.py`

## `http_server.py` for login and REST API
`python http_server.py`
 
## `ws_client.py` as WS client
`python ws_client.py`


## Client Behaviour
1. client gets AK and AKID from login server
2. establishes WS server


## HTTP server
- provides login and gateway status API
- gateway status API randomly returns connection/not connected flag

## WS behaviour
- emit device state change messages
- emit a capability push every fourth messages
- can close all sockets via telnet `echo "close" | curl telnet://localhost:8000` --> triggers re-login

## Screenshot
![Screenshot](https://raw.githubusercontent.com/dschien/secure-ws/master/screen.png)
