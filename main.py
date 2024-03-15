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
import twai_ids as ids

gi.require_version("Gtk", "3.0")

from gi.repository import Gtk, GLib

# Used for usleep
libc = ctypes.CDLL('libc.so.6')

SPEED_MAX = 1200
CURRENT_MAX = 50.0



# Global parameters
gsc_vbus = 0.0
gsc_vbus_max = 0.0  # Maximum bus voltage
gsc_vbus_target_max = 0.0
gsc_vbus_target_min = 0.0
gsc_vbus_min = 0.0

gsc_power = 220e3  # injected active power
gsc_power_nom = 250e3  # Nominal active power to be injected
gsc_power_max = 275e3  # Maximum allowed active power to be injected
gsc_vgrid_nom = 380.0  # grid nominal voltage
gsc_vgrid = 372.0  # Grid measured voltage
gsc_vgrid_max = 480.0  # Maximum grid voltage
gsc_vgrid_imbalance = 0.02  # measured grid voltage imbalance
gsc_i_max = 0.0  # maximum current
gsc_i_min = 0.0  # minimum current
gsc_f_nom = 0.0  # nominal frequency
gsc_hs_temp = 125.0  # Heatsink temperature in °C
gsc_status: int = 0  # status
gsc_adc_raw = False  # if True, GSC must send ADC raw data values
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

    def on_connect_btn_clicked(self, _):
        self.on_connect_clicked(self)

    def on_gsc_adc_raw_toggled(self, wdg):
        """Enable raw data CAN commando for GSC."""
        # global gsc_adc_raw
        if wdg.get_active():
            print('ADC raw active')
            myser.write('send {:08x} 0040'.format(ids.GSCID_DATA_REQ))
        else:
            print('ADC raw inactive')
            myser.write('send {:08x} 0080'.format(ids.GSCID_DATA_REQ))

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
        i_ref = int(x * 10)
        if i_ref < 0:
            i_ref = 0x10000 + i_ref
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

    def on_msc_adc_raw_toggled(self, wdg):
        if wdg.get_active():
            cmd = 'send {:08x} {:04x}'.format(ids.MSCID_DATA_REQ, 0x40)
        else:
            cmd = 'send {:08x} {:04x}'.format(ids.MSCID_DATA_REQ, 0x80)
        myser.write(cmd)

def set_version(ver):
    """Set ESP32 firmware version."""
    version = builder.get_object('version')
    version.set_text('Version: {}'.format(ver[1]))
    # Taking a chance to get parameters:
    print('INFO: sending MSC parameters request')
    myser.write('send {:08x} 0001'.format(ids.MSCID_DATA_REQ))
    print('INFO: sending GSC parameters group 1 and 2 request')
    myser.write('send {:08x} 0003'.format(ids.GSCID_DATA_REQ))


def str_to_size(s: str, size: int) -> str:
    """Fill the beginning of string with zeroes."""
    while len(s) < size:
        s = '0' + s
    return s


def CANDataToString(s: str, k=1.0, n_dec=0, unit='') -> str:
    """Return a string representing the value from CAN data represented by string s, multiplied by k with n_dec number of decimal digits, appended by unit."""
    # global builder
    val = struct.unpack("!i", bytes.fromhex(str_to_size(s, 8)))[0] * k
    s = f'{{:.{n_dec}f}}{unit}'
    return s.format(val)


def CANDataToInt16(s: str) -> int:
    "Return signed integer from string s being data of CAN message."
    val = struct.unpack("!h", bytes.fromhex(s))[0]
    return val


def CANDataToUInt16(s: str) -> int:
    "Return signed integer from string s being data of CAN message."
    val = struct.unpack("!H", bytes.fromhex(s))[0]
    return val


def builder_set(s: str, label: str, k=1.0, n_dec=0, unit='', signed=True) -> None:
    """Set a GTK label with value from s, no scale."""
    # global builder
    if signed:
        val = CANDataToInt16(s) * k
    else:
        val = CANDataToUInt16(s) * k
    fmt = f'{{:.{n_dec}f}}{unit}'
    builder.get_object(label).set_text(fmt.format(val))


def gsc_vbus_n_status(s):
    """
    Extract Vbus and status from s.
    """
    # global builder
    global gsc_vbus, gsc_status
    if not len(s) == 16:
        print(f'ERROR: gsc_vbus_n_status: s={s} has not 16 chars')
    gsc_vbus = CANDataToInt16(s[0:4]) * 0.1
    gsc_status = CANDataToUInt16(s[12:16])
    # Vbus
    txt = '{:.1f}'.format(gsc_vbus)
    builder.get_object('gsc_vbus').set_text(txt)
    builder.get_object('gsc_vbus_lvl').set_value(gsc_vbus)
    # i_rms
    i_rms = CANDataToUInt16(s[4:8]) * 0.1
    txt = '{:.1f}'.format(i_rms)
    builder.get_object('gsc_i_line').set_text(txt)
    builder.get_object('gsc_i_line_lvl').set_value(i_rms)
    # Output power
    p_out = CANDataToInt16(s[8:12]) * 0.1
    txt = '{:.1f}'.format(p_out)
    builder.get_object('gsc_power').set_text(txt)
    builder.get_object('gsc_power_lvl').set_value(p_out)
    # Status
    builder.get_object('gsc_inv_enabled').set_active(gsc_status & 1)
    builder.get_object('gsc_imbalanced').set_active(gsc_status & 2)
    # gsc_mode
    gsc_mode = (gsc_status >> 5) & 3
    builder.get_object('gsc_off').set_active(gsc_mode == 0)
    builder.get_object('gsc_normal').set_active(gsc_mode == 1)
    builder.get_object('gsc_discharge').set_active(gsc_mode == 2)
    # Program Mode
    gsc_program_mode = (gsc_status >> 2) & 7
    match gsc_program_mode:
        case 0:
            builder.get_object('gsc_program_mode').set_text('Initializing')
        case 1:
            builder.get_object('gsc_program_mode').set_text('Checking UCC5870')
        case 2:
            builder.get_object('gsc_program_mode').set_text('Running OK')
        case 3:
            builder.get_object('gsc_program_mode').set_text('Emulation')
        case _:
            print('ERROR: got invalid gsc_program_mode')


def set_gsc_hs_temp(s):
    """
    Heatsink temperature.
    """
    # global builder
    global gsc_hs_temp
    # print(f'gsc_hs_temp: setting temp {s}')
    if not len(s) == 4:
        print(f'ERROR: gsc_hs_temp: s={s} has not 4 chars')
    gsc_hs_temp = CANDataToInt16(s) * 0.1
    builder.get_object('gsc_hs_temp').set_text('{:.1f}'.format(gsc_hs_temp))


def gsc_params_1(s):
    """
    Parameters group 1
    target_fp, vgrid_nom, max_peak_current, droop_coef
    """
    global gsc_power_max
    global gsc_i_max, gsc_i_min, gsc_f_nom
    if not len(s) == 12:
        print(f'ERROR: gsc_params_1: s={s} has not 12 chars')
    # print(f'target_fp = {s[0:4]}')
    gsc_i_max = float(CANDataToInt16(s[0:4]))
    txt = "{:.1f}".format(gsc_i_max)
    builder.get_object("gsc_i_max").set_text(txt)
    builder.get_object("gsc_i_line_max").set_text(txt)
    builder.get_object("gsc_i_line_lvl").set_max_value(gsc_i_max)
    if gsc_vbus_max != 0:
        gsc_power_max = gsc_vbus_max * gsc_i_max
        builder.get_object('gsc_power_max').set_text('{:.1f}'.format(gsc_power_max))
        builder.get_object('gsc_power_lvl').set_max_value(gsc_power_max)
    gsc_i_min = float(CANDataToInt16(s[4:8]))
    builder.get_object('gsc_i_min').set_text('{:.1f}'.format(gsc_i_min))
    gsc_f_nom = float(CANDataToInt16(s[8:12]))
    builder.get_object('gsc_f_nom').set_text('{:.1f}'.format(gsc_f_nom))


def gsc_params_2(s: str) -> None:
    """
    Parameters group 2
    """
    global gsc_power_max, gsc_vbus_max
    if not len(s) == 16:
        print(f'ERROR: gsc_params_2: s={s} has not 16 chars')
    # VBUS_MAX
    gsc_vbus_max = float(CANDataToUInt16(s[0:4]))
    if gsc_i_max != 0:
        gsc_power_max = gsc_vbus_max * gsc_i_max
        builder.get_object('gsc_power_max').set_text('{:.0f}'.format(gsc_power_max))
        builder.get_object('gsc_power_lvl').set_max_value(gsc_power_max)
    txt = '{:.1f}'.format(gsc_vbus_max)
    builder.get_object("gsc_vbus_max").set_text(txt)
    builder.get_object("gsc_vbus_peak").set_text(txt)
    builder.get_object("gsc_vbus_lvl").set_max_value(gsc_vbus_max)
    #VBUS_TARGET_MAX
    x = float(CANDataToUInt16(s[4:8]))
    builder.get_object("gsc_vbus_target_max").set_text('{:.1f}'.format(x))
    #VBUS_TARGET_MIN
    x = float(CANDataToUInt16(s[8:12]))
    builder.get_object("gsc_vbus_target_min").set_text('{:.1f}'.format(x))
    #VBUS_MIN
    x = float(CANDataToUInt16(s[12:16]))
    builder.get_object("gsc_vbus_min").set_text('{:.1f}'.format(x))


def gsc_meas_1(s):
    """
    Measures group 1
    """
    # global builder
    if not len(s) == 16:
        print(f'ERROR: gsc_meas_1: s={s} has not 16 chars')
    builder_set(s[0:4], 'ila_rms', 0.1, 1)
    builder_set(s[4:8], 'ilb_rms', 0.1, 1)
    builder_set(s[8:12], 'ilc_rms', 0.1, 1)
    builder_set(s[12:16], 'gsc_imbalance', 1e-1, 1)


def gsc_meas_2(s):
    """
    Measures group 1 pt 2.
    vga_rms, vgb_rms, vgc_rms, ila_avg
    """
    # global builder
    if not len(s) == 12:
        print(f'ERROR: gsc_meas_2: s={s} has not 12 chars')
        return
    builder_set(s[0:4], 'ila_avg', 0.1, 1, signed=True)
    builder_set(s[4:8], 'ilb_avg', 0.1, 1, signed=True)
    builder_set(s[8:12], 'ilc_avg', 0.1, 1, signed=True)


def gsc_meas_3(s):
    """
    Measures group 1 pt 2.
    vga_rms, vgb_rms, vgc_rms, ila_avg
    """
    # global builder
    if not len(s) == 12:
        print(f'ERROR: gsc_meas_3: s={s} has not 12 chars')
        return
    builder_set(s[0:4], 'vga_rms', 0.1, 1)
    builder_set(s[4:8], 'vgb_rms', 0.1, 1)
    builder_set(s[8:12], 'vgc_rms', 0.1, 1)


def gsc_meas_4(s):
    """
    Measures group 1 pt 2.
    vga_rms, vgb_rms, vgc_rms, ila_avg
    """
    # global builder
    if not len(s) == 12:
        print(f'ERROR: gsc_meas_4: s={s} has not 12 chars')
        return
    builder_set(s[0:4], 'vga_avg', 0.1, 1, signed=True)
    builder_set(s[4:8], 'vgb_avg', 0.1, 1, signed=True)
    builder_set(s[8:12], 'vgc_avg', 0.1, 1, signed=True)


def can_gsc_adc_1(s):
    """ADC calibration measures group 1."""
    # global builder
    if not len(s) == 16:
        print(f'ERROR: can_gsc_adc_1: s={s} has not 16 chars')
        return
    builder_set(s[0:4], "gsc_adc_a1")
    builder_set(s[4:8], "gsc_adc_a2")
    builder_set(s[8:12], "gsc_adc_a3")
    builder_set(s[12:16], "gsc_adc_a4")
    # copies
    builder_set(s[0:4], "gsc_adc_a1_")
    builder_set(s[4:8], "gsc_adc_a2_")
    builder_set(s[8:12], "gsc_adc_a3_")
    builder_set(s[12:16], "gsc_adc_a4_")


def can_gsc_adc_2(s):
    """Set ADC group 2: ADC_B14, ADC_B2 .. 4."""
    if not len(s) == 16:
        print(f'ERROR: can_gsc_adc_2: s={s} has not 16 chars')
        return
    builder_set(s[0:4], 'gsc_adc_b14')
    builder_set(s[4:8], 'gsc_adc_b2')
    builder_set(s[8:12], 'gsc_adc_b3')
    builder_set(s[12:16], 'gsc_adc_b4')
    # no copies

    
def can_gsc_adc_3(s):
    """Set ADC group 2: ADC_C14, ADC_C2 .. 4."""
    if not len(s) == 16:
        print(f'ERROR: can_gsc_adc_3: s={s} has not 16 chars')
        return
    builder_set(s[0:4], 'gsc_adc_c14')
    builder_set(s[4:8], 'gsc_adc_c2')
    builder_set(s[8:12], 'gsc_adc_c3')
    builder_set(s[12:16], 'gsc_adc_c4')
    # copies
    builder_set(s[4:8], 'gsc_adc_c2_')
    builder_set(s[12:16], 'gsc_adc_c4_')


def msc_vbus_etal(s: str) -> None:
    "Receive MSC Vbus, stator current, electric machine frequency Hz and status (which is not well defined)."
    if not len(s) == 16:
        print(f'ERROR: msc_vbus_etal: s={s} has not 16 chars')
        return
    # print('can_msc_vbus_etal:')
    # Vbus
    x = abs(CANDataToInt16(s[0:4]) * 0.1)
    txt = "{:.1f}".format(x)
    builder.get_object('msc_vbus').set_text(txt)
    builder.get_object('msc_vbus_lvl').set_value(x)
    # print(f'can_msc_vbus_etal: Vbus={txt}')
    # Line Current
    x: float = abs(CANDataToInt16(s[4:8]) * 0.1)
    txt = "{:.1f}".format(x)
    builder.get_object('im_i_line').set_text(txt)
    builder.get_object('im_i_line_lvl').set_value(float(txt))
    # Frequency
    x: float = abs(CANDataToInt16(s[8:12]) * 0.1)
    txt = "{:.1f}".format(x)
    builder.get_object('im_fs').set_text(txt)
    builder.get_object('im_fs_lvl').set_value(float(txt))
    # Status
    status = CANDataToUInt16(s[12:16])
    builder.get_object('inv1_enabled').set_active(status & 1)
    builder.get_object('msc_active').set_active(status & 2)
    builder.get_object('pll_good').set_active(status & 4)
    builder.get_object('encoder_is_calibrated').set_active(status & 8)
    builder.get_object('encoder_is_valid').set_active(status & 0x10)


def msc_hs_temp(s: str) -> None:
    if not len(s) == 4:
        print(f'ERROR: msc_params_1: s={s} has not 4 chars')
        return
    txt = CANDataToString(s[0:4], 0.1, 1)
    hs_temp = float(txt)
    builder.get_object('msc_hs_temp').set_text(txt)
    builder.get_object('msc_hs_temp_lvl').set_value(hs_temp)


def msc_params_1(s: str) -> None:
    "Receive PMSM i_nom, v_nom, fs_min ans i_max."
    global msc_i_max, msc_v_mon
    if not len(s) == 16:
        print(f'ERROR: msc_params_1: s={s} has not 16 chars')
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
    # i rms
    i_rms_max = msc_i_max * 1.1
    builder.get_object('i_rms_range').set_text('0  ...  {:-6.1f}'.format(i_rms_max))
    builder.get_object('ia_rms_lvl').set_max_value(i_rms_max)
    builder.get_object('ib_rms_lvl').set_max_value(i_rms_max)
    builder.get_object('ic_rms_lvl').set_max_value(i_rms_max)
    # i avg
    i_avg_max = msc_i_max * 1.1
    builder.get_object('i_avg_range').set_text('0  ...  {:-6.1f}'.format(i_avg_max))
    builder.get_object('ia_avg_lvl').set_max_value(i_avg_max)
    builder.get_object('ib_avg_lvl').set_max_value(i_avg_max)
    builder.get_object('ic_avg_lvl').set_max_value(i_avg_max)
    # v rms
    v_rms_max = msc_v_nom * 1.25
    builder.get_object('v_rms_range').set_text('0  ...  {:-6.1f}'.format(v_rms_max))
    builder.get_object('va_rms_lvl').set_max_value(v_rms_max)
    builder.get_object('vb_rms_lvl').set_max_value(v_rms_max)
    builder.get_object('vc_rms_lvl').set_max_value(v_rms_max)
    # v avg
    v_avg_max = msc_v_nom * 1.1
    builder.get_object('v_avg_range').set_text('0  ...  {:-6.1f}'.format(v_avg_max))
    builder.get_object('va_avg_lvl').set_max_value(v_avg_max)
    builder.get_object('vb_avg_lvl').set_max_value(v_avg_max)
    builder.get_object('vc_avg_lvl').set_max_value(v_avg_max)


def set_values_n_lvl(s: list[str], name: str, meas: str, k=1.0) -> None:
    i = 0
    for ph in ['a', 'b', 'c']:
        x = CANDataToInt16(s[i]) * k
        builder.get_object(name + ph + '_' + meas).set_text('{:.1f}'.format(x))
        builder.get_object(name + ph + '_' + meas + '_lvl').set_value(x)
        i += 1


def msc_meas_1(s: str) -> None:
    "Receive ia, ib and ic RMS and estimated Tel."
    # print('msc_meas_1')
    set_values_n_lvl([s[0:4], s[4:8], s[8:12]], 'i', 'rms', 0.1)
    # Estimated Tel
    x = int(CANDataToInt16(s[12:16]) * 0.1)
    builder.get_object('msc_tel').set_text('{:d}'.format(x))
    builder.get_object('msc_tel_lvl').set_value(x)


def msc_meas_2(s: str) -> None:
    "Receive ia, ib, ic average and encoder."
    set_values_n_lvl([s[0:4], s[4:8], s[8:12]], 'i', 'avg', 0.1)
    # Encoder
    x = CANDataToInt16(s[12:16])
    builder.get_object('msc_enc').set_text('{:d}'.format(x))
    builder.get_object('msc_enc_lvl').set_value(x)


def msc_meas_3(s: str) -> None:
    "Receive va, vb and vc RMS."
    set_values_n_lvl([s[0:4], s[4:8], s[8:12]], 'v', 'rms', 0.1)


def msc_meas_4(s: str) -> None:
    "Receive ia, ib and ic average."
    set_values_n_lvl([s[0:4], s[4:8], s[8:12]], 'v', 'avg', 0.1)

def msc_adc_a(s: str) -> None:
    builder_set(s[0:4], 'msc_adc_a1')
    builder_set(s[4:8], 'msc_adc_a2')
    builder_set(s[8:12], 'msc_adc_a3')
    builder_set(s[12:16], 'msc_adc_a4')
    # copies
    builder_set(s[0:4], "msc_adc_a1_")
    builder_set(s[4:8], "msc_adc_a2_")
    builder_set(s[8:12], "msc_adc_a3_")
    builder_set(s[12:16], "msc_adc_a4_")

def msc_adc_b(s: str) -> None:
    builder_set(s[0:4], 'msc_adc_b14')
    builder_set(s[4:8], 'msc_adc_b2')
    builder_set(s[8:12], 'msc_adc_b3')
    builder_set(s[12:16], 'msc_adc_b4')

def msc_adc_c(s: str) -> None:
    builder_set(s[0:4], 'msc_adc_c14')
    builder_set(s[4:8], 'msc_adc_c2')
    builder_set(s[8:12], 'msc_adc_c3')
    builder_set(s[12:16], 'msc_adc_c4')
    # copies
    builder_set(s[4:8], 'msc_adc_c2_')
    builder_set(s[12:16], 'msc_adc_c4_')


can_ids = [
    # From GSC:
    [ids.GSCID_VBUS_N_STATUS, gsc_vbus_n_status, "Vbus, status"],
    [ids.GSCID_HS_TEMP, set_gsc_hs_temp, "Heatsink temp"],
    [ids.GSCID_PARAMS_1, gsc_params_1, "Params group 1"],
    [ids.GSCID_PARAMS_2, gsc_params_2, "Params group 2"],
    [ids.GSCID_MEAS_1, gsc_meas_1, "Measures group 1"],
    [ids.GSCID_MEAS_2, gsc_meas_2, "Measures group 2"],
    [ids.GSCID_MEAS_3, gsc_meas_3, "Measures group 3"],
    [ids.GSCID_MEAS_4, gsc_meas_4, "Measures group 4"],
    [ids.GSCID_ADCA, can_gsc_adc_1, "ADC A raw values"],
    [ids.GSCID_ADCB, can_gsc_adc_2, "ADC B raw values"],
    [ids.GSCID_ADCC, can_gsc_adc_3, "ADC C raw values"],
    # From MSC:
    [ids.MSCID_VBUS_N_STATUS, msc_vbus_etal, "Vbus LineCurrent Freq Status"],
    [ids.MSCID_HS_TEMP, msc_hs_temp, "MSC Heatsink temperature °C"],
    [ids.MSCID_PARAMS_1, msc_params_1, "MSC parameters group 1"],
    [ids.MSCID_MEAS_1, msc_meas_1, "MSC measurements group 1"],
    [ids.MSCID_MEAS_2, msc_meas_2, "MSC measurements group 2"],
    [ids.MSCID_MEAS_3, msc_meas_3, "MSC measurements group 3"],
    [ids.MSCID_MEAS_4, msc_meas_4, "MSC measurements group 4"],
    [ids.MSCID_ADCA, msc_adc_a, "MSC ADC A raw values"],
    [ids.MSCID_ADCB, msc_adc_b, "MSC ADC B raw values"],
    [ids.MSCID_ADCC, msc_adc_c, "MSC ADC C raw values"]
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
            #     print(f'WARNING: can id={hex(can_id)} has not data')


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
    i: int = 0
    while True:
        i += 1
        if not myser.ser.isOpen():
            time.sleep(2)
            continue
        if i == 1:
            # MSC meas group 1, 2, 3 and 4
            myser.write('send {:08x} 003c'.format(ids.MSCID_DATA_REQ))
        elif i == 2:
            # GSC meas group 1, 2, 3 and 4
            myser.write('send {:08x} 003c'.format(ids.GSCID_DATA_REQ)) # meas group 1
            # Go to MSC again
            i = 0
        else:
            i = 0
        time.sleep(2)  # TODO: review this time


w_th = Thread(target=write_thread)
w_th.daemon = True
w_th.start()

Gtk.main()
