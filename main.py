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
from threading import Thread
import struct
import ctypes
from termcolor import colored
import gi
from canserial import CanSerial

gi.require_version("Gtk", "3.0")

from gi.repository import Gtk, GLib

# Used for usleep
libc = ctypes.CDLL('libc.so.6')

SPEED_MAX = 1200
CURRENT_MAX = 50.0


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

#
# MSC
#
msc_active: bool = False
msc_i_max: float = 1.0

#
# Inverter
#
inv_da: int = 0
inv_active: bool = False

def rad2rpm(rad):
    """Convert radian value to degree value."""
    return 30 * rad / math.pi


class Handler:
    """Main handler for GTK interface."""
    builder: Gtk.Builder

    def __init__(self, _builder):
        self.builder = _builder
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
        myser.write('version')

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
        name = combo.get_active_text()
        myser.open(name)
        version = self.builder.get_object('version')
        version.set_text('Version: ?????')
        serial_status = self.builder.get_object('serial_status')
        if myser.ser.isOpen():
            print('Serial {} openned successfuly'.format(name))
            serial_status.set_from_stock(Gtk.STOCK_APPLY, Gtk.IconSize.LARGE_TOOLBAR)
            print('Serial device changed')

            self.builder.get_object('serial_device').set_sensitive(False)
            self.builder.get_object('connect').set_sensitive(False)
            self.builder.get_object('disconnect').set_sensitive(True)
        else:
            serial_status.set_from_stock(Gtk.STOCK_DIALOG_WARNING, Gtk.IconSize.LARGE_TOOLBAR)

    def on_gsc_adc_raw_toggled(self, wdg):
        """Enable raw data CAN commando for GSC."""
        # global gsc_adc_raw
        if wdg.get_active():
            print('ADC raw active')
            myser.write('send e00010b 0001')
        else:
            print('ADC raw inactive')
            myser.write('send e00010b 0002')

    #
    # MSC
    #
    def on_msc_stop_clicked(self, _btn):
        global msc_active
        entry_mode = self.builder.get_object('msc_mode')
        entry_mode.set_text('Stopped')
        msc_active = False
        myser.write('send E000205 0000')

    def on_msc_start_clicked(self, _btn):
        global msc_active
        s_i_nom = builder.get_object('msc_i_nom').get_text()
        if (len(s_i_nom) < 2):
            print('ERR: msc_i_nom is not set')
            return
        entry_mode = self.builder.get_object('msc_mode')
        entry_mode.set_text('Running')
        x = builder.get_object('adj_op_current').get_value()
        i_ref = x * float(s_i_nom) * 0.01
        msc_active = True
        cmd = 'send 0e000205 {:04x}'.format(int(i_ref))
        print(f'start_clicked: cmd={cmd}')
        myser.write(cmd)

    def on_adj_op_current_value_changed(self, wdg):
        x = wdg.get_value()
        print(f'vc msc_i_ref={x}')
        if msc_active:
            s_i_nom = builder.get_object('msc_i_nom').get_text()
            if (len(s_i_nom) < 2):
                print('ERR: msc_i_nom is not set')
                return
            i_ref = x * float(s_i_nom) * 0.01
            cmd = 'send 0e000205 {:04x}'.format(int(i_ref))
            myser.write(cmd)

    def on_inv_active_toggled(self, wdg):
        global inv_active
        inv_active = wdg.get_active()
        cmd = 'inv {} {:02}'.format('1' if inv_active else '0', inv_da)
        print(f'INV: {cmd}')
        myser.write(cmd)
        # To TWAI:
        cmd = 'send 1ffc0700 {:02x}'.format((0x80 if inv_active else 0) + inv_da)
        print(f'INV: {cmd}')
        myser.write(cmd)

    def on_inv_da_value_changed(self, wdg):
        global inv_da
        inv_da = int(wdg.get_value())
        if inv_active:
            cmd = 'inv 1 {:02}'.format(inv_da)
            print(f'INV: {cmd}')
            myser.write(cmd)
            # To TWAI:
            cmd = 'send 1ffc0700 {:02x}'.format((0x80 if inv_active else 0) + inv_da)
            print(f'INV: {cmd}')
            myser.write(cmd)


def set_version(ver):
    """Set ESP32 firmware version."""
    version = builder.get_object('version')
    version.set_text('Version: {}'.format(ver[1]))
    # Taking a chance to get parameters:
    print('INFO: sending parameters request')
    myser.write('send e000208 0001')


def str_to_size(s: str, size: int) -> str:
    """Fill the beginning of string with zeroes."""
    while len(s) < size:
        s = '0' + s
    return s


def CANDataToString(s: str, k=1.0, n=0, unit='') -> str:
    """Return a string representing the value from CAN data represented by string s, multiplied by k with n number of decimal digits, appended by unit."""
    # global builder
    val = struct.unpack("!i", bytes.fromhex(str_to_size(s, 8)))[0] * k
    s = f'{{:.{n}f}}{unit}'
    return s.format(val)


def CANDataToInt16(s: str) -> int:
    "Return signed integer from string s being data of CAN message."
    val = struct.unpack("!h", bytes.fromhex(str_to_size(s, 4)))[0]
    return val


def CANDataToUInt16(s: str) -> int:
    "Return signed integer from string s being data of CAN message."
    val = struct.unpack("!H", bytes.fromhex(str_to_size(s, 4)))[0]
    return val


def builder_set(s: str, label: str, k=1.0, n=0, unit='') -> None:
    """Set a GTK label with value from s, no scale."""
    # global builder
    s = CANDataToString(s, k, n, unit)
    builder.get_object(label).set_text(s)


def gsc_vbus_n_status(s):
    """
    Extract Vbus, Pgrid, Vgrid and status from s.
    """
    # global builder
    global gsc_vbus, gsc_power, gsc_vgrid, gsc_status
    if not len(s) == 16:
        print(f'ERROR: gsc_vbus_n_status: s={s} has no 16 chars')
    gsc_vbus = CANDataToInt16(s[0:4]) * 0.1
    gsc_power = CANDataToInt16(s[4:8]) * 0.1
    gsc_vgrid = CANDataToInt16(s[8:12]) * 0.1
    gsc_status = CANDataToUInt16(s[12:16]) * 0.1
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


def set_gsc_hs_temp(s):
    """
    Heatsink temperature.
    """
    # global builder
    global gsc_hs_temp
    # print(f'gsc_hs_temp: setting temp {s}')
    if not len(s) == 4:
        print(f'ERROR: gsc_hs_temp: s={s} has no 4 chars')
    gsc_hs_temp = CANDataToInt16(s) * 0.1
    builder.get_object('gsc_hs_temp').set_text('{:.1f}'.format(gsc_hs_temp))


def gsc_params_1(s):
    """
    Parameters group 1 pt 1.
    target_fp, vgrid_nom, max_peak_current, droop_coef
    """
    # global builder
    global gsc_target_fp, gsc_vgrid_nom, gsc_i_max_p, gsc_droop_coef
    if not len(s) == 16:
        print(f'ERROR: gsc_params_1: s={s} has no 16 chars')
    # print(f'target_fp = {s[0:4]}')
    gsc_target_fp = CANDataToInt16(s[0:4]) / 1000
    builder.get_object("gsc_fp_target").set_text("{:0.2f}".format(gsc_target_fp))
    gsc_vgrid_nom = struct.unpack("!i", bytes.fromhex(str_to_size(s[4:8], 8)))[0] / 10
    builder.get_object('gsc_vgrid_nom').set_text('{:.0f}'.format(gsc_vgrid_nom))
    gsc_i_max_p = struct.unpack("!i", bytes.fromhex(str_to_size(s[8:12], 8)))[0] / 10
    builder.get_object('gsc_i_max_p').set_text('{:.0f}'.format(gsc_i_max_p))
    builder.get_object('gsc_i_max').set_text('{:.0f}'.format(gsc_i_max_p / math.sqrt(2)))
    gsc_droop_coef = struct.unpack("!i", bytes.fromhex(str_to_size(s[12:16], 8)))[0] / 1000
    builder.get_object('droop_val').set_text('{:.1f}'.format(gsc_droop_coef * 100))


def gsc_params_2(s: str) -> None:
    """
    Parameters group 1 pt 2. TODO: fix it is a mess
    power_nom, vbus_peak
    """
    # global builder
    global gsc_power_nom, gsc_vbus_peak
    if not len(s) == 8:
        print(f'ERROR: gsc_params_2: s={s} has no 8 chars')
    builder_set(s[0:4], 'gsc_power_nom', 10)
    gsc_power_nom = float(CANDataToString(s[0:4], 0.1))
    builder_set(s[4:8], 'gsc_vbus_peak', 10)
    gsc_vbus_peak = float(CANDataToString(s[4:8], 0.1))


def gsc_meas_1(s):
    """
    Measures group 1 pt 1.
    reactive_power, voltage_imbalance, injected_current, grid_freq
    """
    # global builder
    global gsc_reactive_power, gsc_reactive_power_max, gsc_vgrid_imbalance, gsc_i_line, gsc_fgrid
    if not len(s) == 16:
        print(f'ERROR: gsc_meas_1: s={s} has no 16 chars')
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


def gsc_meas_2(s):
    """
    Measures group 1 pt 2.
    vga_rms, vgb_rms, vgc_rms, ila_avg
    """
    # global builder
    if not len(s) == 16:
        print(f'ERROR: gsc_meas_2: s={s} has no 16 chars')
        return
    builder_set(s[0:4], 'vga_rms', 0.1)
    builder_set(s[4:8], 'vgb_rms', 0.1)
    builder_set(s[8:12], 'vgc_rms', 0.1)
    builder_set(s[12:16], 'ila_avg', 0.1)


def gsc_meas_3(s):
    """
    Measures group 1 pt 2.
    vga_rms, vgb_rms, vgc_rms, ila_avg
    """
    # global builder
    if not len(s) == 16:
        print(f'ERROR: gsc_meas_3: s={s} has no 16 chars')
        return
    builder_set(s[0:4], 'vga_avg', 0.1)
    builder_set(s[4:8], 'vgb_avg', 0.1)
    builder_set(s[8:12], 'vgc_avg', 0.1)
    builder_set(s[12:16], 'ilb_avg', 0.1)


def gsc_meas_4(s):
    """
    Measures group 1 pt 2.
    vga_rms, vgb_rms, vgc_rms, ila_avg
    """
    # global builder
    if not len(s) == 16:
        print(f'ERROR: gsc_meas_4: s={s} has no 16 chars')
        return
    builder_set(s[0:4], 'ila_rms', 0.1)
    builder_set(s[4:8], 'ilb_rms', 0.1)
    builder_set(s[8:12], 'ilc_rms', 0.1)
    builder_set(s[12:16], 'ilc_avg', 0.1)


def can_gsc_adc_1(s):
    """ADC calibration measures group 1."""
    # global builder
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


def msc_vbus_etal(s: str) -> None:
    "Receive MSC Vbus, stator current, electric machine frequency Hz and status (which is not well defined)."
    if not len(s) == 16:
        print(f'ERROR: msc_vbus_etal: s={s} has no 16 chars')
        return
    # print('can_msc_vbus_etal:')
    txt = CANDataToString(s[0:4], 0.1, 1)
    builder.get_object('msc_vbus').set_text(txt)
    builder.get_object('msc_vbus_lvl').set_value(float(txt))
    # print(f'can_msc_vbus_etal: Vbus={txt}')
    txt = CANDataToString(s[4:8], 0.1, 1)
    builder.get_object('im_i_line').set_text(txt)
    builder.get_object('im_i_line_lvl').set_value(float(txt))
    txt = CANDataToString(s[8:12], 0.1, 1)
    builder.get_object('im_fs').set_text(txt)
    builder.get_object('im_fs_lvl').set_value(float(txt))
    status = struct.unpack("!i", bytes.fromhex(str_to_size(s[12:16], 8)))[0]
    builder.get_object('inv1_enabled').set_active(status & 1)
    builder.get_object('msc_active').set_active(status & 2)
    builder.get_object('pll_good').set_active(status & 4)
    builder.get_object('encoder_is_calibrated').set_active(status & 8)
    builder.get_object('encoder_is_valid').set_active(status & 0x10)


def msc_hs_temp(s: str) -> None:
    if not len(s) == 4:
        print(f'ERROR: msc_params_1: s={s} has no 4 chars')
        return
    txt = CANDataToString(s[0:4], 0.1, 1)
    hs_temp = float(txt)
    builder.get_object('msc_hs_temp').set_text(txt)
    builder.get_object('msc_hs_temp_lvl').set_value(hs_temp)


def msc_params_1(s: str) -> None:
    "Receive PMSM i_nom, v_nom, fs_min ans i_max."
    global msc_i_max, msc_v_mon
    if not len(s) == 16:
        print(f'ERROR: msc_params_1: s={s} has no 16 chars')
        return
    i_nom = CANDataToString(s[0:4], 0.1, 1)
    builder.get_object("msc_i_nom").set_text(i_nom)
    v_nom = CANDataToString(s[4:8], 0.1, 1)
    msc_v_nom = float(v_nom)
    builder.get_object("msc_v_nom").set_text(v_nom)
    f_min = CANDataToString(s[8:12], 0.1, 1)
    builder.get_object('msc_f_min').set_text(f_min)
    i_max = CANDataToString(s[12:16], 0.1, 1)
    msc_i_max = float(i_max)
    builder.get_object('msc_i_max').set_text(i_max)
    builder.get_object('im_i_max').set_text(i_max)
    builder.get_object('im_i_line_lvl').set_max_value(msc_i_max)
    builder.get_object('i_rms_range').set_text('0  ...  {:-6.1f}'.format(msc_i_max))
    builder.get_object('ia_rms_lvl').set_max_value(msc_i_max)
    builder.get_object('ib_rms_lvl').set_max_value(msc_i_max)
    builder.get_object('ic_rms_lvl').set_max_value(msc_i_max)
    builder.get_object('i_avg_range').set_text('0  ...  {:-6.1f}'.format(msc_i_max * 0.01))
    builder.get_object('ia_avg_lvl').set_max_value(msc_i_max * 0.01)
    builder.get_object('ib_avg_lvl').set_max_value(msc_i_max * 0.01)
    builder.get_object('ic_avg_lvl').set_max_value(msc_i_max * 0.01)
    builder.get_object('v_rms_range').set_text('0  ...  {:-6.1f}'.format(msc_v_nom * 1.5))
    builder.get_object('va_rms_lvl').set_max_value(msc_v_nom * 1.5)
    builder.get_object('vb_rms_lvl').set_max_value(msc_v_nom * 1.5)
    builder.get_object('vc_rms_lvl').set_max_value(msc_v_nom * 1.5)
    builder.get_object('v_avg_range').set_text('0  ...  {:-6.1f}'.format(msc_v_nom * 0.01))
    builder.get_object('va_avg_lvl').set_max_value(msc_v_nom * 0.01)
    builder.get_object('vb_avg_lvl').set_max_value(msc_v_nom * 0.01)
    builder.get_object('vc_avg_lvl').set_max_value(msc_v_nom * 0.01)


def set_values_n_lvl(s: list[str], name: str, meas: str, k=1.0) -> None:
    i = 0
    for ph in ['a', 'b', 'c']:
        x = abs(CANDataToInt16(s[i]) * k)
        builder.get_object(name + ph + '_' + meas).set_text('{:.1f}'.format(x))
        builder.get_object(name + ph + '_' + meas + '_lvl').set_value(x)
        i += 1


def msc_meas_1(s: str) -> None:
    "Receive ia, ib and ic RMS and estimated Tel."
    set_values_n_lvl([s[0:4], s[4:8], s[8:12]], 'i', 'rms', 0.1)


def msc_meas_2(s: str) -> None:
    "Receive ia, ib and ic average."
    set_values_n_lvl([s[0:4], s[4:8], s[8:12]], 'i', 'avg', 0.1)


def msc_meas_3(s: str) -> None:
    "Receive va, vb and vc RMS and estimated Tel."
    set_values_n_lvl([s[0:4], s[4:8], s[8:12]], 'v', 'rms', 0.1)


def msc_meas_4(s: str) -> None:
    "Receive ia, ib and ic average and estimated Tel."
    set_values_n_lvl([s[0:4], s[4:8], s[8:12]], 'v', 'avg', 0.1)


can_ids = [
    # From GSC:
    [0x0040101, gsc_vbus_n_status, "Vbus P_grid V_grid status"],
    [0xc800103, set_gsc_hs_temp, "Heatsink temp"],
    [0xd000109, gsc_params_1, "Params group 1"],
    [0xd00010a, gsc_params_2, "Params group 2"],
    [0xd00010b, gsc_meas_1, "Measures group 1"],
    [0xd00010c, gsc_meas_2, "Measures group 2"],
    [0xd00010d, gsc_meas_3, "Measures group 3"],
    [0xd00010e, gsc_meas_4, "Measures group 4"],
    [0xc40010f, can_gsc_adc_1, "ADC A raw values"],
    [0xc400110, can_gsc_adc_2, "ADC B raw values"],
    [0xc400111, can_gsc_adc_3, "ADC C raw values"],
    # From MSC:
    [0xc100201, msc_vbus_etal, "Vbus LineCurrent Freq Status"],
    [0xc800203, msc_hs_temp, "MSC Heatsink temperature °C"],
    [0xd000209, msc_params_1, "MSC parameters group 1"],
    [0xd00020b, msc_meas_1, "MSC measurements group 1"],
    [0xd00020c, msc_meas_2, "MSC measurements group 2"],
    [0xd00020d, msc_meas_3, "MSC measurements group 3"],
    [0xd00020e, msc_meas_4, "MSC measurements group 4"],
]


def get_twai_data(lst) -> None:
    """
    Parse data of each CAN id.
    """
    if len(lst) < 2:
        print('WARN: get_twai_data has lst with less than 2 elements.')
        return
    s = lst[1]
    while len(s) < 8:
        s = '0' + s
    # print(f's={s}')
    can_id = struct.unpack("!I", bytes.fromhex(s))[0]
    for row in can_ids:
        if can_id == row[0]:
            if len(lst) == 3:
                row[1](lst[2].strip())
            # else:
            #     print(f'WARNING: can id={hex(can_id)} has no data')


callbacks = [['version', set_version],
             ['twai', get_twai_data],
             ]


def interpret(lst: list[str]) -> None:
    """Interpret commands from serial device."""
    for pair in callbacks:
        if lst[0] == pair[0]:
            GLib.idle_add(pair[1], lst)


builder = Gtk.Builder()
builder.add_from_file("superv.glade")

myser = CanSerial(interpret)
myser.debug = False  # remove this to operate
myser.create_list()
serial_combo = builder.get_object('serial_device')
serial_combo.remove_all()
for nn in myser.dev_list:
    serial_combo.append(nn, nn)
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
        # MSC Data request
        myser.write('send 0e000208 003c') # meas group 1

        time.sleep(2)  # TODO: review this time


w_th = Thread(target=write_thread)
w_th.daemon = True
w_th.start()

Gtk.main()
