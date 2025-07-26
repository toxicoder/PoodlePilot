import 'package:camera/camera.dart';
import 'package:flutter/material.dart';

class OnroadScreen extends StatefulWidget {
  const OnroadScreen({Key? key}) : super(key: key);

  @override
  _OnroadScreenState createState() => _OnroadScreenState();
}

class _OnroadScreenState extends State<OnroadScreen> {
  CameraController? _controller;
  List<CameraDescription>? _cameras;

  @override
  void initState() {
    super.initState();
    _initializeCamera();
  }

  Future<void> _initializeCamera() async {
    _cameras = await availableCameras();
    if (_cameras != null && _cameras!.isNotEmpty) {
      _controller = CameraController(_cameras![0], ResolutionPreset.high);
      _controller!.initialize().then((_) {
        if (!mounted) {
          return;
        }
        setState(() {});
      });
    }
  }

  @override
  void dispose() {
    _controller?.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    if (_controller == null || !_controller!.value.isInitialized) {
      return Container();
    }
    return Scaffold(
      body: Stack(
        children: [
          CameraPreview(_controller!),
        ],
      ),
    );
  }
}
