import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

class HomeScreen extends StatefulWidget {
  const HomeScreen({Key? key}) : super(key: key);

  @override
  _HomeScreenState createState() => _HomeScreenState();
}

class _HomeScreenState extends State<HomeScreen> {
  static const platform = MethodChannel('agnos_flutter');

  String _deviceInfo = 'No device info';
  String _carInfo = 'No car info';
  bool _awake = true;

  @override
  void initState() {
    super.initState();
    platform.setMethodCallHandler(_handleMethod);
  }

  Future<void> _handleMethod(MethodCall call) async {
    switch (call.method) {
      case 'updateDeviceInfo':
        setState(() {
          _deviceInfo = call.arguments as String;
        });
        break;
      case 'updateCarInfo':
        setState(() {
          _carInfo = call.arguments as String;
        });
        break;
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text('Home'),
      ),
      body: Center(
        child: Column(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            Text(_deviceInfo),
            const SizedBox(height: 20),
            Text(_carInfo),
            const SizedBox(height: 20),
            ElevatedButton(
              onPressed: () {
                setState(() {
                  _awake = !_awake;
                });
                platform.invokeMethod('setAwake', _awake);
              },
              child: Text(_awake ? 'Turn Screen Off' : 'Turn Screen On'),
            ),
          ],
        ),
      ),
    );
  }
}
