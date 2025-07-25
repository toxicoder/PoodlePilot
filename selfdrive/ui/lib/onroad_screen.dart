import 'package:flutter/material.dart';

class OnroadScreen extends StatefulWidget {
  const OnroadScreen({Key? key}) : super(key: key);

  @override
  _OnroadScreenState createState() => _OnroadScreenState();
}

class _OnroadScreenState extends State<OnroadScreen> {
  @override
  Widget build(BuildContext context) {
    return Scaffold(
      body: Stack(
        children: [
          Container(
            color: Colors.black,
            child: const Center(
              child: Text(
                'Camera feed',
                style: TextStyle(color: Colors.white),
              ),
            ),
          ),
        ],
      ),
    );
  }
}
