#include "selfdrive/ui/device.h"
#include "system/hardware/hw.h"

Device::Device(QObject *parent) : QObject(parent) {
  setAwake(true);
}

void Device::setAwake(bool on) {
  if (on != awake) {
    awake = on;
    Hardware::set_display_power(awake);
  }
}

Device *device() {
  static Device _device;
  return &_device;
}
