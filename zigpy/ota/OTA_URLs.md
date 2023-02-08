# Zigbee OTA source provider sources for these and others

Collection of external Zigbee OTA firmware images from official and unofficial OTA provider sources.

### Inovelli OTA Firmware provider

Manufacturer ID = 4655

Inovelli Zigbee OTA firmware images for zigpy are made publicly available by Inovelli (first-party) at the following URLs:

https://files.inovelli.com/firmware/firmware-zha.json

https://files.inovelli.com/firmware

### Sonoff OTA Firmware provider

Manufacturer ID = 4742

Sonoff Zigbee OTA firmware images are made publicly available by Sonoff (first-party) at the following URLs:

https://zigbee-ota.sonoff.tech/releases/upgrade.json

### Koenkk zigbee-OTA repository

Koenkk zigbee-OTA repository host third-party OTA firmware images and external URLs for many third-party Zigbee OTA firmware images.

https://github.com/Koenkk/zigbee-OTA/tree/master/images

https://raw.githubusercontent.com/Koenkk/zigbee-OTA/master/index.json

### Dresden Elektronik

Manufacturer ID = 4405

Dresden Elektronik Zigbee OTA firmware images are made publicly available by Dresden Elektronik (first-party) at the following URLs:

https://deconz.dresden-elektronik.de/otau/

Dresden Elektronik also provide third-party OTA firmware images and external URLs for many third-party Zigbee OTA firmware images here:

https://github.com/dresden-elektronik/deconz-rest-plugin/wiki/OTA-Image-Types---Firmware-versions

Dresden Elektronik themselvers implement updates of third-party Zigbee firmware images via their deCONZ STD OTAU plugin:

https://github.com/dresden-elektronik/deconz-ota-plugin

### EUROTRONICS

EUROTRONICS Zigbee OTA firmware images are made publicly available by EUROTRONIC Technology (first-party) at the following URL:

https://github.com/EUROTRONIC-Technology/Spirit-ZigBee/releases/download/

### IKEA Trådfri

Manufacturer ID = 4476

IKEA Tradfi Zigbee OTA firmware images are made publicly available by IKEA (first-party) at the following URL:

Download-URL: 

http://fw.ota.homesmart.ikea.net/feed/version_info.json

Release changelogs

https://ww8.ikea.com/ikeahomesmart/releasenotes/releasenotes.html

### LEDVANCE/Sylvania and OSRAM Lightify

Manufacturer ID = 4364

LEDVANCE/Sylvania and OSRAM Lightify Zigbee OTA firmware images are made publicly available by LEDVANCE (first-party) at the following URL:

https://update.ledvance.com/firmware-overview

https://api.update.ledvance.com/v1/zigbee/firmwares/download

https://consumer.sylvania.com/our-products/smart/sylvania-smart-zigbee-products-menu/index.jsp

### Legrand/Netatmo

Manufacturer ID = 4129

Legrand/Netatmo Zigbee OTA firmware images are made publicly available by Legrand (first-party) at the following URL:

https://developer.legrand.com/documentation/operating-manual/ https://developer.legrand.com/documentation/firmwares-download/

### LiXee

LiXee Zigbee OTA firmware images are made publicly available by Fairecasoimeme / ZiGate (first-party) at the following URL:

https://github.com/fairecasoimeme/Zlinky_TIC/releases

### SALUS/Computime

Manufacturer ID = 4216

SALUS/Computime Zigbee OTA firmware images are made publicly available by SALUS (first-party) at the following URL:

https://eu.salusconnect.io/demo/default/status/firmware

### Sengled

Manufacturer ID = 4448

Sengled Zigbee OTA firmware images are made publicly available by Sengled  (first-party) at the following URLs but does now seem to allow listing:

http://us-fm.cloud.sengled.com:8000/sengled/zigbee/firmware/

Note that Sengled do not seem to provide their firmware for use with other ZigBee gateways than the Sengled Smart Hub. The communication between their hub/gateway/bridge appliance and the server hosting the firmware files is encrypted, so we cannot directly get listing of all the files available. To find the URL for firmware files, you need to sniff the traffic from the Hue bridge to the Internet, as it downloads the files, (since the bridge will only download firmware files for connected devices with outdated firmware sniffing traffic is not repeatable once the device has been updated).

The official URLs for Philips Hue (Signify) Zigbee OTA firmware images are therefore documented by community and third-parties such as Koenkk and Dresden Elektronik:

https://raw.githubusercontent.com/Koenkk/zigbee-OTA/master/index.json

https://github.com/dresden-elektronik/deconz-rest-plugin/wiki/OTA-Image-Types---Firmware-versions#sengled

### Philips Hue (Signify)

Manufacturer ID = 4107

Philips Hue OTA firmware images are available for different Hue devices for several official sources that do not all use the same APIs:

https://firmware.meethue.com/v1/checkUpdate

https://firmware.meethue.com/storage/

http://fds.dc1.philips.com/firmware/

Philips Hue (Signify) Zigbee OTA firmware images direct URLs are available by Koenkk zigbee-OTA repository (third-party) at following URL:

https://raw.githubusercontent.com/Koenkk/zigbee-OTA/master/index.json

Note that Philips/Signify do not provide their firmware for use with other ZigBee gateways than the Philips Hue bridge. The communication between their hub/gateway/bridge appliance and the server hosting the firmware files is encrypted, so we cannot directly get listing of all the files available. To find the URL for firmware files, you need to sniff the traffic from the Hue bridge to the Internet, as it downloads the files, (since the bridge will only download firmware files for connected devices with outdated firmware sniffing traffic is not repeatable once the device has been updated).

The official URLs for Philips Hue (Signify) Zigbee OTA firmware images are therefore documented by community and third-parties such as Koenkk and Dresden Elektronik:

https://raw.githubusercontent.com/Koenkk/zigbee-OTA/master/index.json

https://github.com/dresden-elektronik/deconz-rest-plugin/wiki/OTA-Image-Types---Firmware-versions#philips-hue

https://github.com/dresden-elektronik/deconz-ota-plugin/blob/master/README.md#hue-firmware

### Lutron

Manufacturer ID = 4420

Lutron Zigbee OTA firmware images for Lutron Aurora Smart Dimmer Z3-1BRL-WH-L0 is made publicly available by Philips (first-party as ODM) at the following URL:

http://fds.dc1.philips.com/firmware/ZGB_1144_0000/3040/Superman_v3_04_Release_3040.ota

### Ubisys

Manufacturer ID = 4338

Ubisys Zigbee OTA firmware images are made publicly available by Ubisys (first-party) at the following URLs:

https://www.ubisys.de/en/support/firmware/

https://www.ubisys.de/wp-content/uploads/

### Third Reality (3reality)

Manufacturer IDs = 4659, 4877

ThirdReality (3reality) Zigbee OTA firmware images are made publicly available by Third Reality, Inc. (first-party) at the following URL:

https://tr-zha.s3.amazonaws.com/firmware.json

### Danfoss

Manufacturer ID = 4678

Danfoss Zigbee OTA firmware images for Danfoss Ally devices are made publicly available by Danfoss (first-party) at the following URL:

https://files.danfoss.com/download/Heating/Ally/Danfoss%20Ally

More information about updateting Danfoss Ally smart heating products available at:

https://www.danfoss.com/en/products/dhs/smart-heating/smart-heating/danfoss-ally/danfoss-ally-support/#tab-approvals

### Busch-Jaeger

Manufacturer ID = 4398

The ZLL switches from Busch-Jaeger does have upgradable firmware but unfortunately they do not publish the OTOU image files directly via an public OTA provider server. However the firmware can be download and extracted from an Windows Upgrade Tool provided by Busch-Jaeger with the following steps:
 - Download the Upgrade Tool from https://www.busch-jaeger.de/bje/software/Zigbee_Software/BJE_ZLL_Update_Tool_Setup_V1_2_0_Windows_Version.exe
 - Extract the contents of the *.exe file with 7zip (7z x BJE_ZLL_Update_Tool_Setup_V1_2_0_Windows_Version.exe).
 - Navigate to the device/ folder and get the firmware images.
