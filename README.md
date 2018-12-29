# Bang & Olufsen Home Assistant component

## Install

Put `bangolufsen.py` in /config/components/media_player/ and set up the devices in the configuration as 
``` 
media_player:
  platform: bangolufsen
  host: 192.168.1.10
  username: admin
  password: admin
  devices:
    - device_name1
    - device_name2
 ```
