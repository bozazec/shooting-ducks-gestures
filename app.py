from flask import Flask, render_template
from flask_socketio import SocketIO, emit
import time
import random
import math
import threading # Use standard threading

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
socketio = SocketIO(app, async_mode='threading')

# --- Global Set to Track Connected Clients ---
connected_clients = set()

# --- Game State (Server-Side) ---
ducks = []
score = 0
last_spawn_time = time.time()
spawn_interval = random.uniform(SPAWN_INTERVAL_MIN, SPAWN_INTERVAL_MAX)
spawned_ducks_count = 0 # Track total ducks spawned
current_duck_speed = DUCK_SPEED_START # Current speed for new ducks

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

# --- Game Logic Functions (Server-Side) ---
def spawn_duck():
    global last_spawn_time, spawn_interval, spawned_ducks_count, current_duck_speed
    current_time = time.time()
    if current_time - last_spawn_time > spawn_interval:
        # Increase speed if needed BEFORE spawning the new duck
        if spawned_ducks_count > 0 and spawned_ducks_count % STALE_SPEED_DUCKS == 0:
            increase_factor = 1 + (DIFICULTY_PERCENTAGE / 100.0)
            current_duck_speed *= increase_factor
            print(f"Difficulty increased! New duck speed: {current_duck_speed:.2f}")

        # Spawn the duck with the current speed
        ducks.append(Duck(current_duck_speed))
        spawned_ducks_count += 1 # Increment after spawning
        last_spawn_time = current_time
        spawn_interval = random.uniform(SPAWN_INTERVAL_MIN, SPAWN_INTERVAL_MAX)

def move_ducks():
    for duck in ducks:
        duck.move()

def remove_offscreen_ducks():
    global ducks
    ducks = [duck for duck in ducks if not duck.is_offscreen()]

def check_collision(aim_x, aim_y):
    global ducks, score
    hit_duck_index = -1
    for i, duck in enumerate(ducks):
        # Increase hitbox radius by 30%
        effective_radius = (duck.size / 2) * 1.3
        dist_sq = (aim_x - duck.x)**2 + (aim_y - duck.y)**2
        if dist_sq < effective_radius**2:
            hit_duck_index = i
            break

    if hit_duck_index != -1:
        del ducks[hit_duck_index]
        score += 1
        return True # Indicate a hit
    return False

# --- Background Task for Game Updates (using standard threading) ---
stop_event = threading.Event() # To signal the thread to stop

def game_loop():
    """Periodically updates game state and broadcasts to clients."""
    loop_count = 0
    while not stop_event.is_set(): # Check the stop event
        with app.app_context(): # Need app context for emit outside of request
            spawn_duck()
            move_ducks()
            remove_offscreen_ducks()

            # Prepare game state data for clients
            game_state = {
                'ducks': [duck.to_dict() for duck in ducks],
                'score': score
            }
            if loop_count % 30 == 0: # Log every ~second
                # Make a copy of the set to avoid issues if it changes during iteration
                clients_to_update = list(connected_clients)
                print(f"Game Loop Thread {loop_count}: Emitting {len(game_state['ducks'])} ducks, Score: {game_state['score']} to {len(clients_to_update)} clients.")

            # Emit specifically to each connected client
            for sid in clients_to_update:
                print(f"Attempting to emit game_update to SID: {sid}") # Add log before emit
                try:
                    socketio.emit('game_update', game_state, to=sid)
                except Exception as e:
                    print(f"ERROR emitting game_update to SID {sid}: {e}") # Log potential errors

            loop_count += 1
        # Use time.sleep with standard threading
        time.sleep(GAME_UPDATE_RATE)
    print("Game loop thread stopped.")

# --- Flask Routes ---
@app.route('/')
def index():
    return render_template('index.html')

# --- SocketIO Events ---
@socketio.on('connect')
def handle_connect():
    # Correct way to get sid within event handler
    from flask import request
    sid = request.sid
    connected_clients.add(sid) # Add client to the set
    print(f'Client connected: {sid}. Total clients: {len(connected_clients)}')
    # Emit a test event directly to the newly connected client
    emit('test_event', {'data': 'Server says hello upon connection!'}, to=sid) # Target specific client
    print(f"Sent 'test_event' to {sid}")

@socketio.on('disconnect')
def handle_disconnect():
    from flask import request
    sid = request.sid
    connected_clients.discard(sid) # Remove client from the set
    print(f'Client disconnected: {sid}. Total clients: {len(connected_clients)}')

@socketio.on('shoot')
def handle_shoot(data):
    """Handles shoot event from a client."""
    aim_x = data.get('x')
    aim_y = data.get('y')
    if aim_x is not None and aim_y is not None:
        hit = check_collision(aim_x, aim_y)
        if hit:
            print(f"Hit detected at ({aim_x}, {aim_y}). Score: {score}")
            # No need to emit score update immediately, game_loop handles it


if __name__ == '__main__':
    print("Starting game loop thread...")
    # Start the game loop in a separate thread
    game_thread = threading.Thread(target=game_loop)
    game_thread.start()

    print("Starting Flask-SocketIO development server on port 5001...")
    # Run using the development server (handles threading)
    socketio.run(app, debug=True, host='0.0.0.0', port=5001, use_reloader=False)

    # Signal the game loop thread to stop when the server exits
    print("Server stopping, signaling game loop thread...")
    stop_event.set()
    game_thread.join() # Wait for the thread to finish
    print("Exited cleanly.") 