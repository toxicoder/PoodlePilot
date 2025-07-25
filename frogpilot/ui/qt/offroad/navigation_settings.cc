#include "frogpilot/ui/qt/offroad/navigation_settings.h"

void FrogPilotNavigationPanel::createMapboxKeyControl(ButtonControl *&control, const QString &label, const std::string &paramKey, const QString &prefix, FrogPilotListWidget *list) {
  control = new ButtonControl(label, "", tr("Manage your %1.").arg(label));
  QObject::connect(control, &ButtonControl::clicked, [=] {
    if (control->text() == tr("ADD")) {
      QString key = InputDialog::getText(tr("Enter your %1").arg(label), this).trimmed();

      if (!key.startsWith(prefix)) {
        key = prefix + key;
      }
      if (key.length() >= 80) {
        params.put(paramKey, key.toStdString());
      } else {
        ConfirmationDialog::alert(tr("Inputted key is invalid or too short!"), this);
      }
    } else {
      if (FrogPilotConfirmationDialog::yesorno(tr("Are you sure you want to remove your %1?").arg(label), this)) {
        control->setText(tr("ADD"));

        params.put(paramKey, "0");
        params.put(paramKey, "0");

        setupCompleted = false;
      }
    }
  });
  control->setText(QString::fromStdString(params.get(paramKey)).startsWith(prefix) ? tr("REMOVE") : tr("ADD"));
  list->addItem(control);
}

FrogPilotNavigationPanel::FrogPilotNavigationPanel(FrogPilotSettingsWindow *parent) : FrogPilotListWidget(parent), parent(parent) {
  primelessLayout = new QStackedLayout();
  addItem(primelessLayout);

  FrogPilotListWidget *settingsList = new FrogPilotListWidget(this);
  ipLabel = new LabelControl(tr("Manage Your Settings At"), tr("Device Offline"));
  settingsList->addItem(ipLabel);

  std::vector<QString> searchOptions{tr("MapBox"), tr("Amap"), tr("Google")};
  FrogPilotButtonsControl *searchInput = new FrogPilotButtonsControl(tr("Destination Search Provider"),
                                         tr("The search provider used for destination queries in \"Navigate on Openpilot\". "
                                         "Options include \"MapBox\" (recommended), \"Amap\", and \"Google Maps\"."),
                                         "", searchOptions, true);

  QObject::connect(searchInput, &FrogPilotButtonsControl::buttonClicked, [this](int id) {
    amapKeyControl1->setVisible(id == 1);
    amapKeyControl2->setVisible(id == 1);

    googleKeyControl->setVisible(id == 2);

    params.putInt("SearchInput", id);

    update();
  });
  searchInput->setCheckedButton(params.getInt("SearchInput"));
  settingsList->addItem(searchInput);

  amapKeyControl1 = new ButtonControl(tr("Amap Key #1"), "", tr("Manage your Amap key."));
  QObject::connect(amapKeyControl1, &ButtonControl::clicked, [=] {
    if (amapKeyControl1->text() == tr("ADD")) {
      QString key = InputDialog::getText(tr("Enter your Amap key"), this).trimmed();

      if (key.length() >= 39) {
        params.put("AMapKey1", key.toStdString());
      } else {
        ConfirmationDialog::alert(tr("Inputted key is invalid or too short!"), this);
      }
    } else {
      if (FrogPilotConfirmationDialog::yesorno(tr("Are you sure you want to remove your Amap key?"), this)) {
        amapKeyControl1->setText(tr("ADD"));

        params.put("AMapKey1", "0");
        params.put("AMapKey1", "0");
      }
    }
  });
  amapKeyControl1->setText(params.get("AMapKey1").empty() ? tr("ADD") : tr("REMOVE"));
  settingsList->addItem(amapKeyControl1);

  amapKeyControl2 = new ButtonControl(tr("Amap Key #2"), "", tr("Manage your Amap key."));
  QObject::connect(amapKeyControl2, &ButtonControl::clicked, [=] {
    if (amapKeyControl2->text() == tr("ADD")) {
      QString key = InputDialog::getText(tr("Enter your Amap key"), this).trimmed();

      if (key.length() >= 39) {
        params.put("AMapKey2", key.toStdString());
      } else {
        ConfirmationDialog::alert(tr("Inputted key is invalid or too short!"), this);
      }
    } else {
      if (FrogPilotConfirmationDialog::yesorno(tr("Are you sure you want to remove your Amap key?"), this)) {
        amapKeyControl2->setText(tr("ADD"));

        params.put("AMapKey2", "0");
        params.put("AMapKey2", "0");
      }
    }
  });
  amapKeyControl2->setText(params.get("AMapKey2").empty() ? tr("ADD") : tr("REMOVE"));
  settingsList->addItem(amapKeyControl2);

  googleKeyControl = new ButtonControl(tr("Google Maps Key"), "", tr("Manage your Google Maps key."));
  QObject::connect(googleKeyControl, &ButtonControl::clicked, [=] {
    if (googleKeyControl->text() == tr("ADD")) {
      QString key = InputDialog::getText(tr("Enter your Google Maps key"), this).trimmed();

      if (key.length() >= 25) {
        params.put("GMapKey", key.toStdString());
      } else {
        ConfirmationDialog::alert(tr("Inputted key is invalid or too short!"), this);
      }
    } else {
      if (FrogPilotConfirmationDialog::yesorno(tr("Are you sure you want to remove your Google Maps key?"), this)) {
        googleKeyControl->setText(tr("ADD"));

        params.put("GMapKey", "0");
        params.put("GMapKey", "0");
      }
    }
  });
  googleKeyControl->setText(params.get("GMapKey").empty() ? tr("ADD") : tr("REMOVE"));
  settingsList->addItem(googleKeyControl);

  createMapboxKeyControl(publicMapboxKeyControl, tr("Public Mapbox Key"), "MapboxPublicKey", "pk.", settingsList);
  createMapboxKeyControl(secretMapboxKeyControl, tr("Secret Mapbox Key"), "MapboxSecretKey", "sk.", settingsList);

  ButtonControl *setupButton = new ButtonControl(tr("MapBox Setup Instructions"), tr("VIEW"), tr("View the instructions to set up \"MapBox\" for \"Primeless Navigation\"."), this);
  QObject::connect(setupButton, &ButtonControl::clicked, [this]() {
    openSubSubPanel();

    updateStep();

    primelessLayout->setCurrentIndex(1);
  });
  settingsList->addItem(setupButton);

  std::vector<QString> filterButtonNames{tr("CANCEL"), tr("Manually Update Speed Limits")};
  updateSpeedLimitsToggle = new FrogPilotButtonControl("SpeedLimitFiller", tr("Speed Limit Filler"),
                                                    tr("Automatically collect missing or incorrect speed limits from your dashboard (if supported), "
                                                       "<b>Mapbox</b>, and <b>Navigate-on-openpilot</b> while driving.<br><br>"
                                                       "When the car is turned off and connected to Wi-Fi, your speed limit data is automatically processed "
                                                       "into a compiled file formatted for the tool located at <b>SpeedLimitFiller.frogpilot.download</b>.<br><br>"
                                                       "You can grab the processed file from <b>The Pond</b> via the <b>Download Speed Limits</b> menu.<br><br>"
                                                       "Want a more thorough walkthrough? Check out the <b>#speed-limit-filler</b> channel in the <b>FrogPilot Discord</b>!"),
                                                       "", filterButtonNames);
  QObject::connect(updateSpeedLimitsToggle, &FrogPilotButtonControl::buttonClicked, [this](int id) {
    if (id == 0) {
      if (FrogPilotConfirmationDialog::yesorno(tr("Are you sure you want to cancel the speed limit update process?"), this)) {
        updatingLimits = false;

        updateSpeedLimitsToggle->setEnabledButton(0, false);
        updateSpeedLimitsToggle->setValue(tr("Cancelled..."));

        params_memory.remove("UpdateSpeedLimits");

        QTimer::singleShot(2500, [this]() {
          updateSpeedLimitsToggle->clearCheckedButtons(true);
          updateSpeedLimitsToggle->setEnabledButton(0, true);
          updateSpeedLimitsToggle->setValue("");
          updateSpeedLimitsToggle->setVisibleButton(0, false);
          updateSpeedLimitsToggle->setVisibleButton(1, true);

          params_memory.remove("UpdateSpeedLimitsStatus");
        });
      }
    } else if (id == 1) {
      QJsonObject overpassRequests = QJsonDocument::fromJson(QString::fromStdString(params.get("OverpassRequests")).toUtf8()).object();

      int totalRequests = overpassRequests.value("total_requests").toInt(0);
      int maxRequests = overpassRequests.value("max_requests").toInt(10000);
      int savedDay = overpassRequests.value("day").toInt(QDate::currentDate().day());

      int currentDay = QDate::currentDate().day();

      if (savedDay != currentDay) {
        totalRequests = 0;
      }

      if (totalRequests >= maxRequests) {
        QTime now = QTime::currentTime();

        int secondsUntilMidnight = (24 * 3600) - (now.hour() * 3600 + now.minute() * 60 + now.second());
        int hours = secondsUntilMidnight / 3600;
        int minutes = (secondsUntilMidnight % 3600) / 60;

        ConfirmationDialog::alert(QString(tr("You have reached the request limit.\n\nIt will reset in %1 hours and %2 minutes.")).arg(hours).arg(minutes), this);

        updateSpeedLimitsToggle->clearCheckedButtons(true);
        return;
      }

      updateSpeedLimitsToggle->setVisibleButton(0, true);
      updateSpeedLimitsToggle->setVisibleButton(1, false);

      if (FrogPilotConfirmationDialog::yesorno(tr("This process will take awhile, so it's advised to start when you're done driving with a stable Wi-Fi connection. Do you wish to proceed?"), this)) {
        updatingLimits = true;

        updateSpeedLimitsToggle->setValue("Calculating...");

        params_memory.put("UpdateSpeedLimitsStatus", "Calculating...");
        params_memory.putBool("UpdateSpeedLimits", true);
      } else {
        updateSpeedLimitsToggle->setVisibleButton(0, false);
        updateSpeedLimitsToggle->setVisibleButton(1, true);

        updateSpeedLimitsToggle->clearCheckedButtons(true);
      }
    }
  });
  updateSpeedLimitsToggle->setVisibleButton(0, false);
  settingsList->addItem(updateSpeedLimitsToggle);

  ScrollView *settingsPanel = new ScrollView(settingsList, this);
  primelessLayout->addWidget(settingsPanel);

  imageLabel = new QLabel(this);

  ScrollView *instructionsPanel = new ScrollView(imageLabel, this);
  primelessLayout->addWidget(instructionsPanel);

  QObject::connect(parent, &FrogPilotSettingsWindow::closeSubSubPanel, [this] {primelessLayout->setCurrentIndex(0);});
  QObject::connect(uiState(), &UIState::uiUpdate, this, &FrogPilotNavigationPanel::updateState);
}

void FrogPilotNavigationPanel::showEvent(QShowEvent *event) {
  FrogPilotUIState &fs = *frogpilotUIState();
  FrogPilotUIScene &frogpilot_scene = fs.frogpilot_scene;

  QString ipAddress = fs.wifi->getIp4Address();
  ipLabel->setText(ipAddress.isEmpty() ? tr("Device Offline") : QString("%1:8082").arg(ipAddress));

  updateButtons();

  setupCompleted = mapboxPublicKeySet && mapboxSecretKeySet;
  updatingLimits = !params_memory.get("UpdateSpeedLimitsStatus").empty() && QString::fromStdString(params_memory.get("UpdateSpeedLimitsStatus")) != "Completed!";

  int searchInput = params.getInt("SearchInput");

  amapKeyControl1->setVisible(searchInput == 1);
  amapKeyControl2->setVisible(searchInput == 1);

  googleKeyControl->setVisible(searchInput == 2);

  updateSpeedLimitsToggle->setEnabledButton(1, frogpilot_scene.online && util::system_time_valid());
  updateSpeedLimitsToggle->setVisible(parent->tuningLevel >= parent->frogpilotToggleLevels["SpeedLimitFiller"].toDouble());
  updateSpeedLimitsToggle->setVisibleButton(0, updatingLimits);
  updateSpeedLimitsToggle->setVisibleButton(1, !updatingLimits);

  if (updatingLimits) {
    updateSpeedLimitsToggle->setValue(QString::fromStdString(params_memory.get("UpdateSpeedLimitsStatus")));
  }
}

void FrogPilotNavigationPanel::hideEvent(QHideEvent *event) {
  primelessLayout->setCurrentIndex(0);
}

void FrogPilotNavigationPanel::mousePressEvent(QMouseEvent *event) {
  if (primelessLayout->currentIndex() == 1) {
    closeSubSubPanel();

    primelessLayout->setCurrentIndex(0);
  }
}

void FrogPilotNavigationPanel::updateButtons() {
  amapKeyControl1->setText(params.get("AMapKey1").empty() ? tr("ADD") : tr("REMOVE"));
  amapKeyControl2->setText(params.get("AMapKey2").empty() ? tr("ADD") : tr("REMOVE"));

  googleKeyControl->setText(params.get("GMapKey").empty() ? tr("ADD") : tr("REMOVE"));

  mapboxPublicKeySet = QString::fromStdString(params.get("MapboxPublicKey")).startsWith("pk");
  mapboxSecretKeySet = QString::fromStdString(params.get("MapboxSecretKey")).startsWith("sk");

  publicMapboxKeyControl->setText(mapboxPublicKeySet ? tr("REMOVE") : tr("ADD"));
  secretMapboxKeyControl->setText(mapboxSecretKeySet ? tr("REMOVE") : tr("ADD"));
}

void FrogPilotNavigationPanel::updateState(const UIState &s, const FrogPilotUIState &fs) {
  if (!isVisible() || s.sm->frame % (UI_FREQ / 2) != 0) {
    return;
  }

  updateButtons();
  updateStep();

  updateSpeedLimitsToggle->setEnabledButton(1, fs.frogpilot_scene.online && util::system_time_valid());

  if (updatingLimits) {
    if (QString::fromStdString(params_memory.get("UpdateSpeedLimitsStatus")) == "Completed!") {
      updatingLimits = false;

      updateSpeedLimitsToggle->setValue(tr("Completed!"));

      QTimer::singleShot(2500, [this]() {
        updateSpeedLimitsToggle->clearCheckedButtons(true);
        updateSpeedLimitsToggle->setValue("");
        updateSpeedLimitsToggle->setVisibleButton(0, false);
        updateSpeedLimitsToggle->setVisibleButton(1, true);

        params_memory.remove("UpdateSpeedLimitsStatus");
      });
    } else {
      updateSpeedLimitsToggle->setValue(QString::fromStdString(params_memory.get("UpdateSpeedLimitsStatus")));
    }
  }

  parent->keepScreenOn = primelessLayout->currentIndex() == 1 || updatingLimits;
}

void FrogPilotNavigationPanel::updateStep() {
  QString currentStep;
  if (setupCompleted) {
    currentStep = "../../frogpilot/navigation/navigation_training/setup_completed.png";
  } else if (mapboxPublicKeySet && mapboxSecretKeySet) {
    currentStep = "../../frogpilot/navigation/navigation_training/both_keys_set.png";
  } else if (mapboxPublicKeySet) {
    currentStep = "../../frogpilot/navigation/navigation_training/public_key_set.png";
  } else {
    currentStep = "../../frogpilot/navigation/navigation_training/no_keys_set.png";
  }

  QPixmap pixmap;
  pixmap.load(currentStep);
  imageLabel->setPixmap(pixmap.scaledToWidth(1500, Qt::SmoothTransformation));

  update();
}
