# Duck Hunt with Hand Gestures

A modern take on the classic Duck Hunt game using hand gesture controls through your webcam. Shoot ducks by pinching your thumb and index finger together!

Created using Gemini 2.5 prop exp 03-25

## Make this game politically controversial
Change the duck image at location `static/assets/pumpaj.png`

## Features
- Real-time hand tracking using MediaPipe Hands
- Gesture-based shooting controls
- Dynamic duck spawning and movement
- Score tracking
- Responsive canvas display

## Requirements
- Python 3.x
- Webcam
- Modern web browser
- Required Python packages (install via `pip install -r requirements.txt`):
  - Flask
  - Flask-SocketIO
  - OpenCV-Python
  - MediaPipe

## How to Play
1. Install requirements running `pip install -r requirements.txt` (or pip3)
2. Run `python app.py` to start the server
3. Open your browser to `http://localhost:5001`
4. Allow webcam access when prompted
5. Point at ducks with your index finger
6. Pinch your thumb and index finger together to shoot
7. Hit ducks to score points!

## Technical Stack
- Frontend: HTML5 Canvas, JavaScript, MediaPipe Hands
- Backend: Flask, Flask-SocketIO
- Real-time communication via WebSocket
