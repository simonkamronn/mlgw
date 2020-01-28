# Bang & Olufsen Home Assistant component

## Install

Put `bangolufsen` directory in `/config/custom_components/` and set up the devices in the configuration as 
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

## Configure Masterlink Gateway

Add the B&O devices to the gateway and assign the MLN numbers to the devices in the same order as the devices in the HA configuration
