#pragma once

#include <QObject>

class Device : public QObject {
  Q_OBJECT

public:
  Device(QObject *parent = 0);
  void setAwake(bool on);

private:
  bool awake = false;
};

Device *device();
