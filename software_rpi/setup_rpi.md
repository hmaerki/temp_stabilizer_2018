# Installing Raspberry Pi

## Prepare SDCARD (or USB Stick)

Download
https://downloads.raspberrypi.org/raspbian/images/raspbian-2018-11-15/2018-11-13-raspbian-stretch.zip

Write it to a sdcard using rufus.

## Optional: Boot from USB

https://www.raspberrypi.org/documentation/hardware/raspberrypi/bootmodes/msd.md

echo program_usb_boot_mode=1 | sudo tee -a /boot/config.txt

## After first Boot
Location: United States, American English, Timezone Adak
Check: Use US Keyboard
User pi / raspberry
Set new password: xxx

sudo raspi-config
  4 -> I2, change Timezone: Europe/Zurich
  5 -> P2, SSH: Enable

reboot

-> you may use ssh now

git config --global user.email "hans@maerki.com"
git config --global user.name "Hans Maerki"
git clone  --depth 1 https://github.com/hmaerki/temp_stabilizer_2018.git

sudo bash -x ~pi/temp_stabilizer_2018/software_rpi/install_packages.sh


# Configuration Accespoint
# https://www.raspberrypi.org/documentation/configuration/wireless/access-point.md