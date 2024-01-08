#!/usr/bin/python3
"""
Supervisory for GSC and MSC by means of a ESP32.
 Packages: pyserial
.
"""

# pylint: disable=C0103,C0301,W0603,C0209

import math
# import socket
import time
# import subprocess
# import sys, getopt, os
from pathlib import Path
from threading import Thread, Lock
import serial
import struct

import gi

gi.require_version("Gtk", "3.0")

from gi.repository import Gtk, GLib

SPEED_MAX = 1200
CURRENT_MAX = 50.0

USB_max = 4  # Maximum number of serial USB devices to search for
S_max = 4  # Maximum number of standard serial devices to search for


class mySerial:
    """
    Class to group serial status vars.
    """
    name: str
    ser: serial.Serial
    dev_list: list
    mut: Lock
    mut_rd: Lock
    builder: Gtk.Builder
    callbacks: list
    debug: bool

    def __init__(self, builder, callbacks):
        self.mut = Lock()
        self.mut_rd = Lock()
        self.name = ''
        self.ser = serial.Serial()
        self.dev_list = []
        self.builder = builder
        self.callbacks = callbacks
        self.debug = False

    def create_list(self):
        """Return a list of serial devices available."""
        # clean serial_list
        self.dev_list = []
        for i in range(USB_max):
            filename = '/dev/ttyUSB' + str(i)
            if Path(filename).exists():
                self.dev_list.append(filename)
        for i in range(S_max):
            filename = '/dev/ttyS' + str(i)
            if Path(filename).exists():
                self.dev_list.append(filename)

    def write(self, s: str):
        """Safe wrapper to serial write function."""
        if self.debug:
            print(s)
        with self.mut:
            if self.ser.isOpen():
                self.ser.write(s.encode('ascii'))
                self.ser.write(b'\r\n')
            else:
                print('ERROR: serial is not openned')

    def read(self):
        """Safe wrapper to serial read function."""
        with self.mut_rd:
            if self.ser.isOpen():
                return self.ser.readline()
            return ''

    def open(self, name_):
        """
        Safe wrapper to serial open function, that verify other files.
        TODO: need to decouple gtk objects from here.
        """
        print('serial_name={}'.format(name_))
        if self.ser.isOpen():
            self.ser.close()
        try:
            if self.debug:
                print(f'INFO: trying to open serial {name_}')
            self.ser = serial.Serial(name_, 115200, timeout=1)
        except serial.SerialException:
            self.ser.close()
            print(f'ERRO: opening serial {name_}')
        self.ser.flush()
        self.ser.dtr = False
        self.ser.rts = False
        version = self.builder.get_object('version')
        version.set_text('Version: ?????')
        serial_status = self.builder.get_object('serial_status')
        if self.ser.isOpen():
            print('Serial {} openned successfuly'.format(name_))
            serial_status.set_from_stock(Gtk.STOCK_APPLY, Gtk.IconSize.LARGE_TOOLBAR)
            print('Serial device changed')
            self.write('version-id')
            self.name = name_
            self.builder.get_object('serial_device').set_sensitive(False)
            self.builder.get_object('connect').set_sensitive(False)
            self.builder.get_object('disconnect').set_sensitive(True)
        else:
            serial_status.set_from_stock(Gtk.STOCK_DIALOG_WARNING, Gtk.IconSize.LARGE_TOOLBAR)

    def reset(self):
        """Reset ESP32 with Reset pin connected to DTR."""
        if self.debug:
            print('INFO: resetting serial')
        self.ser.dtr = True
        print('Serial RESET clicked')
        self.ser.dtr = False

    def disconnect(self):
        """Properly disconect serial flushing data."""
        global ser_name
        if self.debug:
            print('INFO: flushing serial')
        with self.mut:
            with self.mut_rd:
                if self.ser.isOpen():
                    self.ser.flushInput()
                    self.ser.flushOutput()
                    self.ser.cancel_write()
                    self.ser.close()
                    self.name = ''

    def interpret(self):
        """Interpret commands from serial device."""
        while True:
            ll = self.read().strip()
            if len(ll) < 1:
                break
            try:
                lst = ll.decode('utf-8').strip().split(' ')
                f = filter(None, lst)
                lst = list(f)
                if self.debug:
                    print(f"l = {ll.decode('utf-8')}, lst={lst}")
            except UnicodeDecodeError:
                lst = []
            if len(lst) > 0:
                for pair in self.callbacks:
                    if lst[0] == pair[0]:
                        GLib.idle_add(pair[1], lst)

    def read_thread(self):
        """Read serial and calls interpret function."""
        state = False
        # l = b''
        print('INFO: read_thread: waiting for serial')
        while True:
            if self.ser.isOpen():
                self.interpret()
            else:
                # if it needs to access Gtk widgets:
                # GLib.idle_add(serial_status_blink, state)
                state = not state
                print('INFO: read_thread: serial is not open')
                time.sleep(5)


# Global parameters
gsc_vbus_peak = 800.0
gsc_vbus = 0.0
gsc_vbus_max = 740.0
gsc_vbus_target_max = 700.0
gsc_vbus_target_min = 680.0
gsc_vbus_op_min = 660.0
gsc_vbus_crit_min = 630.0
gsc_power = 220e3  # injected active power
gsc_power_nom = 250e3  # Nominal active power to be injected
gsc_power_max = 275e3  # Maximum allowed active power to be injected
gsc_reactive_power = 90e3  # Injected reactive power in VA
gsc_reactive_power_max = 120e3  # Maximum reactive power
gsc_vgrid_nom = 380.0  # grid nominal voltage
gsc_vgrid = 372.0  # Grid measured voltage
gsc_vgrid_max = 480.0  # Maximum grid voltage
gsc_vgrid_imbalance = 0.02  # measured grid voltage imbalance
gsc_i_max_p = 510.0  # maximum peak current
gsc_i_line = 220.0  # grid injected current RMS value
gsc_hs_temp = 105.0  # Heatsink temperature in °C
gsc_status = 0  # status
gsc_adc_raw = False  # if True, GSC must send ADC raw data values
gsc_droop_coef = 0.04  # reactive droop coefficient
gsc_target_fp = 1.0  # target power factor
gsc_vgrid_imbalance = 0.01  # voltage grid imbalance
gsc_fgrid = 59.5  # grid frequency
gsc_fgrid_nom = 60.0  # grid nominal frequency


def rad2rpm(rad):
    """Convert radian value to degree value."""
    return 30 * rad / math.pi


class Handler:
    """Main handler for GTK interface."""
    builder: Gtk.Builder

    def __init__(self, builder):
        self.builder = builder
        entry_mode = self.builder.get_object('msc_mode')
        entry_mode.set_text('Stopped')

    def onDestroy(self, _):
        """Destroy loops."""
        Gtk.main_quit()

    def on_exit_clicked(self, _):
        """Handle exit button."""
        Gtk.main_quit()

    def on_ser_reset_clicked(self, _):
        """Print."""
        myser.reset()

    def on_set_dc_clicked(self, _):
        """Print."""
        print('set_dc clicked')

    def on_serial_device_changed(self, _):
        """Print serial device changed."""
        print('on_serial_device_changed')

    def on_get_version_clicked(self, _):
        """Show version."""
        myser.write('version-id')

    def on_disconnect_clicked(self, _):
        """Act when disconnect button is clecked."""
        myser.disconnect()
        self.builder.get_object('serial_device').set_sensitive(True)
        self.builder.get_object('connect').set_sensitive(True)
        self.builder.get_object('disconnect').set_sensitive(False)
        self.builder.get_object('version').set_text('Version: XXXXX')

    def on_connect_clicked(self, _):
        """Connect to serial when button is clicked."""
        combo = self.builder.get_object('serial_device')
        myser.open(combo.get_active_text())

    def on_gsc_adc_raw_toggled(self, wdg):
        """Enable raw data CAN commando for GSC."""
        global gsc_adc_raw
        if wdg.get_active():
            print('ADC raw active')
            myser.write('send e00010b 0001')
        else:
            print('ADC raw inactive')
            myser.write('send e00010b 0002')

    #
    # MSC
    #
    def on_msc_mode_changed(self, combo):
        """Machine operation mode: if stopped, motor or generator."""
        i = combo.get_active()
        if 0 <= i <= 3:
            myser.write('msc_mode {}'.format(i))
        else:
            print('ERROR: invalid value for msc_mode')

    def on_msc_stop_clicked(self, btn):
        entry_mode = self.builder.get_object('msc_mode')
        entry_mode.set_text('Stopped')
        myser.write('msc_mode 0  # stopped')

    def on_msc_motor_clicked(self, btn):
        entry_mode = self.builder.get_object('msc_mode')
        entry_mode.set_text('Motor')
        myser.write('msc_mode 1  # motor')

    def on_msc_generator_clicked(self, btn):
        entry_mode = self.builder.get_object('msc_mode')
        entry_mode.set_text('Generator')
        myser.write('msc_mode 2  # generator')

    def on_msc_gen_auto_toggled(self, wdg):
        myser.write('msc_gen_auto {}'.format('1' if wdg.get_active() else '0'))


def set_version(ver):
    """Set ESP32 firmware version."""
    version = builder.get_object('version')
    version.set_text('Version: {}'.format(ver[1]))


def str_to_size(s, size):
    while len(s) < size:
        s = '0' + s
    return s


def builder_set(s, label, k=1, n=0, mult=''):
    """Set a GTK label with value from s, no scale."""
    global builder
    val = struct.unpack("!i", bytes.fromhex(str_to_size(s, 8)))[0] * k
    s = f'{{:.{n}f}}{mult}'
    builder.get_object(label).set_text(s.format(val))
    return val


def can_vbus_n_status(s):
    """
    Extract Vbus, Pgrid, Vgrid and status from s.
    """
    global builder, gsc_vbus, gsc_power, gsc_vgrid
    if not len(s) == 16:
        print(f'ERROR: can_vbus_n_status: s={s} has no 16 chars')
    gsc_vbus = struct.unpack("!i", bytes.fromhex(str_to_size(s[0:4], 8)))[0] / 10
    gsc_power = struct.unpack("!i", bytes.fromhex(str_to_size(s[4:8], 8)))[0] * 10
    gsc_vgrid = struct.unpack("!i", bytes.fromhex(str_to_size(s[8:12], 8)))[0] / 10
    gsc_status = struct.unpack("!i", bytes.fromhex(str_to_size(s[12:16], 8)))[0]
    # set interface
    builder.get_object('gsc_vbus')
    builder.get_object('gsc_vbus').set_text("{:.1f}".format(gsc_vbus))
    try:
        builder.get_object('gsc_vbus_level').set_value(gsc_vbus / gsc_vbus_peak)
    except ZeroDivisionError:
        builder.get_object('gsc_vbus_level').set_value(0.0)
    builder.get_object('gsc_power').set_text('{:.0f}k'.format(gsc_power / 1e3))
    try:
        builder.get_object('gsc_power_level').set_value(gsc_power / gsc_power_max)
    except ZeroDivisionError:
        builder.get_object('gsc_power_level').set_value(0.0)
    builder.get_object('gsc_vgrid').set_text('{:.0f}'.format(gsc_vgrid))
    try:
        builder.get_object('gsc_vgrid_level').set_value(gsc_vgrid / gsc_vgrid_max)
    except ZeroDivisionError:
        builder.get_object('gsc_vgrid_level').set_value(0.0)
    # PLL good
    if gsc_status & (1 << 6):
        builder.get_object('gsc_pll_good').set_active(True)
    else:
        builder.get_object('gsc_pll_good').set_active(False)
    control_mode = gsc_status & 0x3
    label = ["gsc_mode_inactive", "gsc_mode_power", "gsc_mode_reactive", "gsc_mode_droop_q"][control_mode]
    builder.get_object(label).set_active(True)


def can_hs_temp(s):
    """
    Heatsink temperature.
    """
    global builder, gsc_hs_temp
    # print(f'can_hs_temp: setting temp {s}')
    if not len(s) == 8:
        print(f'ERROR: can_hs_temp: s={s} has no 8 chars')
    gsc_hs_temp = struct.unpack("!f", bytes.fromhex(s))[0]
    builder.get_object('gsc_hs_temp').set_text('{:.1f}'.format(gsc_hs_temp))


def can_params_1_1(s):
    """
    Parameters group 1 pt 1.
    target_fp, vgrid_nom, max_peak_current, droop_coef
    """
    global builder, gsc_target_fp, gsc_vgrid_nom, gsc_i_max_p, gsc_droop_coef
    if not len(s) == 16:
        print(f'ERROR: can_params_1_1: s={s} has no 16 chars')
    # print(f'target_fp = {s[0:4]}')
    gsc_target_fp = struct.unpack("!i", bytes.fromhex(str_to_size(s[0:4], 8)))[0] / 1000
    builder.get_object("gsc_fp_target").set_text("{:0.2f}".format(gsc_target_fp))
    gsc_vgrid_nom = struct.unpack("!i", bytes.fromhex(str_to_size(s[4:8], 8)))[0] / 10
    builder.get_object('gsc_vgrid_nom').set_text('{:.0f}'.format(gsc_vgrid_nom))
    gsc_i_max_p = struct.unpack("!i", bytes.fromhex(str_to_size(s[8:12], 8)))[0] / 10
    builder.get_object('gsc_i_max_p').set_text('{:.0f}'.format(gsc_i_max_p))
    builder.get_object('gsc_i_max').set_text('{:.0f}'.format(gsc_i_max_p / math.sqrt(2)))
    gsc_droop_coef = struct.unpack("!i", bytes.fromhex(str_to_size(s[12:16], 8)))[0] / 1000
    builder.get_object('droop_val').set_text('{:.1f}'.format(gsc_droop_coef * 100))


def can_params_1_2(s):
    """
    Parameters group 1 pt 2.
    power_nom, vbus_peak
    """
    global builder, gsc_power_nom, gsc_vbus_peak
    if not len(s) == 8:
        print(f'ERROR: can_params_1_2: s={s} has no 8 chars')
    gsc_power_nom = builder_set(s[0:4], 'gsc_power_nom', 10)
    gsc_vbus_peak = builder_set(s[4:8], 'gsc_vbus_peak', 10)


def can_meas_1_1(s):
    """
    Measures group 1 pt 1.
    reactive_power, voltage_imbalance, injected_current, grid_freq
    """
    global builder, gsc_reactive_power, gsc_reactive_power_max, gsc_vgrid_imbalance, gsc_i_line, gsc_i_max_p, gsc_fgrid
    if not len(s) == 16:
        print(f'ERROR: can_meas_1_1: s={s} has no 16 chars')
    gsc_reactive_power = struct.unpack("!i", bytes.fromhex(str_to_size(s[0:4], 8)))[0] * 10
    builder.get_object('gsc_reactive_power').set_text('{:.1f}k'.format(gsc_reactive_power / 1e3))
    gsc_reactive_power_max = 0.329 * gsc_power_nom
    builder.get_object('gsc_reactive_power_max').set_text('{:.1f}k'.format(gsc_reactive_power_max / 1e3))
    try:
        builder.get_object('gsc_reactive_power_level').set_value(gsc_reactive_power / gsc_reactive_power_max)
    except ZeroDivisionError:
        builder.get_object('gsc_reactive_power_level').set_value(0.0)
    gsc_vgrid_imbalance = struct.unpack("!i", bytes.fromhex(str_to_size(s[4:8], 8)))[0] / 1000
    builder.get_object('gsc_vgrid_imbalance').set_text('{:.1f}'.format(100 * gsc_vgrid_imbalance))
    gsc_i_line = struct.unpack("!i", bytes.fromhex(str_to_size(s[8:12], 8)))[0] / 10
    builder.get_object('gsc_i_line').set_text('{:.1f}'.format(gsc_i_line))
    try:
        builder.get_object('gsc_i_line_level').set_value((gsc_i_line * math.sqrt(2)) / gsc_i_max_p)
    except ZeroDivisionError:
        builder.get_object('gsc_i_line_level').set_value(0.0)
    gsc_fgrid = struct.unpack("!i", bytes.fromhex(str_to_size(s[12:16], 8)))[0] / (10 * 2 * math.pi)
    builder.get_object('gsc_fgrid').set_text('{:.1f}'.format(gsc_fgrid))
    builder.get_object('gsc_fgrid_level').set_value((gsc_fgrid - 55.0) / (65.0 - 55.0))


def can_meas_2_1(s):
    """
    Measures group 1 pt 2.
    vga_rms, vgb_rms, vgc_rms, ila_avg
    """
    global builder
    if not len(s) == 16:
        print(f'ERROR: can_meas_2_1: s={s} has no 16 chars')
        return
    builder_set(s[0:4], 'vga_rms', 0.1)
    builder_set(s[4:8], 'vgb_rms', 0.1)
    builder_set(s[8:12], 'vgc_rms', 0.1)
    builder_set(s[12:16], 'ila_avg', 0.1)


def can_meas_2_2(s):
    """
    Measures group 1 pt 2.
    vga_rms, vgb_rms, vgc_rms, ila_avg
    """
    global builder
    if not len(s) == 16:
        print(f'ERROR: can_meas_2_2: s={s} has no 16 chars')
        return
    builder_set(s[0:4], 'vga_avg', 0.1)
    builder_set(s[4:8], 'vgb_avg', 0.1)
    builder_set(s[8:12], 'vgc_avg', 0.1)
    builder_set(s[12:16], 'ilb_avg', 0.1)


def can_meas_2_3(s):
    """
    Measures group 1 pt 2.
    vga_rms, vgb_rms, vgc_rms, ila_avg
    """
    global builder
    if not len(s) == 16:
        print(f'ERROR: can_meas_2_3: s={s} has no 16 chars')
        return
    builder_set(s[0:4], 'ila_rms', 0.1)
    builder_set(s[4:8], 'ilb_rms', 0.1)
    builder_set(s[8:12], 'ilc_rms', 0.1)
    builder_set(s[12:16], 'ilc_avg', 0.1)


def can_gsc_adc_1(s):
    """ADC calibration measures group 1."""
    global builder
    if not len(s) == 16:
        print(f'ERROR: can_gsc_adc_1: s={s} has no 16 chars')
        return
    builder_set(s[0:4], "gsc_adc_a1")
    builder_set(s[4:8], "gsc_adc_a2")
    builder_set(s[8:12], "gsc_adc_a3")
    builder_set(s[12:16], "gsc_adc_a4")


def can_gsc_adc_2(s):
    """Set ADC group 2: ADC_B14, ADC_B2 .. 4."""
    if not len(s) == 16:
        print(f'ERROR: can_gsc_adc_2: s={s} has no 16 chars')
        return
    builder_set(s[0:4], 'gsc_adc_b14')
    builder_set(s[4:8], 'gsc_adc_b2')
    builder_set(s[8:12], 'gsc_adc_b3')
    builder_set(s[12:16], 'gsc_adc_b4')


def can_gsc_adc_3(s):
    """Set ADC group 2: ADC_C14, ADC_C2 .. 4."""
    if not len(s) == 16:
        print(f'ERROR: can_gsc_adc_3: s={s} has no 16 chars')
        return
    builder_set(s[0:4], 'gsc_adc_c14')
    builder_set(s[4:8], 'gsc_adc_c2')
    builder_set(s[8:12], 'gsc_adc_c3')
    builder_set(s[12:16], 'gsc_adc_c4')


can_ids = [[0x0040101, can_vbus_n_status, "Vbus P_grid V_grid status"],
           [0xc800103, can_hs_temp, "Heatsink temp"],
           [0xd00010c, can_params_1_1, "Params group 1 pt 1"],
           [0xd00010d, can_params_1_2, "Params group 2 pt 1"],
           [0xd00010e, can_meas_1_1, "Measures 1.1"],
           [0xd00010f, can_meas_2_1, "Measures 2.1"],
           [0xd000110, can_meas_2_2, "Measures 2.2"],
           [0xd000111, can_meas_2_3, "Measures 2.3"],
           [0xc400112, can_gsc_adc_1, "ADC A raw values"],
           [0xc400113, can_gsc_adc_2, "ADC B raw values"],
           [0xc400114, can_gsc_adc_3, "ADC C raw values"]]


def get_twai_data(lst):
    """
    Parse data of each CAN id.
    """
    s = lst[1]
    while len(s) < 8:
        s = '0' + s
    # print(f's={s}')
    can_id = struct.unpack("!I", bytes.fromhex(s))[0]
    for row in can_ids:
        if can_id == row[0]:
            if len(lst) == 3:
                row[1](lst[2].strip())
            else:
                print(f'WARNING: can id={hex(can_id)} has no data')


callbacks = [['version-id', set_version],
             ['twai', get_twai_data],
             ]


builder = Gtk.Builder()
builder.add_from_file("superv.glade")

myser = mySerial(builder, callbacks)
myser.debug = False  # remove this to operate
myser.create_list()
serial_combo = builder.get_object('serial_device')
serial_combo.remove_all()
for n in myser.dev_list:
    serial_combo.append(n, n)
serial_combo.set_active(False)

builder.connect_signals(Handler(builder))
window = builder.get_object('window1')
window.show_all()


# Threads go here
r_th = Thread(target=myser.read_thread)
r_th.daemon = True
r_th.start()


def write_thread():
    """Write serial commands. TODO: the commands."""
    while True:
        if not myser.ser.isOpen():
            time.sleep(2)
            continue
        myser.write('twai')
        time.sleep(1)
        myser.write('send e00010b 0100')
        time.sleep(1)
        myser.write('send e00010b 0200')
        time.sleep(1)
        myser.write('send e00010b 0300')
        time.sleep(1)


w_th = Thread(target=write_thread)
w_th.daemon = True
w_th.start()

Gtk.main()
