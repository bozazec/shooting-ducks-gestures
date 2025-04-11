const videoElement = document.getElementsByClassName('input_video')[0];
const canvasElement = document.getElementsByClassName('output_canvas')[0];
const canvasCtx = canvasElement.getContext('2d');
const scoreElement = document.getElementById('score');
const soundButton = document.getElementById('toggle-sound-button');
const gunshotSound = document.getElementById('gunshot-sound');

const socket = io(); // Connect to the Flask-SocketIO server

let currentDucks = [];
let currentScore = 0;
// Remove unused single-hand tracking variables
// let aimX = -1, aimY = -1;
// let isShooting = false;
// let lastShootState = false; // Keep for single-hand logic temporarily
let lastShootStates = {}; // Track state for each hand {handIndex: boolean}

// Sound state
let isSoundEnabled = true; // Default to ON

const DUCK_COLOR = '#FFFF00'; // Yellow
const AIM_COLOR = '#0000FF'; // Blue
const SHOOT_COLOR = '#FF0000'; // Red
const SHOOT_THRESHOLD = 30; // Pixel distance for pinch

// Load duck image
const duckImage = new Image();
duckImage.src = '/static/assets/pumpaj.png'; // Path relative to the static folder served by Flask
let duckImageLoaded = false;
duckImage.onload = () => {
    console.log("Duck image loaded successfully.");
    duckImageLoaded = true;
};
duckImage.onerror = () => {
    console.error("Failed to load duck image.");
};

// Function to update sound state and button text
function updateSoundState(enabled) {
    isSoundEnabled = enabled;
    soundButton.textContent = `Sound: ${enabled ? 'ON' : 'OFF'}`;
    localStorage.setItem('shootingDucksSoundEnabled', enabled);
    if (enabled) {
        // Optional: Play a short sound to confirm activation
        // gunshotSound.play();
    }
}

// --- Initialize Sound State from localStorage ---
document.addEventListener('DOMContentLoaded', () => {
    const savedSoundSetting = localStorage.getItem('shootingDucksSoundEnabled');
    // If there is a saved setting, use it, otherwise default to true (ON)
    const initialSoundState = savedSoundSetting !== null ? JSON.parse(savedSoundSetting) : true;
    updateSoundState(initialSoundState);
});

// --- Sound Toggle Button Listener ---
soundButton.addEventListener('click', () => {
    updateSoundState(!isSoundEnabled); // Toggle the state
});

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
            canvasCtx.save(); // Save context state before potential flip

            const mirroredDuckX = canvasElement.width - duck.x;
            const drawX = mirroredDuckX - duck.size / 2;
            const drawY = duck.y - duck.size / 2;

            // Flip the duck image if moving left-to-right (direction == -1)
            // Note: Since the whole canvas is already mirrored, a left-to-right
            // moving duck (negative direction) appears to move rightwards.
            // We need to flip it horizontally again around its center to face right.
            if (duck.direction === -1) {
                // Translate to the center of the duck, flip, translate back
                canvasCtx.translate(mirroredDuckX, drawY + duck.size / 2);
                canvasCtx.scale(-1, 1); // Flip horizontally
                canvasCtx.translate(-mirroredDuckX, -(drawY + duck.size / 2));
            }

            // if (index === 0) { // Log EVERY frame for first duck - REMOVED for clarity
            //      console.log(`Drawing Mirrored Duck ${index}: duck.x=${duck.x} -> mirroredX=${mirroredDuckX} -> drawX=${drawX}, drawY=${drawY}, dir=${duck.direction}`);
            // }

            if (typeof drawX === 'number' && typeof drawY === 'number' && typeof duck.size === 'number' && duck.size > 0) {
                // Draw the image at the original (mirrored) position,
                // the context flip handles the orientation
                canvasCtx.drawImage(duckImage, drawX, drawY, duck.size, duck.size);
            } else if (index === 0) {
                console.warn(`Skipping drawing mirrored duck ${index} due to invalid coordinates/size:`, duck);
            }

            canvasCtx.restore(); // Restore context state (removes individual duck flip)
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

    // --- Process Gestures and Draw Cursor (in mirrored context) ---
    // Reset states for hands not currently detected
    const currentHandIndices = results.multiHandLandmarks ? results.multiHandLandmarks.map((_, i) => i) : [];
    Object.keys(lastShootStates).forEach(key => {
        if (!currentHandIndices.includes(parseInt(key))) {
            delete lastShootStates[key];
        }
    });

    if (results.multiHandLandmarks) {
        results.multiHandLandmarks.forEach((landmarks, index) => {
            const indexTip = landmarks[8];
            const thumbTip = landmarks[4];

            if (!indexTip || !thumbTip) return; // Skip if landmarks are missing

            const originalCursorX = indexTip.x * canvasElement.width;
            const originalCursorY = indexTip.y * canvasElement.height;
            const originalThumbX = thumbTip.x * canvasElement.width;
            const originalThumbY = thumbTip.y * canvasElement.height;

            const distance = Math.sqrt(Math.pow(originalThumbX - originalCursorX, 2) + Math.pow(originalThumbY - originalCursorY, 2));
            const isHandShooting = distance < SHOOT_THRESHOLD;

            // Draw aiming cursor at ORIGINAL coordinates (it will be mirrored by the transform)
            canvasCtx.fillStyle = isHandShooting ? SHOOT_COLOR : AIM_COLOR;
            canvasCtx.beginPath();
            canvasCtx.arc(originalCursorX, originalCursorY, isHandShooting ? 15 : 10, 0, 2 * Math.PI);
            canvasCtx.fill();

            // --- Detect Shoot Event and Emit for this hand ---
            const wasShooting = lastShootStates[index] || false; // Get previous state, default to false
            let shootEvent = false;
            if (isHandShooting && !wasShooting) {
                shootEvent = true;
            }
            lastShootStates[index] = isHandShooting; // Update state for this hand index

            if (shootEvent) {
                // Store the MIRRORED coordinates for the shoot event
                const mirroredAimX = canvasElement.width - originalCursorX;
                const mirroredAimY = originalCursorY;

                // Emit the shoot event to the server
                socket.emit('shoot', { x: mirroredAimX, y: mirroredAimY });
                console.log(`Sent shoot event for hand ${index} at (mirrored):`, mirroredAimX, mirroredAimY);

                // --- Play sound if enabled ---
                if (isSoundEnabled && gunshotSound) {
                    gunshotSound.currentTime = 0; // Allow rapid firing
                    gunshotSound.play().catch(error => {
                        // Autoplay might be blocked, log error
                        console.error("Error playing sound:", error);
                    });
                }

                // --- Display bullet hole effect on shoot ---
                const gameContainer = document.querySelector('.container');
                if (gameContainer) {
                    // Create Bullet Hole
                    const bulletHole = document.createElement('div');
                    bulletHole.classList.add('bullet-hole');
                    bulletHole.style.left = `${mirroredAimX - 5}px`;
                    bulletHole.style.top = `${mirroredAimY - 5}px`;
                    gameContainer.appendChild(bulletHole);
                    setTimeout(() => {
                        if (bulletHole.parentNode) {
                            bulletHole.parentNode.removeChild(bulletHole);
                        }
                    }, 2000);

                    // Create Explosion
                    const explosion = document.createElement('div');
                    explosion.classList.add('explosion');
                    explosion.style.left = `${mirroredAimX - 25}px`; // 25 is half of 50px
                    explosion.style.top = `${mirroredAimY - 25}px`; // 25 is half of 50px
                    gameContainer.appendChild(explosion);
                    setTimeout(() => {
                        if (explosion.parentNode) {
                            explosion.parentNode.removeChild(explosion);
                        }
                    }, 500); // 0.5s duration

                } else {
                    console.error("Could not find game container to show effects.");
                }
            }
        });
    }

    // --- Restore canvas state (removes mirror) ---
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
    maxNumHands: 2,
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