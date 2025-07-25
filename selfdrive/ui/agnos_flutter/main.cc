#include "my_application.h"
#include "selfdrive/ui/flutter_bridge.h"

int main(int argc, char** argv) {
  flutter_bridge_init();
  g_autoptr(MyApplication) app = my_application_new();
  return g_application_run(G_APPLICATION(app), argc, argv);
}
