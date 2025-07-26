#pragma once

#include <flutter_linux/flutter_linux.h>

void flutter_bridge_init();
void flutter_bridge_send_camera_frame(const uint8_t* data, int width, int height);
