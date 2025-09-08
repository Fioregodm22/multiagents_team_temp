import socket
import json
import threading
import time
import numpy as np
import agentpy as ap

# Import all classes from the Logic Client (assuming they're in the same file or imported)
# Copy all the classes from Logic Client here or import them

class TrafficLight(ap.Agent):
    def setup(self):
        self.state = 'red'   # todos empiezan en rojo
        self._timer = 0.0
        self.vehicles_passed = 0

class Vehicle(ap.Agent):
    def setup(self, x=None, y=None, direction=None, light=None, stop_x=None, stop_y=None,
              go_north=False, go_south=False, speed=1.0, integrate_y=None, integrate_dir=None, lane='top'):

        # Add unique car ID
        self.car_id = getattr(Vehicle, '_id_counter', 0)
        Vehicle._id_counter = getattr(Vehicle, '_id_counter', 0) + 1

        # Defaults por si llegan None (evita AttributeError)
        self.x = 0 if x is None else x
        self.y = 0 if y is None else y
        self.direction = 1 if direction is None else direction
        self.light = light
        self.stop_x = stop_x
        self.stop_y = stop_y
        self.go_north = go_north
        self.go_south = go_south
        self.speed = speed
        self.integrate_y = integrate_y
        self.integrate_dir = integrate_dir
        self.lane = lane
        self.horizontal_turn_steps = 0

        # Estado
        self.arrived = False
        self.turning_north = False
        self.waiting_for_green = False
        self.cleared_stop3 = False
        self.passed_light = False
        self.turning_right = False
        self.diagonal_phase = False
        self.diagonal_steps = 0
        self.vertical_phase = False
        self.go_straight = False
        self.go_diag_up = False
        self.go_diag_down = False
        self.direction2 = self.direction

        self.counted_pass = False

        # Nuevas variables para controlar diagonal hasta punto específico
        self.diagonal_target_x = None
        self.diagonal_target_y = None
        self.reached_diagonal_target = False

        # Inicializar posición según carril
        if lane == "bottom":
            self.x, self.y = 0, 22
            self.direction = 1
            self.light = self.model.lights[0]
            self.stop_x = 23.5
            self.go_straight = np.random.rand() < 0.5
            self.go_diag_up = not self.go_straight
            self.go_diag_down = False
            if self.go_diag_up:
                self.x, self.y = 0, 25

        elif lane == "top":
            self.x, self.y = 50, 30
            self.direction = -1
            self.light = self.model.lights[1]
            self.stop_x = 30
            self.go_straight = np.random.rand() < 0.5
            self.go_diag_up = not self.go_straight
            self.go_diag_down = False

            # Configurar punto objetivo para diagonal (38, 36.5)
            if self.go_diag_up:
                self.x, self.y = 50, 33
                self.stop_x = 33.5
                self.diagonal_target_x = 50
                self.diagonal_target_y = 50

        elif lane == "topleft":
            self.x, self.y = 10, 50
            self.direction = 1
            self.light = self.model.lights[2]
            self.stop_y = 36.7
            self.vertical_phase = True
            self.go_straight = False
            self.go_diag_up = False
            self.go_diag_down = False

        elif lane == "topleftright":
            self.x, self.y = 10, 50
            self.direction = 1
            self.light = self.model.lights[2]
            self.stop_y = 36.7
            self.vertical_phase = True
            self.go_straight = False
            self.go_diag_up = True   # activará una leve diagonal luego de la fase vertical
            self.go_diag_down = False

        elif lane == "topright":
            self.x, self.y = 10, 50
            self.direction = 1
            self.direction2 = -1
            self.light = self.model.lights[2]
            self.stop_y = 36.7
            self.vertical_phase = True
            self.go_straight = True
            self.go_diag_up = False
            self.go_diag_down = False
        elif lane == "custom_south":
        # No necesita presets: ya viene con go_south, stop_y, integrate_y/dir, etc.
            pass

        else:
            raise ValueError("Lane desconocida")

    def step(self):
        if self.arrived:
            return

        dt = self.model.p.dt
        prev_x, prev_y = self.x, self.y

        # Vehículos que giran al norte
        if self.go_north and not self.turning_north:
            if self.direction == 1:
                distance_to_stop = (self.stop_x if self.stop_x is not None else self.x)*1.7 - self.x
            else:
                distance_to_stop = self.x - (self.stop_x if self.stop_x is not None else self.x)

            if distance_to_stop > 0:
                move = min(self.speed * dt, distance_to_stop)
                self.x += move * self.direction
                if self.light and self.light.state == 'red' and distance_to_stop - move <= 0:
                    self.waiting_for_green = True
                return

            if self.waiting_for_green and self.light and self.light.state == 'red':
                return

            self.turning_north = True

        if self.turning_north:
            HORIZONTAL_STEPS_TARGET = 25

            # Fase 2a: Avanzar solo en horizontal por unos pasos
            if self.horizontal_turn_steps < HORIZONTAL_STEPS_TARGET:
                self.x += self.direction * self.speed * dt
                self.horizontal_turn_steps += 1 # Aumentamos el contador

            # Fase 2b: Una vez completado el tramo horizontal, empezar la diagonal
            else:
                dx_scale = getattr(self.model.p, 'turn_dx_scale_diag_dir1', 0.2) if self.direction == 1 else 1.0
                self.x += self.direction * self.speed * dt * dx_scale
                self.y += self.speed * dt # <-- El movimiento en 'y' solo empieza aquí
            self.check_light_pass(prev_x, prev_y)
            # Comprobar si ha llegado al final
            if self.y >= self.model.p.road_length:
                self.arrived = True
            return

        # --- INTEGRACIÓN POR VEHÍCULO (hacia el sur) ---
        if self.go_south:
            diag_norm = 1.05

            # 1) Semáforo 3 (y = stop_y): respetar mientras no se libere el cruce
            if (not self.cleared_stop3) and (self.stop_y is not None):
                distance_to_stop = self.y - self.stop_y

                if distance_to_stop > 0:
                    move_y = min(self.speed * dt, distance_to_stop)

                    # Si llega justo a la línea y está rojo -> clava en la línea
                    if self.light and self.light.state == 'red' and distance_to_stop - move_y <= 0:
                        self.y = self.stop_y
                        self.waiting_for_green = True
                        self.check_light_pass(prev_x, prev_y)
                        return

                    # Acercarse (con leve movimiento diagonal en x)
                    self.y -= move_y
                    if self.direction in (-1, 1):
                        self.x += self.direction * self.speed * dt * diag_norm
                    self.check_light_pass(prev_x, prev_y)
                    return
                else:
                    # Ya en/por debajo de la línea
                    if self.light and self.light.state == 'red' and self.waiting_for_green:
                        self.y = self.stop_y
                        return
                    # Cruzó: marcar liberado
                    self.waiting_for_green = False
                    self.cleared_stop3 = True

            # 2) Integración en X según integrate_dir
            if self.integrate_dir == -1:
                if self.integrate_y is None:
                    self.go_south = False
                    if self.stop_y is not None:
                        self.y = max(self.y, self.stop_y)
                    self.direction = -1
                    self.light = None
                    self.stop_x = 0
                    self.check_light_pass(prev_x, prev_y)
                    return
                else:
                    d2 = self.y - self.integrate_y
                    if d2 > 0:
                        move_y = min(self.speed * dt, d2)
                        self.y -= move_y
                        if self.direction in (-1, 1):
                            self.x += self.direction * self.speed * dt * 1.05
                        if self.y <= 0 or self.x <= 0 or self.x >= self.model.p.size:
                            self.arrived = True
                        self.check_light_pass(prev_x, prev_y)
                        return
                    else:
                        self.go_south = False
                        self.y = self.integrate_y
                        self.direction = -1
                        self.light = None
                        self.stop_x = 0
                        self.check_light_pass(prev_x, prev_y)
                        return

            elif self.integrate_dir == 1:
                if self.integrate_y is None:
                    self.go_south = False
                    if self.stop_y is not None:
                        self.y = max(self.y, self.stop_y)
                    self.direction = 1
                    self.light = None
                    self.stop_x = self.model.p.size
                    self.check_light_pass(prev_x, prev_y)
                    return
                else:
                    d2 = self.y - self.integrate_y
                    if d2 > 0:
                        move_y = min(self.speed * dt, d2)
                        self.y -= move_y
                        if self.direction in (-1, 1):
                            self.x += self.direction * self.speed * dt * 1.05
                        if self.y <= 0 or self.x <= 0 or self.x >= self.model.p.size:
                            self.arrived = True
                        self.check_light_pass(prev_x, prev_y)
                        return
                    else:
                        self.go_south = False
                        self.y = self.integrate_y
                        self.direction = 1
                        self.light = None
                        self.stop_x = self.model.p.size
                        self.check_light_pass(prev_x, prev_y)
                        return

            # 3) Sin integración: seguir bajando normal tras cruzar el semáforo 3
            self.y -= self.speed * dt
            if self.direction in (-1, 1):
                self.x += self.direction * self.speed * dt * diag_norm
            if self.y <= 0 or self.x <= 0 or self.x >= self.model.p.size:
                self.arrived = True
            self.check_light_pass(prev_x, prev_y)
            return

        # Vehículos rectos en horizontal (parada en stop_x) - SOLO para movimiento recto
        if (self.stop_x is not None and self.direction in (1, -1) and
            not (self.go_diag_up and self.lane == "top" and self.diagonal_target_x is not None)):
            if self.direction == 1:
                distance_to_stop = self.stop_x - self.x
            else:
                distance_to_stop = self.x - self.stop_x

            if distance_to_stop > 0:
                move = min(self.speed * dt, distance_to_stop)
                self.x += move * self.direction
                if self.light and self.light.state != 'green' and distance_to_stop - move <= 0:
                    self.waiting_for_green = True
                    return
            else:
                if self.light and self.light.state!= 'green' and self.waiting_for_green:
                    return
                else:
                    self.waiting_for_green = False
                    # Solo mover horizontalmente si no va en diagonal específica
                    if not (self.go_diag_up and self.lane == "top" and self.diagonal_target_x is not None):
                        self.x += self.speed * dt * self.direction

        # ======================
        # Carriles bottom/top
        # ======================
        if self.lane in ["bottom", "top"]:
            if not self.passed_light:
                dist = self.stop_x - self.x if self.direction == 1 else self.x - self.stop_x
                if dist > 0:
                    move = min(self.speed * dt, dist)
                    self.x += move * self.direction
                    return
                else:
                    if self.light and self.light.state != 'green':
                        self.waiting_for_green = True
                        return
                    else:
                        self.waiting_for_green = False
                        self.passed_light = True

            # Movimiento después del semáforo
            if self.go_straight:
                self.x += self.speed * dt * self.direction
            elif self.go_diag_up and self.lane == "top":
                # Movimiento diagonal hacia punto específico (38, 36.5) para carril top
                if not self.reached_diagonal_target and self.diagonal_target_x is not None:
                    # Calcular distancia al objetivo
                    dx = self.diagonal_target_x - self.x
                    dy = self.diagonal_target_y - self.y
                    distance = (dx**2 + dy**2)**0.5

                    if distance > 0.5:  # Tolerancia para llegar al objetivo
                        # Normalizar el vector de movimiento
                        move_x = (dx / distance) * self.speed * dt
                        move_y = (dy / distance) * self.speed * dt

                        self.x += move_x
                        self.y += move_y
                    else:
                        # Llegó al objetivo, marcar como alcanzado
                        self.x = self.diagonal_target_x
                        self.y = self.diagonal_target_y
                        self.reached_diagonal_target = True
                        self.arrived = True  # O continuar con otro comportamiento
                else:
                    # Comportamiento original si no hay objetivo específico o ya lo alcanzó
                    self.x += self.speed * dt * self.direction
                    self.y += self.speed * dt
            elif self.go_diag_up and self.lane == "bottom":
                # Comportamiento original para carril bottom

                if not self.reached_diagonal_target and self.diagonal_target_x is not None:
                    #calcular distancia al objetivo
                    dx = self.diagonal_target_x - self.x
                    dy = self.diagonal_target_y - self.y
                    distance = (dx**2 + dy**2)**0.5

                    if distance > 0.5:
                        move_x = (dx/distance) * self.speed * dt
                        move_y = (dy/distance) * self.speed * dt

                        self.x += move_x
                        self.y += move_y
                    else:
                        self.x = self.diagonal_target_x
                        self.y = self.diagonal_target_y
                        self.reached_diagonal_target = True
                        self.arrived = True
                        # Llegó al objetivo, marcar como alcanzado
                else:
                    # Comportamiento original si no hay objetivo específico o ya lo alcanzó
                    self.x += self.speed * dt * self.direction * 0.05
                    self.y += self.speed * dt
            elif self.go_diag_down:
                self.x += self.speed * dt * self.direction
                self.y -= self.speed * dt

        # ======================
        # Lane topleft
        # ======================
        elif self.lane == "topleft":
            if self.vertical_phase:
                if self.y > (self.stop_y if self.stop_y is not None else self.y):
                    self.y -= self.speed * dt
                    self.x += self.speed * dt * self.direction
                else:
                    if self.light and self.light.state != 'green':
                        self.waiting_for_green = True
                        return
                    else:
                        self.vertical_phase = False
                        self.diagonal_phase = True
                        self.diagonal_steps = 0
            elif self.diagonal_phase:
                self.x += self.speed * dt
                self.y -= self.speed * dt
                self.diagonal_steps += 1
                if self.diagonal_steps >= 10:
                    self.diagonal_phase = False
                    self.turning_right = True
            elif self.turning_right:
                self.x += self.speed * dt
                if self.x >= self.model.p.size:
                    self.arrived = True

        elif self.lane == "topleftright":
            if self.vertical_phase:
                if self.y > (self.stop_y if self.stop_y is not None else self.y):
                    self.y -= self.speed * dt * 1.12
                    self.x += self.speed * dt * self.direction
                else:
                    if self.light and self.light.state != 'green':
                        self.waiting_for_green = True
                        return
                    else:
                        self.vertical_phase = False
                        self.diagonal_phase = True
                        self.diagonal_steps = 0
            elif self.diagonal_phase:
                self.x += (self.speed * dt) * 0.63
                self.y -= (self.speed * dt) * 0.1
                self.diagonal_steps += 0.5
                if self.diagonal_steps >= 10:
                    self.diagonal_phase = False
                    self.go_diag_up = True  # activar fase diagonal-up
            elif self.go_diag_up:
                self.x += self.speed * dt * self.direction
                self.y += self.speed * dt

        elif self.lane == "topright":
            if self.vertical_phase:
                if self.y > (self.stop_y if self.stop_y is not None else self.y):
                    self.y -= self.speed * dt
                    self.x += self.speed * dt * self.direction
                else:
                    if self.light and self.light.state != 'green':
                        self.waiting_for_green = True
                        return
                    else:
                        self.vertical_phase = False
                        self.diagonal_phase = True
                        self.diagonal_steps = 0
            elif self.diagonal_phase:
                self.x += self.speed * dt
                self.y -= self.speed * dt
                self.diagonal_steps += 1
                if self.diagonal_steps >= 3:
                    self.diagonal_phase = False
                    self.go_straight = True
            elif self.go_diag_up:
                self.x += self.speed * dt * self.direction
                self.y += self.speed * dt
            elif self.go_straight:
                self.x += self.speed * dt * self.direction2
        # Verificar si pasó el semáforo en verde
        self.check_light_pass(prev_x, prev_y)
        # Verificar límites del modelo
        if (self.x <= 0 or self.x >= self.model.p.size or
            self.y <= 0 or self.y >= self.model.p.road_length):
            self.arrived = True

    def check_light_pass(self, prev_x, prev_y):
      if not self.light or self.counted_pass or self.light.state != 'green':
          return

      eps = 1e-2
      passed = False

      if self.lane in ["bottom", "top"] and self.stop_x is not None:
          if self.direction == 1:
              passed = (prev_x <= self.stop_x <= self.x + eps)
          else:
              passed = (prev_x >= self.stop_x >= self.x - eps)

      elif self.lane in ["topleft", "topleftright", "topright"] and self.stop_y is not None:
          passed = (prev_y >= self.stop_y >= self.y - eps)

      elif self.lane == "custom_south" and self.stop_y is not None:
          passed = (prev_y >= self.stop_y >= self.y - eps)

      if passed:
          self.light.vehicles_passed += 1
          self.counted_pass = True

class Sensor(ap.Agent):
    def setup(self, x, y, radius):
        self.x = x
        self.y = y
        self.r = radius
        self.value = 0  # 0 = no hay vehículo, 1 = hay vehículo

    def read(self, vehicles):
        self.value = 1 if any(
            (getattr(v, 'x', None) is not None) and
            (getattr(v, 'y', None) is not None) and
            (not v.arrived) and ((v.x - self.x)**2 + (v.y - self.y)**2 <= self.r**2)
            for v in vehicles
        ) else 0

class TrafficController:
    def __init__(self, lights, sensor_Ah, sensor_Nog):
        self.lights = lights
        self.sensor_Ah = sensor_Ah
        self.sensor_Nog = sensor_Nog

        self.timer = 0.0
        self.state_duration = 25

        # Flags para control de sensores
        self.flag_semaforo_Ah = False
        self.flag_semaforo_Nog = False

        self.in_yellow = False
        self.current_green_idx = None
        self.yellow_main = 3      # S0/S1
        self.yellow_sensor = 3    # S2/S3

        # Secuencia de semáforos a ejecutar
        self.sequence = []
        self.current_step = 0

        # Inicializar secuencia
        self.build_sequence()
        self.execute_current_step()

    def step(self, dt):
        self.timer += dt
        if self.timer >= self.state_duration:
            self.timer = 0.0
            # Si veníamos de verde, pasa a amarillo del mismo semáforo
            if not self.in_yellow and self.current_step < len(self.sequence):
                idx = self.sequence[self.current_step]
                for l in self.lights:
                    l.state = "red"
                self.lights[idx].state = "yellow"
                self.in_yellow = True
                self.state_duration = self.yellow_main if idx in (0, 1) else self.yellow_sensor
                return
            # Si ya cumplió el amarillo, avanza al siguiente paso
            self.in_yellow = False
            self.next_step()

    def turn_on(self, coord_idx):
        """Apaga todos los semáforos y prende solo el especificado"""
        for light in self.lights:
            light.state = "red"
        self.lights[coord_idx].state = "green"

    def build_sequence(self):
        """Construye la secuencia completa según el pseudocódigo"""

        self.sequence = []

        # Paso 1: prender semáforo 1 (S0)
        self.sequence.append(0)

        # Paso 2: if(sensorAh = 1) prender + flag = true
        if self.sensor_Ah.value == 1:
            self.sequence.append(2)  # Ahuehuetes
            self.flag_semaforo_Ah = True

        # Paso 3: if(sensorNog = 1) prender + flag = true
        if self.sensor_Nog.value == 1:
            self.sequence.append(3)  # Nogales
            self.flag_semaforo_Nog = True

        # Paso 4: prender semáforo 2 (S1)
        self.sequence.append(1)

        self.current_step = 0
        self.timer = 0.0
        self.execute_current_step()


    def execute_current_step(self):
        if self.current_step < len(self.sequence):
            light_index = self.sequence[self.current_step]
            # prender solo el indicado
            for l in self.lights:
                l.state = "red"
            self.lights[light_index].state = "green"

            # guarda quién está en verde y duración
            self.current_green_idx = light_index
            self.in_yellow = False
            self.state_duration = 25 if light_index in (0, 1) else 13
        else:
            self.restart_cycle()

    def next_step(self):
        """Avanza y, si toca, inserta S2/S3 respetando flags y sensores."""
        just_finished = self.sequence[self.current_step] if self.current_step < len(self.sequence) else None

        # Pasos 2–3 (después de S0): insertar antes de S1, solo si aún no atendidos
        if just_finished == 0:
            insert_pos = self.current_step + 1
            if (not self.flag_semaforo_Ah) and (self.sensor_Ah.value == 1):
                self.sequence.insert(insert_pos, 2)
                self.flag_semaforo_Ah = True
                insert_pos += 1
            if (not self.flag_semaforo_Nog) and (self.sensor_Nog.value == 1):
                self.sequence.insert(insert_pos, 3)
                self.flag_semaforo_Nog = True

        # Pasos 5–6 (después de S1): añadir al final lo que falte atender
        if just_finished == 1:
            if (not self.flag_semaforo_Ah) and (self.sensor_Ah.value == 1):
                self.sequence.append(2)
                self.flag_semaforo_Ah = True
            if (not self.flag_semaforo_Nog) and (self.sensor_Nog.value == 1):
                self.sequence.append(3)
                self.flag_semaforo_Nog = True
        # avanzar
        self.current_step += 1
        if self.current_step >= len(self.sequence):
            self.restart_cycle()
        else:
            self.execute_current_step()
    def restart_cycle(self):
        """Reinicia el ciclo completo"""
        # Resetear flags
        self.flag_semaforo_Ah = False
        self.flag_semaforo_Nog = False

        # Reiniciar secuencia
        self.current_step = 0
        self.build_sequence()
        self.execute_current_step()

    def get_debug_info(self):
        """Devuelve información de debug"""
        return {
            "sequence": self.sequence,
            "current_step": self.current_step,
            "timer": round(self.timer, 1),
            "duration": self.state_duration,
            "sensor_Ah": self.sensor_Ah.value,
            "sensor_Nog": self.sensor_Nog.value,
            "flag_Ah": self.flag_semaforo_Ah,
            "flag_Nog": self.flag_semaforo_Nog,
            "current_light": self.sequence[self.current_step] if self.current_step < len(self.sequence) else "RESTART"
        }

class RoadModel(ap.Model):
    def setup(self):
        # 4 semáforos
        self.lights = [ap.AgentList(self, 1, TrafficLight)[0] for _ in range(4)]

        # Inicializar todos en rojo
        for l in self.lights:
            l.state = "red"

        self.vehicles = []
        self.stopped_history = []

        # Sensores
        self.sensor_Ah = ap.AgentList(self, 1, Sensor, x=23.2, y=37.5, radius=2.0)[0]
        self.sensor_Nog = ap.AgentList(self, 1, Sensor, x=32.0, y=37.5, radius=2.0)[0]

        # Traffic Controller
        self.traffic_controller = TrafficController(self.lights, self.sensor_Ah, self.sensor_Nog)

    def step(self):
        dt = self.p.dt

        # Calcular vehículos detenidos
        stopped = sum(1 for v in self.vehicles if hasattr(v, 'speed') and v.speed == 0)
        self.stopped_history.append(stopped)

        # Llegada de vehículos (fiorella y oscar)
        arrivals = np.random.poisson(self.p.arrival_rate)
        for _ in range(arrivals):
            lane = np.random.choice(["bottom", "top"])
            v = ap.AgentList(self, 1, Vehicle, lane=lane, speed=self.p.speed)[0]
            self.vehicles.append(v)
        arrivals = np.random.poisson(self.p.arrival_rate * 0.3)
        for _ in range(arrivals):
            lane = np.random.choice([ "topleft", "topleftright", "topright"])
            v = ap.AgentList(self, 1, Vehicle, lane=lane, speed=self.p.speed)[0]
            self.vehicles.append(v)

        # Selector de vehículos (Abel) - segunda fuente de llegadas
        arrivals = np.random.poisson(self.p.arrival_rate)
        for _ in range(arrivals):
            r = np.random.rand()
            r2 = np.random.rand()
            integ_y = 34 if r2 < 1/3 else 26
            integ_dir = -1 if r2 < 1/3 else 1

            if r < 0.25:
                v = ap.AgentList(
                    self, 1, Vehicle,
                    x=46, y=self.p.size, direction=-1,
                    light=self.lights[3], stop_y=self.p.nogales_stop_y,
                    go_south=True, speed=self.p.speed,
                    stop_x=None,
                    integrate_y=integ_y, integrate_dir=integ_dir,
                    lane='custom_south'  # etiqueta auxiliar, no usada en lógica
                )[0]
                self.vehicles.append(v)

        # Sensores leen
        self.sensor_Ah.read(self.vehicles)
        self.sensor_Nog.read(self.vehicles)
        # Traffic Controller
        self.traffic_controller.step(dt)

        # --- Cola por carril (car-following simple) ---
        gap = getattr(self.p, 'queue_gap', 2.0)
        gap_bottom = getattr(self.p, 'queue_gap_bottom', gap)
        gap_topg = getattr(self.p, 'queue_gap_bottom', gap)
        gap_cs  = getattr(self.p, 'queue_gap_custom_south', gap)
        band_cs = getattr(self.p, 'custom_south_band', 1.5)
        band_topg = getattr(self.p, 'topgroup_band', 1.5)

        # Agrupa los vehículos por carril
        groups = {}
        for v in self.vehicles:
            if v.arrived:
                continue
            if v.lane == 'bottom':
                if not v.passed_light:
                    groups.setdefault('bottom', []).append(v)
            elif v.lane == 'top':
                if not v.passed_light:
                    groups.setdefault('top', []).append(v)
            elif v.lane in ('topleft', 'topleftright', 'topright'):
                if v.vertical_phase:
                    groups.setdefault('top_group', []).append(v)
            elif v.lane == 'custom_south':
                if not v.cleared_stop3:
                    groups.setdefault(v.lane, []).append(v)

        def progress(v):
            if v.lane == 'bottom':
                return v.x
            if v.lane == 'top':
                return -v.x
            return -v.y

        blocked = set()
        for lane, vecs in groups.items():
            vecs.sort(key=progress, reverse=True)

            if lane in ('bottom', 'top'):
                lane_gap = gap_bottom if lane == 'bottom' else gap
                for lead, foll in zip(vecs, vecs[1:]):
                    if lead.direction == 1:
                        if (lead.x - foll.x) < lane_gap:
                            blocked.add(foll)
                    else:
                        if (foll.x - lead.x) < lane_gap:
                            blocked.add(foll)
                continue

            if lane == 'top_group':
                for lead, foll in zip(vecs, vecs[1:]):
                    same_corridor = abs(foll.x - lead.x) <= band_topg
                    if same_corridor and (foll.y - lead.y) < gap_topg:
                        blocked.add(foll)
                continue

            if lane == 'custom_south':
                for lead, foll in zip(vecs, vecs[1:]):
                    same_corridor = abs(foll.x - lead.x) <= band_cs
                    if same_corridor and (foll.y - lead.y) < gap_cs:
                        blocked.add(foll)
                continue

        # Pre-alto S1 (top) para no "chocar" en la diagonal
        hold_x = getattr(self.p, 's1_hold_x', 38.0)
        if self.lights[1].state == 'red' and 'top' in groups and groups['top']:
            vecs_top = sorted(groups['top'], key=progress, reverse=True)
            leader = vecs_top[0]
            if leader.x <= hold_x + gap:
                blocked.add(leader)

        # Aplica el "espera": congela velocidad SOLO este tick
        for v in self.vehicles:
            v._orig_speed = v.speed
            if v in blocked:
                v.speed = 0.0

        # Actualizar vehículos
        for v in self.vehicles:
            v.step()
        
        # Restaurar velocidad original DESPUÉS de mover
        for v in self.vehicles:
            if hasattr(v, '_orig_speed'):
                v.speed = v._orig_speed
                del v._orig_speed

        # Eliminar los que salieron
        self.vehicles = [v for v in self.vehicles if not v.arrived]

    def get_state(self):
        scale = 10
        
        """Convert the model state to Unity-compatible format"""
        cars_data = []
        for v in self.vehicles:
            if not v.arrived:
                cars_data.append({
                    'car_id': v.car_id,
                    'position': [v.x * scale, 0, v.y * scale],
                    'stopped': v.waiting_for_green or (hasattr(v, 'speed') and v.speed == 0),
                    'lane': v.lane,
                    'direction': getattr(v, 'direction', 1),
                    'turning': getattr(v, 'turning_north', False) or getattr(v, 'turning_right', False),
                    'rotation': self._calculate_rotation(v),
                    
                })
                print([v.x , 0, v.y ])

        # Format compatible with your Unity script structure
        return {
            'cars': cars_data,
            'lights': {
                'light_0': {
                    'state': self.lights[0].state,
                    'timer': round(self.lights[0]._timer, 1),
                    'vehicles_passed': self.lights[0].vehicles_passed
                },
                'light_1': {
                    'state': self.lights[1].state,
                    'timer': round(self.lights[1]._timer, 1),
                    'vehicles_passed': self.lights[1].vehicles_passed
                },
                'light_2': {
                    'state': self.lights[2].state,
                    'timer': round(self.lights[2]._timer, 1),
                    'vehicles_passed': self.lights[2].vehicles_passed
                },
                'light_3': {
                    'state': self.lights[3].state,
                    'timer': round(self.lights[3]._timer, 1),
                    'vehicles_passed': self.lights[3].vehicles_passed
                }
            },
            'sensors': {
                'sensor_Ah': {
                    'value': self.sensor_Ah.value,
                    'x': self.sensor_Ah.x * scale,
                    'y': self.sensor_Ah.y * scale
                },
                'sensor_Nog': {
                    'value': self.sensor_Nog.value,
                    'x': self.sensor_Nog.x * scale,
                    'y': self.sensor_Nog.y * scale
                }
            },
            'debug': self.traffic_controller.get_debug_info()
        }

    def _calculate_rotation(self, vehicle):
        """Calculate rotation based on vehicle movement direction and lane"""
        if hasattr(vehicle, 'turning_north') and vehicle.turning_north:
            return 45.0  # Diagonal up
        elif hasattr(vehicle, 'turning_right') and vehicle.turning_right:
            return 0.0   # Right
        elif vehicle.lane == "bottom":
            if vehicle.go_diag_up:
                return 45.0
            else:
                return 0.0  # Right
        elif vehicle.lane == "top":
            if vehicle.go_diag_up:
                return 135.0
            else:
                return 180.0  # Left
        elif vehicle.lane in ["topleft", "topleftright", "topright"]:
            if vehicle.vertical_phase:
                return 270.0  # Down
            elif vehicle.diagonal_phase:
                return 315.0  # Diagonal down-right
            else:
                return 0.0    # Right
        elif vehicle.lane == "custom_south":
            return 270.0  # Down
        else:
            return 0.0

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
        print(f"Logic Server listening on {self.host}:{self.port}")

        try:
            self.client_conn, addr = self.sock.accept()
            print(f"Unity connected from {addr}")

            while self.running:
                self.model.step()
                state = self.model.get_state()
                message = json.dumps(state).encode('utf-8')
                self.client_conn.sendall(message + b'\n')
                time.sleep(0.05)  # 20 FPS
        except Exception as e:
            print(f"Server error: {e}")
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
    # Initialize Vehicle ID counter
    Vehicle._id_counter = 0
    
    # Parameters for the model
    parameters = {
        'dt': 1,
        'light_period': 15.0,
        'speed': 1.0,
        'light_position': 25,
        'nogales_stop_y': 36.0,
        'road_length': 56,
        'size': 50,
        'steps': 250,
        'arrival_rate': 0.1,
        's1_hold_x': 37.0,
        'queue_gap_custom_south': 3.0,
        'custom_south_band': 1.5,
        'topgroup_band': 2.0,
        's3_hold_y': 39.0,
        'turn_dx_scale_dir1': 0.2,
        'turn_hsteps_dir1': 8
    }
    
    # Create and setup model
    model = RoadModel(parameters)
    model.setup()
    
    # Start server
    server = SocketServer(model)
    server.start()
    
    try:
        print("Logic server running... Press Ctrl+C to stop")
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("Shutting down server...")
        server.stop()
        server.join()