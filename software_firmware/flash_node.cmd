@rem pip install esptool

set PORT=COM39

python -m esptool --chip esp32 --port %PORT% --baud 460800 erase_flash

@echo Next step: Flashing the firmware
@pause

python -m esptool --chip esp32 --port %PORT% --baud 460800 write_flash -z --flash_mode dio --flash_freq 40m 0x1000 micropython\ports\esp32\build\firmware.bin

@pause
