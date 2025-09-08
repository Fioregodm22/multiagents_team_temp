

#//SOCKETER
import agentpy as ap
import socket
import json
import threading
import time
import random

# -------------------------
# Car Agent
# -------------------------
class CarAgent(ap.Agent):
    _id_counter = 0

    def setup(self, start_position=None, lane=1, direction='north'):
        if start_position is None:
            start_position = [0.0, -120.0]

        self.car_id = CarAgent._id_counter
        CarAgent._id_counter += 1

        self.position = start_position
        self.speed = 1.0
        self.stopped = False
        self.lane = lane
        self.direction = direction
        self.turning = False
        self.rotation = 0.0 if direction == 'north' else 180.0
        self.turn_direction = None
        self.will_turn = random.choice([True, False]) if lane in [2, 3] else False

        # Lane 5 diagonal
        if lane == 5:
            self.movement_pattern = random.choice([1, 2, 3])
            self.phase = 'diagonal'
            self.rotation = 45.0
        # Lane 4 diagonal mirror
        elif lane == 4:
            self.movement_pattern = random.choice([1, 2])
            self.phase = 'diagonal'
            self.rotation = 115.0  # mirrored
        else:
            self.movement_pattern = None
            self.phase = None

    def step(self, lights, cars):
        stop_distance = 10.0

        # -----------------------------
        # Special handling for lane 5 (diagonal)
        # -----------------------------
        if self.lane == 5:
            stop_x = None
            light = None
            if self.phase == 'diagonal':
                stop_x = -8.0
                light = lights['left']
            elif self.phase == 'turn_right':
                stop_x = 20.0
                light = lights['left']
            elif self.phase == 'reverse':
                stop_x = 9.0
                light = lights['left']

            # Check near light
            near_light = abs(self.position[0] - stop_x) < stop_distance + 5.0 if stop_x else False
            obey_light = (self.position[1] < -40) and (self.position[0] < -2)

            # Check car ahead
            car_ahead = any(
                other != self and other.lane == 5 and
                ((other.position[0] - self.position[0])**2 + (other.position[1] - self.position[1])**2)**0.5 < 8.0 and
                other.position[0] > self.position[0]
                for other in cars
            )

            self.stopped = (light and light.state in ['red', 'yellow'] and near_light and obey_light) or car_ahead

            if not self.stopped:
                # Phase transitions
                if self.phase == 'diagonal':
                    if self.movement_pattern == 1 and self.position[0] >= 4.5:
                        self.phase = 'turn_right'
                        self.rotation = 0.0
                    elif self.movement_pattern == 2 and self.position[0] >= 20.0:
                        self.phase = 'turn_right'
                        self.rotation = 0.0
                    elif self.movement_pattern == 3 and self.position[0] >= 9.0:
                        self.phase = 'reverse'
                        self.rotation = -70.0

                # Movement
                if self.phase == 'diagonal':
                    self.position[0] += self.speed * 0.85
                    self.position[1] += self.speed * 0.7
                elif self.phase == 'turn_right':
                    if self.movement_pattern == 1:
                        self.position[1] -= self.speed
                    else:
                        self.position[1] += self.speed
                elif self.phase == 'reverse':
                    self.position[0] -= self.speed * 0.9
                    self.position[1] += self.speed * 0.5
            return  # skip normal logic

        # -----------------------------
        # Special handling for lane 4 (mirrored diagonal)
        # -----------------------------
        if self.lane == 4:
            stop_x = None
            light = None
            if self.phase == 'diagonal':
                stop_x = 8.0
                light = lights['right']
            elif self.phase == 'turn_left':
                stop_x = 20.0
                light = lights['right']

            near_light = abs(self.position[0] - stop_x) < stop_distance + 5.0 if stop_x else False
            obey_light = (self.position[1] > -35) and (self.position[0] < -2)

            # Check car ahead in lane 4
            car_ahead = any(
                other != self and other.lane == 4 and
                ((other.position[0] - self.position[0])**2 + (other.position[1] - self.position[1])**2)**0.5 < 8.0 and
                other.position[0] > self.position[0]
                for other in cars
            )

            self.stopped = (light and light.state in ['red', 'yellow'] and near_light and obey_light) or car_ahead

            if not self.stopped:
                # Phase transitions
                if self.phase == 'diagonal':
                    if self.movement_pattern in [1] and self.position[0] >= 4.5:
                        self.phase = 'turn_left'
                        self.rotation = 180.0
                    elif self.movement_pattern in [2] and self.position[0] >= 20.0:
                        self.phase = 'turn_left'
                        self.rotation = -180.0

                # Movement
                if self.phase == 'diagonal':
                    self.position[0] += self.speed * 0.85
                    self.position[1] -= self.speed * 0.35  # reversed z
                elif self.phase == 'turn_left':
                    if self.movement_pattern == 1:
                        self.position[1] -= self.speed
                    else:
                        self.position[1] += self.speed
            return  # skip normal logic

        # -----------------------------
        # Normal lanes (north/south/east/west)
        # -----------------------------
        if self.direction == 'north':
            stop_z = -65.0
            movement_direction = 1
            light = lights['north']
            turn_point_z = -39.0
            turn_target_x = -70.0
        elif self.direction == 'south':
            stop_z = -18.0
            movement_direction = -1
            light = lights['south']
            turn_point_z = -30.0
            turn_target_x = -70.0
        elif self.direction == 'east':
            stop_x = 65.0
            movement_direction = -1
            light = lights['right']
        elif self.direction == 'west':
            stop_x = -65.0
            movement_direction = 1
            light = lights['left']
        else:
            return

        # Turning logic for north/south - NEW: Check left arrow for lane 2
        if self.direction in ['north', 'south'] and not self.turning and self.will_turn:
            if self.lane == 2 and self.direction == 'north' and self.position[1] >= turn_point_z:
                # Lane 2 can only turn left when left arrow is green
                if lights['left_arrow'].state == 'green':
                    self.turning = True
                    self.rotation = -70.0
                    self.turn_direction = 'left'
            elif self.lane == 3 and self.direction == 'south' and self.position[1] <= turn_point_z:
                self.turning = True
                self.rotation = -70.0
                self.turn_direction = 'right'

        # Check if near light
        near_light = False
        if self.direction == 'north':
            near_light = (self.position[1] >= stop_z and self.position[1] < stop_z + stop_distance and not self.turning)
        elif self.direction == 'south':
            near_light = (self.position[1] <= stop_z and self.position[1] > stop_z - stop_distance and not self.turning)
        elif self.direction == 'east':
            near_light = (self.position[0] <= stop_x and self.position[0] > stop_x - stop_distance)
        elif self.direction == 'west':
            near_light = (self.position[0] >= stop_x and self.position[0] < stop_x + stop_distance)

        # Check car ahead
        car_ahead = False
        if not self.turning and self.direction in ['north', 'south']:
            for other in cars:
                if other == self:
                    continue
                if other.direction == self.direction and abs(other.position[0] - self.position[0]) < 5.0:
                    if self.direction == 'north' and 0 < other.position[1] - self.position[1] < 8.0:
                        car_ahead = True
                        break
                    elif self.direction == 'south' and 0 < self.position[1] - other.position[1] < 8.0:
                        car_ahead = True
                        break

        # Stop logic - When left arrow is green, only lanes 1 and 2 can move
        stop_for_light = False
        if not self.turning:
            # Check if left arrow is green (only lanes 1 and 2 can move)
            if lights['left_arrow'].state == 'green':
                # Only lanes 1 and 2 (northbound) can move during left arrow phase
                if not (self.lane in [1, 2] and self.direction == 'north'):
                    stop_for_light = True
            # Normal light checking
            elif light.state in ["red", "yellow"] and near_light:
                stop_for_light = True
            # Lane 2 cars wanting to turn left must stop if left arrow is red
            elif (self.lane == 2 and self.will_turn and self.direction == 'north' and 
                  near_light and lights['left_arrow'].state in ['red', 'yellow']):
                stop_for_light = True
                
        self.stopped = stop_for_light or car_ahead

        # Move car
        if not self.stopped:
            if self.turning:
                if self.turn_direction == 'left':
                    if self.position[0] > turn_target_x:
                        self.position[0] -= self.speed * 1.4
                        self.position[1] += self.speed * 0.7
                    else:
                        self.position[0] -= self.speed
                elif self.turn_direction == 'right':
                    if self.direction == 'north':
                        if self.position[0] < turn_target_x:
                            self.position[0] += self.speed * 1.3
                            self.position[1] += self.speed * 0.7
                        else:
                            self.position[0] += self.speed
                    else:
                        self.position[0] -= self.speed * 1.2
                        self.position[1] += self.speed * 0.6
            else:
                if self.direction in ['north', 'south']:
                    self.position[1] += self.speed * movement_direction
                elif self.direction == 'east':
                    self.position[0] += self.speed * movement_direction
                elif self.direction == 'west':
                    self.position[0] += self.speed * movement_direction

# -------------------------
# Traffic Light
# -------------------------
class TrafficLight(ap.Agent):
    def setup(self, name='north', axis='z', position=0.0, green_duration=5.0, red_duration=5.0):
        # Identification
        self.name = name          # e.g., 'north', 'south', 'left', 'right', 'left_arrow'
        self.axis = axis          # 'z' for vertical roads, 'x' for horizontal/branches
        self.position = position  # numerical value along the axis

        # State and timers
        self.state = 'red'
        self.timer = 0.0
        self.green_duration = green_duration
        self.red_duration = red_duration

    def step(self, dt):
        # Update timer
        self.timer += dt

        # Switch lights based on timer
        if self.state == 'red' and self.timer >= self.red_duration:
            self.state = 'green'
            self.timer = 0.0
        elif self.state == 'green' and self.timer >= self.green_duration:
            self.state = 'red'
            self.timer = 0.0


# -------------------------
# Traffic Controller
# -------------------------
class TrafficController:
    def __init__(self, lights, phases):
        """
        lights: dict of TrafficLight instances, e.g. {'north': light, 'south': light, ...}
        phases: list of dicts, each dict maps light name to color + 'duration' key
        """
        self.lights = lights
        self.phases = phases
        self.current_phase_index = 0
        self.timer = 0.0

        # Initialize lights to first phase
        self.apply_phase(self.phases[0])

    def apply_phase(self, phase):
        for name, state in phase.items():
            if name == 'duration':
                continue
            if name in self.lights:
                self.lights[name].state = state
                self.lights[name].timer = 0.0  # reset each light timer

    def step(self, dt):
        self.timer += dt
        current_phase = self.phases[self.current_phase_index]
        if self.timer >= current_phase['duration']:
            # Move to next phase
            self.current_phase_index = (self.current_phase_index + 1) % len(self.phases)
            next_phase = self.phases[self.current_phase_index]
            self.apply_phase(next_phase)
            self.timer = 0.0

# -------------------------
# Traffic Model
# -------------------------
class TrafficModel(ap.Model):
    def setup(self):
        self.cars = []

        # Define lights - NEW: Added left_arrow light
        self.north_light = TrafficLight(self); self.north_light.setup('north', 'z', -65.0)
        self.south_light = TrafficLight(self); self.south_light.setup('south', 'z', -22.0)
        self.left_light  = TrafficLight(self); self.left_light.setup('left', 'x', -65.0)
        self.right_light = TrafficLight(self); self.right_light.setup('right', 'x', 65.0)
        self.left_arrow_light = TrafficLight(self); self.left_arrow_light.setup('left_arrow', 'z', -65.0)

        lights = {
            'north': self.north_light,
            'south': self.south_light,
            'left': self.left_light,
            'right': self.right_light,
            'left_arrow': self.left_arrow_light
        }

        self.phases = [
            # --- NORTH/SOUTH block ---
            # Phase 1: Protected North left + North/South straight
            {'north': 'green', 'south': 'green', 'left': 'red', 'right': 'red', 'left_arrow': 'green', 'duration': 7},

            # Phase 2: North/South straight continues (arrow off)
            {'north': 'green', 'south': 'green', 'left': 'red', 'right': 'red', 'left_arrow': 'red', 'duration': 11},

            # Phase 3: North/South yellow (both directions)
            {'north': 'yellow', 'south': 'yellow', 'left': 'red', 'right': 'red', 'left_arrow': 'red', 'duration': 5},


            # --- EAST block ---
            # Phase 4: East left turn only
            {'north': 'red', 'south': 'red', 'left': 'green', 'right': 'red', 'left_arrow': 'red', 'duration': 8},

            # Phase 5: East yellow
            {'north': 'red', 'south': 'red', 'left': 'yellow', 'right': 'red', 'left_arrow': 'red', 'duration': 5},


            # --- WEST block ---
            # Phase 6: West right turn only
            {'north': 'red', 'south': 'red', 'left': 'red', 'right': 'green', 'left_arrow': 'red', 'duration': 8},

            # Phase 7: West yellow
            {'north': 'red', 'south': 'red', 'left': 'red', 'right': 'yellow', 'left_arrow': 'red', 'duration': 5},
        ]





        self.controller = TrafficController(lights, self.phases)

        # Spawn timers
        self.spawn_timer_lane1 = random.uniform(0, 3)
        self.spawn_timer_lane2 = random.uniform(0, 3)
        self.spawn_timer_lane3 = random.uniform(0, 3)
        self.spawn_timer_lane4 = random.uniform(0, 3)
        self.spawn_timer_lane5 = random.uniform(0, 3)

    def step(self):
        dt = 0.1
        self.spawn_timer_lane1 += dt
        self.spawn_timer_lane2 += dt
        self.spawn_timer_lane3 += dt
        self.spawn_timer_lane4 += dt
        self.spawn_timer_lane5 += dt

        # Spawn cars northbound
        if self.spawn_timer_lane1 >= 3.0:
            car = CarAgent(self); car.setup([25.0, -120.0], lane=1, direction='north')
            self.cars.append(car); self.spawn_timer_lane1 = random.uniform(-1, 2)

        if self.spawn_timer_lane2 >= 3.0:
            car = CarAgent(self); car.setup([20.0, -120.0], lane=2, direction='north')
            self.cars.append(car); self.spawn_timer_lane2 = random.uniform(-6, 1)

        # Spawn cars southbound
        if self.spawn_timer_lane3 >= 3.0:
            car = CarAgent(self); car.setup([0.0, 15.0], lane=3, direction='south')
            self.cars.append(car); self.spawn_timer_lane3 = random.uniform(-1, 1)

        if self.spawn_timer_lane4 >= 4.0:
            car = CarAgent(self); car.setup([-70.0, -6.0], lane=4, direction='diagonal')
            self.cars.append(car)
            self.spawn_timer_lane4 = random.uniform(-8, -2)
        # Spawn cars in diagonal lane (lane 5)
        if self.spawn_timer_lane5 >= 4.0:
            car = CarAgent(self); car.setup([-60.0, -91.0], lane=5, direction='diagonal')
            self.cars.append(car); self.spawn_timer_lane5 = random.uniform(-8, -2)

        # Update lights via controller
        self.controller.step(dt)

        # Update cars - NEW: Pass left_arrow light to cars
        lights = {
            'north': self.north_light,
            'south': self.south_light,
            'left': self.left_light,
            'right': self.right_light,
            'left_arrow': self.left_arrow_light
        }
        for car in self.cars:
            car.step(lights, self.cars)

        # Remove cars out of bounds
        self.cars = [car for car in self.cars if -150.0 < car.position[1] < 50.0 and -100.0 < car.position[0] < 100.0]

    def get_state(self):
        return {
            'cars': [
                {
                    'car_id': car.car_id,
                    'position': car.position,
                    'stopped': car.stopped,
                    'lane': car.lane,
                    'turning': car.turning,
                    'rotation': car.rotation,
                    'direction': car.direction,
                    'movement_pattern': getattr(car, 'movement_pattern', None),
                    'phase': getattr(car, 'phase', None)
                } for car in self.cars
            ],
            'lights': {name: {'state': light.state, 'timer': round(light.timer, 1)} for name, light in {
                'north': self.north_light,
                'south': self.south_light,
                'left': self.left_light,
                'right': self.right_light,
                'left_arrow': self.left_arrow_light
            }.items()}
        }

# -------------------------
# Socket Server
# -------------------------
class SocketServer(threading.Thread):
    def __init__(self, model, host='127.0.0.1', port=5555):
        super().__init__()
        self.model = model
        self.host = host
        self.port = port
        self.running = True
        self.sock = None
        self.client_conn = None

    def run(self):
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.sock.bind((self.host, self.port))
        self.sock.listen(1)
        print(f"Server listening on {self.host}:{self.port}")

        self.client_conn, addr = self.sock.accept()
        print(f"Unity connected from {addr}")

        try:
            while self.running:
                self.model.step()
                state = self.model.get_state()
                message = json.dumps(state).encode('utf-8')
                self.client_conn.sendall(message + b'\n')
                time.sleep(0.05)
        finally:
            if self.client_conn:
                self.client_conn.close()
            if self.sock:
                self.sock.close()

    def stop(self):
        self.running = False

# -------------------------
# Main
# -------------------------
if __name__ == "__main__":
    model = TrafficModel()
    model.setup()
    server = SocketServer(model)
    server.start()
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        server.stop()
        server.join()

