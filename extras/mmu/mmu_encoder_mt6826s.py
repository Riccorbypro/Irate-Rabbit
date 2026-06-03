# Happy Hare MMU Software
# MT6826S-backed encoder wrapper for Happy Hare's mmu encoder API
#
# Copyright (C) 2022-2026  moggieuk#6538 (discord)
#                          moggieuk@hotmail.com
#
# This file may be distributed under the terms of the GNU GPLv3 license.
#
import logging


RAW_ANGLE_TICKS = 32768.0
RAW_ANGLE_HALF_TURN = RAW_ANGLE_TICKS / 2.0


class MmuEncoderMt6826s:
    CHECK_MOVEMENT_TIMEOUT = 0.250

    RUNOUT_DISABLED = 0
    RUNOUT_STATIC = 1
    RUNOUT_AUTOMATIC = 2

    def __init__(self, config):
        self.name = config.get_name().split()[-1]
        self.printer = config.get_printer()
        self.reactor = self.printer.get_reactor()
        self.gcode = self.printer.lookup_object('gcode')
        self.encoder_angle = config.get('encoder_angle')
        self.angle_sensor = self.printer.lookup_object('angle %s' % self.encoder_angle, None)
        if self.angle_sensor is None:
            raise config.error("Missing [angle %s] section referenced by [mmu_encoder_mt6826s %s]"
                               % (self.encoder_angle, self.name))

        rotation_distance = config.getfloat('rotation_distance', 4.0, above=0.)
        self.set_resolution(config.getfloat('encoder_resolution', rotation_distance / RAW_ANGLE_TICKS, above=0.))
        self.poll_interval = config.getfloat('poll_interval', 0.005, above=0.)
        self.use_bulk_angle_stream = bool(config.getint('use_bulk_angle_stream', 0, minval=0, maxval=1))
        self.encoder_reversed = config.getboolean('encoder_reversed', False)

        self._logger = None
        self._counts = 0.
        self._movement_counts = 0.
        self._last_angle = None
        self._last_raw_angle = None
        self._last_time = None
        self._movement = False
        self._angle_client_registered = False
        self._angle_batches = 0
        self._angle_empty_batches = 0
        self._angle_samples = 0
        self._angle_errors = 0
        self._angle_last_batch_delta = 0.
        self._angle_last_batch_samples = 0
        self._angle_last_batch_time = None
        self._angle_last_position_offset = None
        self._last_signed_delta = 0.
        self._angle_logged_batches = 0
        self._angle_last_log_systime = 0.
        self._poll_timer = None
        self._poll_reads = 0
        self._poll_errors = 0
        self._poll_crc_errors = 0
        self._poll_last_status = None
        self._poll_logged_reads = 0
        self._poll_last_log_systime = 0.

        self.extruder_name = config.get('extruder', 'extruder')
        self.desired_headroom = config.getfloat('desired_headroom', 6., above=0.)
        self.average_samples = config.getint('average_samples', 4, minval=1)
        self.next_calibration_point = self.calibration_length = config.getfloat('calibration_length', 10000., minval=50.)
        self.detection_length = self.min_headroom = config.getfloat('detection_length', 10., above=2.)
        self.event_delay = config.getfloat('event_delay', 2., above=0.)
        self.pause_delay = config.getfloat('pause_delay', 0, above=0.)
        self.runout_gcode = '__MMU_ENCODER_RUNOUT'
        self.insert_gcode = '__MMU_ENCODER_INSERT'
        self._enabled = True
        self.min_event_systime = self.reactor.NEVER
        self.extruder = None
        self.filament_detected = False
        self.detection_mode = self.RUNOUT_STATIC
        self.last_extruder_pos = self.filament_runout_pos = 0.
        self.filament_runout_pos = self.min_headroom = self.detection_length

        self.flowrate_last_encoder_pos = 0.
        self.extrusion_flowrate = 0.
        self.samples = []
        self.flowrate_samples = config.getint('flowrate_samples', 20, minval=5)

        self.printer.register_event_handler('klippy:ready', self._handle_ready)
        self.printer.register_event_handler('klippy:connect', self._handle_connect)
        self.printer.register_event_handler('idle_timeout:printing', self._handle_printing)
        self.printer.register_event_handler('idle_timeout:ready', self._handle_not_printing)
        self.printer.register_event_handler('idle_timeout:idle', self._handle_not_printing)

    def _register_angle_client(self):
        if not self._angle_client_registered:
            self.angle_sensor.add_client(self._angle_batch_cb)
            self._angle_client_registered = True
            self._log_encoder("MT6826S encoder '%s' registered angle client '%s' (15-bit angle scale, %.0f ticks/rev)"
                              % (self.name, self.encoder_angle, RAW_ANGLE_TICKS))

    def _register_angle_client_event(self, eventtime):
        self._register_angle_client()
        return self.reactor.NEVER

    def _log_encoder(self, msg):
        if self._logger:
            self._logger(msg)
        else:
            logging.info("MMU: %s" % msg)

    def _angle_batch_cb(self, msg):
        samples = msg.get('data', [])
        self._angle_batches += 1
        self._angle_last_batch_samples = len(samples)
        self._angle_errors += msg.get('errors', 0)
        self._angle_last_position_offset = msg.get('position_offset', None)
        if not samples:
            self._angle_empty_batches += 1
            if self._angle_empty_batches <= 3:
                self._log_encoder("MT6826S encoder '%s' received empty angle batch #%d (errors=%d)"
                                  % (self.name, self._angle_batches, msg.get('errors', 0)))
            return True

        batch_delta = 0.
        first_angle = samples[0][1]
        first_raw_angle = first_angle % RAW_ANGLE_TICKS
        for sample_time, angle in samples:
            raw_angle = angle % RAW_ANGLE_TICKS
            batch_delta += self._record_raw_angle(raw_angle, sample_time, angle)
        self._angle_samples += len(samples)
        self._angle_last_batch_delta = batch_delta
        self._angle_last_batch_time = samples[-1][0]
        self._log_angle_batch(samples, first_angle, first_raw_angle, batch_delta, msg.get('errors', 0))
        return True

    def _record_raw_angle(self, raw_angle, sample_time, angle=None):
        if self._last_raw_angle is None:
            self._last_angle = raw_angle if angle is None else angle
            self._last_raw_angle = raw_angle
            self._last_time = sample_time
            return 0.
        delta = raw_angle - self._last_raw_angle
        if delta > RAW_ANGLE_HALF_TURN:
            delta -= RAW_ANGLE_TICKS
        elif delta < -RAW_ANGLE_HALF_TURN:
            delta += RAW_ANGLE_TICKS
        if self.encoder_reversed:
            delta = -delta
        abs_delta = abs(delta)
        if abs_delta:
            self._counts += delta
            self._movement_counts += abs_delta
            self._last_signed_delta = delta
            self._movement = True
        self._last_angle = raw_angle if angle is None else angle
        self._last_raw_angle = raw_angle
        self._last_time = sample_time
        return abs_delta

    def _read_raw_angle(self):
        sensor_helper = getattr(self.angle_sensor, 'sensor_helper', None)
        if sensor_helper is None or not hasattr(sensor_helper, '_read_angle'):
            raise Exception("MT6826S angle helper does not support direct angle reads")
        angle, status, crc, crc_computed = sensor_helper._read_angle(0x003)
        self._poll_last_status = status
        if crc != crc_computed:
            self._poll_crc_errors += 1
            if self._poll_crc_errors <= 5:
                self._log_encoder("MT6826S encoder '%s' CRC mismatch while polling: got=0x%02x expected=0x%02x angle=%d status=0x%02x"
                                  % (self.name, crc, crc_computed, angle, status))
        return float(angle)

    def _poll_angle_once(self, eventtime):
        raw_angle = self._read_raw_angle()
        delta = self._record_raw_angle(raw_angle, eventtime, raw_angle)
        self._poll_reads += 1
        self._angle_samples += 1
        self._log_poll_sample(raw_angle, delta)
        return delta

    def _poll_angle_event(self, eventtime):
        try:
            self._poll_angle_once(eventtime)
        except Exception as e:
            self._poll_errors += 1
            if self._poll_errors <= 5:
                self._log_encoder("MT6826S encoder '%s' polling read failed: %s" % (self.name, str(e)))
        return self.reactor.monotonic() + self.poll_interval

    def _log_poll_sample(self, raw_angle, delta):
        should_log = False
        if self._poll_logged_reads < 5:
            should_log = True
            self._poll_logged_reads += 1
        elif delta:
            now = self.reactor.monotonic()
            should_log = now - self._poll_last_log_systime > 1.
        if not should_log:
            return
        self._poll_last_log_systime = self.reactor.monotonic()
        self._log_encoder(
            "MT6826S encoder '%s' poll_reads=%d raw=%.1f signed_delta=%.1f movement_delta=%.1f net_counts=%.1f movement_counts=%.1f distance=%.3fmm status=0x%02x crc_errors=%d"
            % (self.name, self._poll_reads, raw_angle, self._last_signed_delta, delta,
               self._counts, self._movement_counts, self.get_distance(),
               self._poll_last_status if self._poll_last_status is not None else 0, self._poll_crc_errors))

    def _log_angle_batch(self, samples, first_angle, first_raw_angle, batch_delta, errors):
        should_log = False
        if self._angle_logged_batches < 5:
            should_log = True
            self._angle_logged_batches += 1
        elif batch_delta:
            now = self.reactor.monotonic()
            should_log = now - self._angle_last_log_systime > 1.
        if not should_log:
            return
        self._angle_last_log_systime = self.reactor.monotonic()
        last_angle = samples[-1][1]
        last_raw_angle = last_angle % RAW_ANGLE_TICKS
        self._log_encoder(
            "MT6826S encoder '%s' batch=%d samples=%d errors=%d first_angle=%.1f last_angle=%.1f "
            "first_raw=%.1f last_raw=%.1f batch_counts=%.1f net_counts=%.1f movement_counts=%.1f distance=%.3fmm"
            % (self.name, self._angle_batches, len(samples), errors, first_angle, last_angle,
               first_raw_angle, last_raw_angle, batch_delta, self._counts, self._movement_counts, self.get_distance()))

    def _handle_connect(self):
        try:
            self.extruder = self.printer.lookup_object(self.extruder_name)
        except Exception:
            pass

    def _handle_ready(self):
        self.min_event_systime = self.reactor.monotonic() + 2.
        self._reset_filament_runout_params()
        self._extruder_pos_update_timer = self.reactor.register_timer(self._extruder_pos_update_event)
        if self.use_bulk_angle_stream:
            self.reactor.register_callback(self._register_angle_client_event, self.reactor.monotonic() + 0.1)
        self._poll_timer = self.reactor.register_timer(self._poll_angle_event, self.reactor.monotonic() + 0.1)
        self._log_encoder("MT6826S encoder '%s' using direct SPI polling at %.4fs intervals%s"
                          % (self.name, self.poll_interval,
                             "%s%s" % (
                                 " with bulk angle stream enabled" if self.use_bulk_angle_stream else "",
                                 " with reversed direction" if self.encoder_reversed else "")))

    def _handle_printing(self, print_time):
        self.reactor.update_timer(self._extruder_pos_update_timer, self.reactor.NOW)

    def _handle_not_printing(self, print_time):
        self.reactor.update_timer(self._extruder_pos_update_timer, self.reactor.NEVER)

    def _get_extruder_pos(self, eventtime=None):
        if eventtime is None:
            eventtime = self.reactor.monotonic()
        print_time = self.printer.lookup_object('mcu').estimated_print_time(eventtime)
        return self.extruder.find_past_position(print_time) if self.extruder else 0.

    def _extruder_pos_update_event(self, eventtime):
        if self._enabled:
            extruder_pos = self._get_extruder_pos(eventtime)
            if self._movement:
                self._movement = False
                self.filament_runout_pos = max(extruder_pos + self.detection_length, self.filament_runout_pos)
            if extruder_pos >= self.next_calibration_point:
                if self.next_calibration_point > 0:
                    self._update_detection_length()
                self.next_calibration_point = extruder_pos + self.calibration_length
            if self.filament_runout_pos - extruder_pos < self.min_headroom:
                self.min_headroom = self.filament_runout_pos - extruder_pos
                if self._logger and self.min_headroom < self.desired_headroom:
                    if self.detection_mode == self.RUNOUT_AUTOMATIC:
                        self._logger("Automatic clog detection: new min_headroom (< %.1fmm desired): %.1fmm" % (self.desired_headroom, self.min_headroom))
                    elif self.detection_mode == self.RUNOUT_STATIC:
                        self._logger("Warning: Only %.1fmm of headroom to clog/runout" % self.min_headroom)
            self._handle_filament_event(extruder_pos < self.filament_runout_pos)

            encoder_pos = self.get_distance()
            if encoder_pos > self.flowrate_last_encoder_pos:
                self._record(encoder_pos, extruder_pos)
                self.flowrate_last_encoder_pos = encoder_pos
            self.last_extruder_pos = extruder_pos
        return eventtime + self.CHECK_MOVEMENT_TIMEOUT

    def _reset_filament_runout_params(self, eventtime=None):
        if eventtime is None:
            eventtime = self.reactor.monotonic()
        self.last_extruder_pos = self._get_extruder_pos(eventtime)
        self.flowrate_last_encoder_pos = self.get_distance()
        self.extrusion_flowrate = 0.
        self.samples = []
        self.filament_runout_pos = self.last_extruder_pos + self.detection_length + self.desired_headroom
        self.next_calibration_point = self.last_extruder_pos + self.calibration_length
        self.min_headroom = self.detection_length

    def _update_detection_length(self, increase_only=False):
        if not self._enabled or self.detection_mode != self.RUNOUT_AUTOMATIC:
            return
        current_detection_length = self.detection_length
        if self.min_headroom < self.desired_headroom:
            extra_length = min((self.desired_headroom - self.min_headroom), self.desired_headroom)
            self.detection_length += extra_length
            if self._logger:
                self._logger("Automatic clog detection: maintaining headroom by adding %.1fmm to detection_length" % extra_length)
        elif not increase_only:
            sample = self.detection_length - (self.min_headroom - self.desired_headroom)
            self.detection_length = ((self.average_samples * self.detection_length) + self.desired_headroom - self.min_headroom) / self.average_samples
            if self._logger:
                self._logger("Automatic clog detection: averaging down detection_length with new %.1fmm measurement" % sample)
        else:
            return

        self.min_headroom = self.detection_length
        self.filament_runout_pos = self.last_extruder_pos + self.detection_length
        if round(self.detection_length, 1) != round(current_detection_length, 1):
            if self._logger:
                self._logger("Automatic clog detection: reset detection_length to %.1fmm" % self.min_headroom)
            self.set_clog_detection_length(self.detection_length)

    def _handle_filament_event(self, filament_detected):
        if self.filament_detected == filament_detected:
            return
        self.filament_detected = filament_detected
        eventtime = self.reactor.monotonic()
        if eventtime < self.min_event_systime or self.detection_mode == self.RUNOUT_DISABLED or not self._enabled:
            return
        is_printing = self.printer.lookup_object("idle_timeout").get_status(eventtime)["state"] == "Printing"
        if filament_detected:
            if not is_printing and self.insert_gcode is not None:
                self.min_event_systime = self.reactor.NEVER
                logging.info("MMU: Encoder Sensor %s: insert event detected, Time %.2f" % (self.name, eventtime))
                self.reactor.register_callback(self._insert_event_handler)
        elif is_printing and self.runout_gcode is not None:
            self.min_event_systime = self.reactor.NEVER
            logging.info("MMU: Encoder Sensor %s: runout event detected, Time %.2f" % (self.name, eventtime))
            self.reactor.register_callback(self._runout_event_handler)

    def _runout_event_handler(self, eventtime):
        pause_resume = self.printer.lookup_object('pause_resume')
        pause_resume.send_pause_command()
        if self.pause_delay:
            self.printer.get_reactor().pause(eventtime + self.pause_delay)
        self._exec_gcode(self.runout_gcode)

    def _insert_event_handler(self, eventtime):
        self._exec_gcode(self.insert_gcode)

    def _exec_gcode(self, command):
        try:
            self.gcode.run_script(command)
        except Exception:
            logging.exception("MMU: Error running mmu encoder handler: `%s`" % command)
        self.min_event_systime = self.reactor.monotonic() + self.event_delay

    def get_clog_detection_length(self):
        return self.detection_length

    def set_clog_detection_length(self, clog_length):
        self.detection_length = max(clog_length, 2.)
        self._reset_filament_runout_params()

    def note_clog_detection_length(self):
        self._update_detection_length()

    def set_mode(self, mode):
        if self.RUNOUT_DISABLED <= mode <= self.RUNOUT_AUTOMATIC:
            self.detection_mode = mode

    def set_extruder(self, extruder_name):
        self.extruder = self.printer.lookup_object(extruder_name)
        if not self.extruder:
            raise self.printer.config.error("Extruder named `%s` not found" % extruder_name)
        self.extruder_name = extruder_name
        self.filament_runout_pos = self.min_headroom = self.detection_length

    def set_logger(self, log):
        self._logger = log

    def enable(self):
        self._reset_filament_runout_params()
        self._enabled = True

    def disable(self):
        self._enabled = False

    def is_enabled(self):
        return self._enabled

    def _record(self, encoder_pos, extruder_pos):
        self.samples.append((encoder_pos, extruder_pos))
        if len(self.samples) > self.flowrate_samples:
            self.samples = self.samples[-self.flowrate_samples:]
        encoder_movement = encoder_pos - self.samples[0][0]
        extruder_movement = extruder_pos - self.samples[0][1]
        new_extrusion_flowrate = (encoder_movement / extruder_movement) if extruder_movement > 0. else 1.
        self.extrusion_flowrate = (self.extrusion_flowrate + new_extrusion_flowrate) / 2.

    def set_resolution(self, resolution):
        self.resolution = resolution

    def get_resolution(self):
        return self.resolution

    def get_counts(self):
        return int(round(self._counts))

    def get_movement_counts(self):
        return int(round(self._movement_counts))

    def get_distance(self):
        return self._counts * self.resolution

    def get_movement_distance(self):
        return self._movement_counts * self.resolution

    def set_distance(self, new_distance):
        self._counts = new_distance / self.resolution
        self._movement_counts = abs(self._counts)

    def reset_counts(self):
        try:
            self._poll_angle_once(self.reactor.monotonic())
        except Exception as e:
            self._log_encoder("MT6826S encoder '%s' could not seed angle during reset: %s" % (self.name, str(e)))
        self._counts = 0.
        self._movement_counts = 0.
        self._movement = False
        self._last_signed_delta = 0.
        self._angle_last_batch_delta = 0.
        self._log_encoder("MT6826S encoder '%s' counts reset (last_raw=%s, batches=%d, samples=%d, poll_reads=%d)"
                          % (self.name, "unknown" if self._last_raw_angle is None else "%.1f" % self._last_raw_angle,
                             self._angle_batches, self._angle_samples, self._poll_reads))

    def get_status(self, eventtime):
        angle_status = self.angle_sensor.get_status(eventtime)
        return {
            'encoder_pos': round(self.get_distance(), 1),
            'encoder_counts': self.get_counts(),
            'encoder_movement_pos': round(self.get_movement_distance(), 1),
            'encoder_movement_counts': self.get_movement_counts(),
            'encoder_resolution': self.get_resolution(),
            'encoder_reversed': self.encoder_reversed,
            'angle_temperature': angle_status.get('temperature', None),
            'angle_client_registered': self._angle_client_registered,
            'angle_batches': self._angle_batches,
            'angle_empty_batches': self._angle_empty_batches,
            'angle_samples': self._angle_samples,
            'angle_errors': self._angle_errors,
            'angle_last': self._last_angle,
            'angle_last_raw': self._last_raw_angle,
            'angle_last_time': self._last_time,
            'angle_last_signed_delta': round(self._last_signed_delta, 3),
            'angle_last_batch_samples': self._angle_last_batch_samples,
            'angle_last_batch_delta': round(self._angle_last_batch_delta, 3),
            'angle_last_position_offset': self._angle_last_position_offset,
            'angle_poll_interval': self.poll_interval,
            'angle_poll_reads': self._poll_reads,
            'angle_poll_errors': self._poll_errors,
            'angle_poll_crc_errors': self._poll_crc_errors,
            'angle_poll_status': self._poll_last_status,
            'detection_length': round(self.detection_length, 1),
            'min_headroom': round(self.min_headroom, 1),
            'headroom': round(self.filament_runout_pos - self.last_extruder_pos, 1),
            'desired_headroom': round(self.desired_headroom, 1),
            'detection_mode': self.detection_mode,
            'enabled': self._enabled,
            'flow_rate': int(round(min(self.extrusion_flowrate, 1.) * 100))
        }


def load_config_prefix(config):
    encoder = MmuEncoderMt6826s(config)

    alias_name = 'mmu_encoder %s' % encoder.name
    printer = config.get_printer()
    if printer.lookup_object(alias_name, None) is None:
        printer.add_object(alias_name, encoder)

    return encoder
