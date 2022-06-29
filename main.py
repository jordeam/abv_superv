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

import gi

gi.require_version("Gtk", "3.0")

from gi.repository import Gtk, GLib

SPEED_MAX = 1200
CURRENT_MAX = 50.0

USB_max = 4  # Maximum number of serial USB devices to search for
S_max = 4  # Maximum number of standard serial devices to search for


class mySerial:
    """
    Class to agroup serial status vars.
    """
    name: str
    ser: serial.Serial
    dev_list: list
    mut: Lock
    builder: Gtk.Builder
    callbacks: list
    debug: bool

    def __init__(self, builder, callbacks):
        self.mut = Lock()
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
        if self.ser.isOpen():
            with self.mut:
                self.ser.write(s.encode('ascii'))
        else:
            print('ERROR: serial is not openned')

    def read(self):
        """Safe wrapper to serial read function."""
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
        version = self.builder.get_object('version')
        version.set_text('Version: ?????')
        serial_status = self.builder.get_object('serial_status')
        if self.ser.isOpen():
            print('Serial {} openned successfuly'.format(name_))
            serial_status.set_from_stock(Gtk.STOCK_APPLY, Gtk.IconSize.LARGE_TOOLBAR)
            print('Serial device changed')
            self.ser.write(b'version-id\r\n')
            self.name = name_
            self.builder.get_object('serial_device').set_sensitive(False)
            self.builder.get_object('connect').set_sensitive(False)
            self.builder.get_object('disconnect').set_sensitive(True)
        else:
            serial_status.set_from_stock(Gtk.STOCK_DIALOG_WARNING, Gtk.IconSize.LARGE_TOOLBAR)

    def serial_reset(self):
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
        if self.ser.isOpen():
            self.ser.flushInput()
            self.ser.flushOutput()
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
                    print(f'l = {ll}')
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
        while True:
            if self.ser.isOpen():
                self.interpret()
            else:
                # if it needs to access Gtk widgets:
                # GLib.idle_add(serial_status_blink, state)
                state = not state
                time.sleep(0.5)

    def write_thread(self):
        """Write serial commands. TODO: the commands."""
        while True:
            time.sleep(1)


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
gsc_vgrid_nom = 380.0  # grid nominal voltage
gsc_vgrid = 372.0  # Grid measured voltage
gsc_vgrid_imbalance = 0.02  # measured grid voltage imbalance
gsc_i_max_p = 510.0  # maximum peak current
gsc_i_line = 220.0  # grid injected current RMS value
gsc_hs_temp = 105.0  # Heatsink temperature in °C
gsc_status = 0  # status
gsc_adc_raw = False  # if True, GSC must send ADC raw data values


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
        myser.write(b'version-id\r\n')

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
        gsc_adc_raw = wdg.get_active()
        myser.write('gsc_adc_raw {}'.format("1" if gsc_adc_raw else "0"))

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

    def  on_msc_gen_auto_toggled(self, wdg):
        myser.write('msc_gen_auto {}'.format('1' if wdg.get_active() else '0'))


def set_version(ver):
    """Set ESP32 firmware version."""
    version = builder.get_object('version')
    version.set_text('Version: {}'.format(ver[1]))


def set_gsc_vbus(lst):
    """Set bus voltage widget."""
    global gsc_vbus
    gsc_vbus = float(lst[1])
    builder.get_object('gsc_vbus').set_text(lst[1])
    try:
        builder.get_object('gsc_vbus_level').set_value(float(lst[1]) / gsc_vbus_peak)
    except ZeroDivisionError:
        builder.get_object('gsc_vbus_level').set_value(0.0)


def set_gsc_vbus_peak(lst):
    """Set maximum allowed vbus voltage."""
    global gsc_vbus_peak
    gsc_vbus_peak = float(lst[1])
    builder.get_object('gsc_vbus_peak').set_text('{}'.format(gsc_vbus_peak))


def set_gsc_i_max_p(lst):
    """Set maximum allowed peak current value."""
    global gsc_i_max_p
    gsc_i_max_p = float(lst[1])
    builder.get_object('gsc_i_max_p').set_text('{}'.format(gsc_i_max_p))
    builder.get_object('gsc_i_max').set_text('{:.0f}'.format(gsc_i_max_p / math.sqrt(2)))


def set_gsc_vgrid_nom(lst):
    """Set nominal grid voltage parameter."""
    global gsc_vgrid_nom
    gsc_vgrid_nom = float(lst[1])
    builder.get_object('gsc_vgrid_nom').set_text('{}'.format(gsc_vgrid_nom))
    builder.get_object('gsc_vgrid_level').add_offset_value('a', 0.8)


def set_gsc_vgrid(lst):
    """Set grid voltage measure."""
    global gsc_vgrid
    gsc_vgrid = float(lst[1])
    builder.get_object('gsc_vgrid').set_text('{}'.format(gsc_vgrid))


def set_gsc_power(lst):
    """Set GSC active power."""
    global gsc_power
    gsc_power = float(lst[1])
    builder.get_object('gsc_power').set_text('{:.0f}k'.format(gsc_power / 1e3))
    try:
        builder.get_object('gsc_power_level').set_value(gsc_power / gsc_power_max)
    except ZeroDivisionError:
        builder.get_object('gsc_power_level').set_value(0.0)


def set_gsc_power_nom(lst):
    """Set grid side converter nominal and maximum power."""
    global gsc_power_nom, gsc_power_max
    gsc_power_nom = float(lst[1])
    builder.get_object('gsc_power_nom').set_text('{:.1f}'.format(gsc_power_nom))
    gsc_power_max = 1.1 * gsc_power_nom
    builder.get_object('gsc_power_max').set_text('{:.1f}k'.format(gsc_power_max / 1e3))


def set_gsc_vgrid_imbalance(lst):
    """Set voltage grid imbalance measure."""
    global gsc_vgrid_imbalance
    gsc_vgrid_imbalance = float(lst[1])
    builder.get_object('gsc_vgrid_imbalance').set_text('{}'.format(100 * gsc_vgrid_imbalance))


def set_gsc_reactive_power(lst):
    """Set GSC reactive power injected in grid."""
    global gsc_reactive_power
    gsc_reactive_power = float(lst[1])
    builder.get_object('gsc_reactive_power').set_text('{:.1f}k'.format(gsc_reactive_power / 1e3))
    reactive_power_max = 0.329 * gsc_power_nom
    builder.get_object('gsc_reactive_power_max').set_text('{:.1f}k'.format(reactive_power_max / 1e3))
    try:
        builder.get_object('gsc_reactive_power_level').set_value(gsc_reactive_power / reactive_power_max)
    except ZeroDivisionError:
        builder.get_object('gsc_reactive_power_level').set_value(0.0)


def set_gsc_i_line(lst):
    """Set GSC line current to grid."""
    global gsc_i_line
    gsc_i_line = float(lst[1])
    builder.get_object('gsc_i_line').set_text('{:.1f}'.format(gsc_i_line))
    try:
        builder.get_object('gsc_i_line_level').set_value((gsc_i_line * math.sqrt(2)) / gsc_i_max_p)
    except ZeroDivisionError:
        builder.get_object('gsc_i_line_level').set_value(0.0)


def set_gsc_hs_temp(lst):
    """Set heatsink temperature."""
    global gsc_hs_temp
    gsc_hs_temp = float(lst[1])
    builder.get_object('gsc_hs_temp').set_text('{:.0f}'.format(gsc_hs_temp))


def set_gsc_status(lst):
    """Set status."""
    global gsc_status
    gsc_status = int(lst[1])
    pll_good = gsc_status & (1 << 2)  # TODO: right value is BIT 6
    builder.get_object('gsc_pll_good').set_active(pll_good)


def gsc_meas_1_2(lst):
    """GSC Measurements Group 1 Part 2: vga, vgb and vgc."""
    builder.get_object('vga').set_text('{}'.format((lst[0] << 8 + lst[1]) / 10.0))
    builder.get_object('vgb').set_text('{}'.format((lst[2] << 8 + lst[3]) / 10.0))
    builder.get_object('vgc').set_text('{}'.format((lst[4] << 8 + lst[5]) / 10.0))


def set_gsc_adc_1(lst):
    """Set ADC group 1: ADC_A1 .. 4."""
    builder.get_object('gsc_adc_a1').set_text('{}'.format(lst[0] << 8 + lst[1]))
    builder.get_object('gsc_adc_a2').set_text('{}'.format(lst[2] << 8 + lst[3]))
    builder.get_object('gsc_adc_a3').set_text('{}'.format(lst[4] << 8 + lst[5]))
    builder.get_object('gsc_adc_a4').set_text('{}'.format(lst[6] << 8 + lst[7]))


def set_gsc_adc_2(lst):
    """Set ADC group 2: ADC_B14, ADC_B2 .. 4."""
    builder.get_object('gsc_adc_b14').set_text('{}'.format(lst[0] << 8 + lst[1]))
    builder.get_object('gsc_adc_b2').set_text('{}'.format(lst[2] << 8 + lst[3]))
    builder.get_object('gsc_adc_b3').set_text('{}'.format(lst[4] << 8 + lst[5]))
    builder.get_object('gsc_adc_b4').set_text('{}'.format(lst[6] << 8 + lst[7]))


def set_gsc_adc_3(lst):
    """Set ADC group 2: ADC_C14, ADC_C2 .. 4."""
    builder.get_object('gsc_adc_c14').set_text('{}'.format(lst[0] << 8 + lst[1]))
    builder.get_object('gsc_adc_c2').set_text('{}'.format(lst[2] << 8 + lst[3]))
    builder.get_object('gsc_adc_c3').set_text('{}'.format(lst[4] << 8 + lst[5]))
    builder.get_object('gsc_adc_c4').set_text('{}'.format(lst[6] << 8 + lst[7]))


callbacks = [['version-id', set_version],
             ['gsc_vbus', set_gsc_vbus],
             ['gsc_vbus_peak', set_gsc_vbus_peak],
             ['gsc_status', set_gsc_status],
             ['gsc_i_max_p', set_gsc_i_max_p],
             ['gsc_vgrid', set_gsc_vgrid],
             ['gsc_vgrid_nom', set_gsc_vgrid_nom],
             ['gsc_power', set_gsc_power],
             ['gsc_reactive_power', set_gsc_reactive_power],
             ['gsc_power_nom', set_gsc_power_nom],
             ['gsc_i_line', set_gsc_i_line],
             ['gsc_vgrid_imbalance', set_gsc_vgrid_imbalance],
             ['gsc_hs_temp', set_gsc_hs_temp],
             ['gsc_meas_1_2', gsc_meas_1_2],
             ['gsc_adc_1', set_gsc_adc_1],
             ['gsc_adc_2', set_gsc_adc_2],
             ['gsc_adc_3', set_gsc_adc_3]]


builder = Gtk.Builder()
builder.add_from_file("superv.glade")

myser = mySerial(builder, callbacks)
myser.debug = True  # remove this to operate
myser.create_list()
serial_combo = builder.get_object('serial_device')
serial_combo.remove_all()
for n in myser.dev_list:
    serial_combo.append(n, n)
serial_combo.set_active(0)

builder.connect_signals(Handler(builder))
window = builder.get_object('window1')
window.show_all()


# Threads go here
r_th = Thread(target=myser.read_thread)
r_th.daemon = True
r_th.start()

w_th = Thread(target=myser.write_thread)
w_th.daemon = True
w_th.start()

Gtk.main()
