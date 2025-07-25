import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

class SettingsScreen extends StatefulWidget {
  const SettingsScreen({Key? key}) : super(key: key);

  @override
  _SettingsScreenState createState() => _SettingsScreenState();
}

class _SettingsScreenState extends State<SettingsScreen> {
  static const platform = MethodChannel('agnos_flutter');

  bool _isMetric = false;

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text('Settings'),
      ),
      body: ListView(
        children: [
          SwitchListTile(
            title: const Text('Use metric units'),
            value: _isMetric,
            onChanged: (value) {
              setState(() {
                _isMetric = value;
              });
              platform.invokeMethod('setMetric', value);
            },
          ),
        ],
      ),
    );
  }
}
