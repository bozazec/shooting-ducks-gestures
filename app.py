import gevent
from gevent import monkey
monkey.patch_all()

from flask import Flask, render_template, request
from flask_socketio import SocketIO, emit
import time
import random
import math
import gevent.event # Use gevent event

# Constants
SCREEN_WIDTH = 1280
SCREEN_HEIGHT = 720
DUCK_SPEED_START = 3  # Initial speed
STALE_SPEED_DUCKS = 5 # Increase speed every 10 ducks
DIFICULTY_PERCENTAGE = 30 # Increase speed by 10%
# DUCK_SPEED_MIN = 1 # Removed
# DUCK_SPEED_MAX = 4 # Removed
DUCK_SIZE = 80
DUCK_COLOR = (0, 255, 255) # Yellow (will be converted to hex later)
SPAWN_INTERVAL_MIN = 1.0
SPAWN_INTERVAL_MAX = 3.0
GAME_UPDATE_RATE = 1/30 # 30 FPS

app = Flask(__name__)
app.config['SECRET_KEY'] = 'secret!' # Change this in production
# Ensure async_mode is gevent for multi-session background tasks
socketio = SocketIO(app, async_mode='gevent')

# --- Duck Class (Server-Side) ---
class Duck:
    def __init__(self, speed): # Accept speed as argument
        self.id = random.randint(1000, 9999) # Simple ID for tracking
        self.x = 0
        self.y = random.randint(DUCK_SIZE, SCREEN_HEIGHT - DUCK_SIZE)
        self.speed = speed # Use the provided speed
        self.direction = random.choice([-1, 1]) # -1 for left to right, 1 for right to left
        if self.direction == 1:
            self.x = SCREEN_WIDTH
        self.size = DUCK_SIZE

    def move(self):
        self.x -= self.speed * self.direction

    def is_offscreen(self):
        return (self.direction == 1 and self.x < -self.size) or \
               (self.direction == -1 and self.x > SCREEN_WIDTH + self.size)

    def to_dict(self):
        # Convert to a dictionary for sending via SocketIO
        return {
            'id': self.id,
            'x': self.x,
            'y': self.y,
            'size': self.size,
            'direction': self.direction
        }

# --- Game Session Class ---
# Encapsulates the state and logic for a single player's game
class GameSession:
    def __init__(self, sid, socketio_instance):
        self.sid = sid
        self.socketio = socketio_instance
        self.ducks = []
        self.score = 0
        self.lives = 3
        self.game_active = True
        self.last_spawn_time = time.time()
        self.spawn_interval = random.uniform(SPAWN_INTERVAL_MIN, SPAWN_INTERVAL_MAX)
        self.spawned_ducks_count = 0
        self.current_duck_speed = DUCK_SPEED_START
        self._stop_event = gevent.event.Event() # Event specific to this session's loop
        self._game_loop_task = None

    def start_game_loop(self):
        """Starts the game loop for this session in a background task."""
        if self._game_loop_task is None:
            self._stop_event.clear() # Ensure event is clear before starting
            self._game_loop_task = self.socketio.start_background_task(self._run_game_loop)
            print(f"Started game loop for session {self.sid}")

    def stop_game_loop(self):
        """Signals the game loop for this session to stop."""
        if self._game_loop_task is not None:
            self._stop_event.set()
            # Optional: wait for the task to finish if needed, but might block disconnect
            # self._game_loop_task.join()
            print(f"Stopped game loop for session {self.sid}")
            self._game_loop_task = None # Clear the task handle

    def _run_game_loop(self):
        """The actual game loop logic for this session."""
        loop_count = 0
        print(f"Game loop running for {self.sid}")
        while not self._stop_event.is_set():
            # No app_context needed when using start_background_task with gevent
            if self.game_active:
                self._spawn_duck()
                self._move_ducks()
                self._remove_offscreen_ducks()

            # Prepare game state data specifically for this client
            game_state = {
                'ducks': [duck.to_dict() for duck in self.ducks],
                'score': self.score,
                'lives': self.lives,
                'game_active': self.game_active
            }

            if loop_count % 60 == 0: # Log less frequently per session
                 print(f"Session {self.sid} Loop {loop_count}: Emitting {len(game_state['ducks'])} ducks, Score: {game_state['score']}, Lives: {self.lives}, Active: {self.game_active}")

            try:
                # Emit only to the specific client associated with this session
                self.socketio.emit('game_update', game_state, to=self.sid)
            except Exception as e:
                # Handle potential errors if the client disconnected abruptly
                print(f"ERROR emitting game_update to SID {self.sid}: {e}")
                # Consider stopping the loop if emit fails consistently
                # self.stop_game_loop()
                # break # Exit loop

            loop_count += 1
            gevent.sleep(GAME_UPDATE_RATE) # Use gevent sleep

        print(f"Game loop for session {self.sid} has exited.")

    # --- Game Logic Methods (now part of GameSession) ---
    def _spawn_duck(self):
        current_time = time.time()
        if self.game_active and current_time - self.last_spawn_time > self.spawn_interval:
            if self.spawned_ducks_count > 0 and self.spawned_ducks_count % STALE_SPEED_DUCKS == 0:
                increase_factor = 1 + (DIFICULTY_PERCENTAGE / 100.0)
                self.current_duck_speed *= increase_factor
                # print(f"Session {self.sid}: Difficulty increased! New duck speed: {self.current_duck_speed:.2f}") # Less verbose logging

            self.ducks.append(Duck(self.current_duck_speed))
            self.spawned_ducks_count += 1
            self.last_spawn_time = current_time
            self.spawn_interval = random.uniform(SPAWN_INTERVAL_MIN, SPAWN_INTERVAL_MAX)

    def _move_ducks(self):
        for duck in self.ducks:
            duck.move()

    def _remove_offscreen_ducks(self):
        ducks_kept = []
        missed_count = 0
        for duck in self.ducks:
            if duck.is_offscreen():
                missed_count += 1
            else:
                ducks_kept.append(duck)

        if missed_count > 0:
            self.lives -= missed_count
            # print(f"Session {self.sid}: Missed {missed_count} duck(s). Lives remaining: {self.lives}") # Less verbose logging
            if self.lives <= 0:
                self.lives = 0
                self.game_active = False
                print(f"Session {self.sid}: Game Over!")
                # Emit game over state immediately? Or let the loop handle it? Loop is probably fine.

        self.ducks = ducks_kept

    def check_collision(self, aim_x, aim_y):
        if not self.game_active: # Don't register hits if game is over
             return False

        hit_duck_index = -1
        for i, duck in enumerate(self.ducks):
            effective_radius = (duck.size / 2) * 1.3
            dist_sq = (aim_x - duck.x)**2 + (aim_y - duck.y)**2

            if dist_sq < effective_radius**2:
                hit_duck_index = i
                break

        if hit_duck_index != -1:
            del self.ducks[hit_duck_index]
            self.score += 1
            print(f"Session {self.sid}: Hit detected at ({aim_x}, {aim_y}). Score: {self.score}")
           
            # Game loop will emit the updated score/duck list later
            return True
        return False

    def reset_game(self):
        """Resets the game state for this session."""
        print(f"Resetting game state for session {self.sid}...")
        self.ducks = []
        self.score = 0
        self.lives = 3
        self.game_active = True
        self.spawned_ducks_count = 0
        self.current_duck_speed = DUCK_SPEED_START
        self.last_spawn_time = time.time()
        self.spawn_interval = random.uniform(SPAWN_INTERVAL_MIN, SPAWN_INTERVAL_MAX)

        # Prepare the reset game state specifically for this client
        reset_state = {
            'ducks': [],
            'score': 0,
            'lives': self.lives,
            'game_active': self.game_active
        }
        # Emit the reset state directly to this client
        try:
            self.socketio.emit('game_update', reset_state, to=self.sid)
            print(f"Session {self.sid}: Game reset. Emitted reset state.")
        except Exception as e:
            print(f"ERROR emitting reset_game update to SID {self.sid}: {e}")


# --- Session Management ---
game_sessions = {} # Dictionary to store active GameSession instances {sid: GameSession}

# --- Flask Routes ---
@app.route('/')
def index():
    # Renders the main game page
    return render_template('index.html')

# --- SocketIO Events ---
@socketio.on('connect')
def handle_connect():
    sid = request.sid
    if sid in game_sessions:
        print(f"Client {sid} reconnected? Handling potential existing session.")
        # Decide how to handle reconnection: maybe stop old loop, create new?
        # For simplicity, let's stop the old one if it exists and create a new one.
        old_session = game_sessions.pop(sid, None)
        if old_session:
            old_session.stop_game_loop()

    print(f'Client connected: {sid}. Creating new game session.')
    # Create a new session for the connected client
    session = GameSession(sid, socketio)
    game_sessions[sid] = session
    session.start_game_loop() # Start the dedicated game loop for this session

    # Optional: Send an initial state or confirmation
    emit('connection_ack', {'message': 'Game session started!'}, to=sid)

@socketio.on('disconnect')
def handle_disconnect():
    sid = request.sid
    print(f'Client disconnected: {sid}. Cleaning up session.')
    session = game_sessions.pop(sid, None) # Remove session and get it
    if session:
        session.stop_game_loop() # Signal the session's game loop to stop
    else:
        print(f"Warning: No active session found for disconnected SID {sid}")
    print(f"Active sessions: {len(game_sessions)}")

@socketio.on('shoot')
def handle_shoot(data):
    """Handles shoot event from a client, routes to their session."""
    sid = request.sid
    session = game_sessions.get(sid)
    if session:
        aim_x = data.get('x')
        aim_y = data.get('y')
        if aim_x is not None and aim_y is not None:
            session.check_collision(aim_x, aim_y)
            # Score/state update is handled by the session's game loop emit
    else:
        print(f"Warning: Received 'shoot' from unknown/inactive session {sid}")

@socketio.on('reset_game')
def handle_reset():
    """Resets the game state for the requesting client's session."""
    sid = request.sid
    session = game_sessions.get(sid)
    if session:
        session.reset_game()
    else:
        print(f"Warning: Received 'reset_game' from unknown/inactive session {sid}")

# --- Main Execution ---
if __name__ == '__main__':
    print("Starting Flask-SocketIO development server (using gevent)...")
    # No global game loop to start here; loops are per-session.
    # Run using the development server with gevent worker
    # Use host='0.0.0.0' to make it accessible on the network
    # use_reloader=False is important when using background tasks managed this way
    socketio.run(app, debug=True, host='0.0.0.0', port=5001, use_reloader=False)

    # Cleanup happens naturally as the server process exits
    print("Server stopping...")
    # Note: Active gevent greenlets might not be explicitly joined here in a simple
    # dev server shutdown scenario, but stopping sessions on disconnect helps. 