#include "selfdrive/ui/flutter_bridge.h"
#include "selfdrive/ui/device.h"

#include <flutter_linux/flutter_linux.h>
#include <iostream>
#include <chrono>
#include <thread>

static FlMethodChannel* channel = nullptr;

static void method_call_handler(FlMethodChannel* channel, FlMethodCall* method_call, gpointer user_data) {
  const gchar* method = fl_method_call_get_name(method_call);
  if (strcmp(method, "setMetric") == 0) {
    FlValue* args = fl_method_call_get_args(method_call);
    bool is_metric = fl_value_get_bool(args);
    // TODO: Save the value
    std::cout << "is_metric: " << is_metric << std::endl;
  } else if (strcmp(method, "setAwake") == 0) {
    FlValue* args = fl_method_call_get_args(method_call);
    bool awake = fl_value_get_bool(args);
    device()->setAwake(awake);
  }
}

#include <vector>

void flutter_bridge_send_camera_frame(const uint8_t* data, int width, int height) {
  if (channel != nullptr) {
    g_autoptr(FlValue) camera_frame = fl_value_new_uint8_list(data, width * height * 3 / 2);
    fl_method_channel_invoke_method(channel, "updateCameraFrame", camera_frame, nullptr, nullptr, nullptr);
  }
}

static void send_data() {
  while (true) {
    std::this_thread::sleep_for(std::chrono::seconds(1));
    g_autoptr(FlValue) args = fl_value_new_string("Device Info: ...
");
    fl_method_channel_invoke_method(channel, "updateDeviceInfo", args, nullptr, nullptr, nullptr);

    args = fl_value_new_string("Car Info: ...
");
    fl_method_channel_invoke_method(channel, "updateCarInfo", args, nullptr, nullptr, nullptr);
  }
}

void flutter_bridge_init() {
  device(); // Initialize device
  g_autoptr(FlDartProject) project = fl_dart_project_new();
  g_autoptr(FlView) view = fl_view_new(project);
  gtk_widget_show(GTK_WIDGET(view));

  g_autoptr(FlEngine) engine = fl_view_get_engine(view);
  g_autoptr(FlStandardMethodCodec) codec = fl_standard_method_codec_new();
  channel = fl_method_channel_new(fl_engine_get_binary_messenger(engine), "agnos_flutter", FL_METHOD_CODEC(codec));
  fl_method_channel_set_method_call_handler(channel, method_call_handler, nullptr, nullptr);

  std::thread(send_data).detach();
}
