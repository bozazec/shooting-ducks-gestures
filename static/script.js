const videoElement = document.getElementsByClassName('input_video')[0];
const canvasElement = document.getElementsByClassName('output_canvas')[0];
const canvasCtx = canvasElement.getContext('2d');
const scoreElement = document.getElementById('score');

const socket = io(); // Connect to the Flask-SocketIO server

let currentDucks = [];
let currentScore = 0;
let aimX = -1, aimY = -1;
let isShooting = false;
let lastShootState = false;

const DUCK_COLOR = '#FFFF00'; // Yellow
const AIM_COLOR = '#0000FF'; // Blue
const SHOOT_COLOR = '#FF0000'; // Red
const SHOOT_THRESHOLD = 30; // Pixel distance for pinch

// Load duck image
const duckImage = new Image();
duckImage.src = '/static/assets/duck.png'; // Path relative to the static folder served by Flask
let duckImageLoaded = false;
duckImage.onload = () => {
    console.log("Duck image loaded successfully.");
    duckImageLoaded = true;
};
duckImage.onerror = () => {
    console.error("Failed to load duck image.");
};

function drawGame(results) {
    canvasCtx.save();
    canvasCtx.clearRect(0, 0, canvasElement.width, canvasElement.height);

    // --- Apply Mirroring --- (Re-enabled)
    canvasCtx.translate(canvasElement.width, 0);
    canvasCtx.scale(-1, 1);

    // --- Draw Mirrored Webcam Image --- (Will be mirrored again)
    canvasCtx.drawImage(
        results.image, 0, 0, canvasElement.width, canvasElement.height);

    // --- Draw Ducks (in mirrored context) --- (Using MIRRORED coordinates again)
    if (duckImageLoaded) {
        currentDucks.forEach((duck, index) => {
            // Calculate mirrored X coordinate for drawing (Re-enabled)
            const mirroredDuckX = canvasElement.width - duck.x;
            const drawX = mirroredDuckX - duck.size / 2;
            // const drawX = duck.x - duck.size / 2; // Use original X
            const drawY = duck.y - duck.size / 2; // Y is not mirrored

            if (index === 0) { // Log EVERY frame for first duck
                 console.log(`Drawing Mirrored Duck ${index}: duck.x=${duck.x} -> mirroredX=${mirroredDuckX} -> drawX=${drawX}, drawY=${drawY}`);
                 // console.log(`Drawing Original Duck ${index}: duck.x=${duck.x} -> drawX=${drawX}, drawY=${drawY}`);
            }
            if (typeof drawX === 'number' && typeof drawY === 'number' && typeof duck.size === 'number' && duck.size > 0) {
                 canvasCtx.drawImage(duckImage, drawX, drawY, duck.size, duck.size);
            } else if (index === 0) {
                 console.warn(`Skipping drawing mirrored duck ${index} due to invalid coordinates/size:`, duck);
                 // console.warn(`Skipping drawing original duck ${index} due to invalid coordinates/size:`, duck);
            }
        });
    } else {
        // Fallback circles (also needs mirrored X) (Re-enabled)
        currentDucks.forEach(duck => {
            const mirroredDuckX = canvasElement.width - duck.x;
            canvasCtx.fillStyle = DUCK_COLOR;
            canvasCtx.beginPath();
            canvasCtx.arc(mirroredDuckX, duck.y, duck.size / 2, 0, 2 * Math.PI);
            // canvasCtx.arc(duck.x, duck.y, duck.size / 2, 0, 2 * Math.PI); // Use original X
            canvasCtx.fill();
        });
    }

    // --- Process Gestures and Draw Cursor (in mirrored context) --- (Using ORIGINAL coordinates for drawing)
    aimX = -1; // Keep track of the *final* shooting coordinate (mirrored)
    aimY = -1;
    isShooting = false;
    if (results.multiHandLandmarks && results.multiHandLandmarks.length > 0) {
        const landmarks = results.multiHandLandmarks[0];
        const indexTip = landmarks[8];
        const thumbTip = landmarks[4];

        const originalCursorX = indexTip.x * canvasElement.width;
        const originalCursorY = indexTip.y * canvasElement.height;
        const originalThumbX = thumbTip.x * canvasElement.width;
        const originalThumbY = thumbTip.y * canvasElement.height;

        const distance = Math.sqrt(Math.pow(originalThumbX - originalCursorX, 2) + Math.pow(originalThumbY - originalCursorY, 2));
        if (distance < SHOOT_THRESHOLD) {
            isShooting = true;
        }

        // Draw aiming cursor at ORIGINAL coordinates (it will be mirrored by the transform)
        canvasCtx.fillStyle = isShooting ? SHOOT_COLOR : AIM_COLOR;
        canvasCtx.beginPath();
        canvasCtx.arc(originalCursorX, originalCursorY, isShooting ? 15 : 10, 0, 2 * Math.PI);
        canvasCtx.fill();

        // Store the MIRRORED coordinates for the shoot event (Re-enabled)
        aimX = canvasElement.width - originalCursorX;
        // aimX = originalCursorX;
        aimY = originalCursorY;
    }

    // --- Detect Shoot Event and Emit (using mirrored coordinates) ---
    let shootEvent = false;
    if (isShooting && !lastShootState) {
        shootEvent = true;
    }
    lastShootState = isShooting;

    if (shootEvent && aimX !== -1) {
        socket.emit('shoot', { x: aimX, y: aimY });
        console.log("Sent shoot event at (mirrored):", aimX, aimY);
        // console.log("Sent shoot event at (original):", aimX, aimY);
    }

    // --- Restore canvas state (removes mirror) --- (Still needed)
    canvasCtx.restore();

    // Score is drawn outside the mirrored context by updating the HTML element
}

// --- MediaPipe Hands Setup ---
const hands = new Hands({
    locateFile: (file) => {
        return `https://cdn.jsdelivr.net/npm/@mediapipe/hands/${file}`;
    }
});
hands.setOptions({
    maxNumHands: 1,
    modelComplexity: 1,
    minDetectionConfidence: 0.7,
    minTrackingConfidence: 0.5
});
hands.onResults(drawGame);

// --- Camera Setup ---
const camera = new Camera(videoElement, {
    onFrame: async () => {
        await hands.send({ image: videoElement });
    },
    width: 1280,
    height: 720
});
camera.start();

// --- SocketIO Event Listener for Game Updates ---
socket.on('connect', () => {
    console.log('Socket.IO connected! ID:', socket.id);
});

socket.on('disconnect', (reason) => {
    console.log('Socket.IO disconnected:', reason);
});

socket.on('connect_error', (error) => {
    console.error('Socket.IO connection error:', error);
});

// Add listener for the test event
socket.on('test_event', (data) => {
    console.log('Received test_event:', data);
});

socket.on('game_update', (data) => {
    console.log('Received game update:', data);
    currentDucks = data.ducks;
    currentScore = data.score;
    scoreElement.textContent = `Score: ${currentScore}`;
    // Redrawing happens in the hands.onResults callback
});

console.log("Client script loaded and running."); 