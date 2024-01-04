from threading import Lock
from pathlib import Path
import serial
import time
from termcolor import colored


USB_max = 4  # Maximum number of serial USB devices to search for
S_max = 4  # Maximum number of standard serial devices to search for


class CanSerial:
    """
    Class to group serial status vars.
    """

    def __init__(self, _interpreter):
        self.mut = Lock()
        self.mut_rd = Lock()
        self.name = ''
        self.ser = serial.Serial()
        self.dev_list = []
        self.debug = False
        self.interpreter = _interpreter

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
        self.name = name_
        self.ser.flush()
        self.ser.dtr = False
        self.ser.rts = False

    def reset(self):
        """Reset ESP32 with Reset pin connected to DTR."""
        if self.debug:
            print('INFO: resetting serial')
        self.ser.dtr = False
        self.ser.rts = True
        print('Serial RESET clicked')
        # sleep here 50.0us
        libc.usleep(50)
        self.ser.dtr = True
        self.ser.rts = True

    def disconnect(self):
        """Properly disconect serial flushing data."""
        # global ser_name
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
                line = ll.decode('utf-8').strip()
                lst = line.split(' ')
                f = filter(None, lst)
                lst = list(f)
                # if self.debug:
                # print(colored("LINE ", "blue") + f"{ll.decode('utf-8')}, lst={lst}")
                print(colored("LINE: ", "blue") + ll.decode('utf-8'))
            except UnicodeDecodeError:
                lst = []
            if len(lst) > 0:
                self.interpreter(lst)


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

