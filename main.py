#!/usr/bin/python2.7
import OLED_driver as oled
import pifacedigitalio as pfd
import subprocess
import traceback
import logging
import cwiid
import time
import re

import multiprocessing.pool

logging.basicConfig(filename="/home/pi/main.log",
                    level=logging.DEBUG,
                    format="%(asctime)s: %(levelname)s: %(message)s",
                    datefmt='%Y-%m-%d %H:%M:%S')

logging.info("Started")

PFD_BTN_1 = 8
PFD_BTN_2 = 4
PFD_BTN_3 = 2
PFD_BTN_4 = 1

ACC_CAL = (128, 128, 128)

oled.init()
try:
    pfd.init()
    piface = True
except pfd.NoPiFaceDigitalDetectedError:
    logging.error("No PiFace detected.")
    piface = False
WIIMOTE = None
EXIT_CMD = None

# -- Motor PWM thread --
MOTOR_PWM_THREAD = multiprocessing.pool.ThreadPool(1)
MOTOR_PWM_THREAD_speeds = [(0, 0, 0, 0)]

def MOTOR_PWM_THREAD_main(speeds):
    CHANGED = True
    while True:
        #t = time.time()
        cstate = speeds[0]
        if any(map(lambda x:x>0, cstate)):
            CHANGED = True
            for x in range(0, 5):
                pfd.digital_write(0, cstate[0]*5 > x)
                pfd.digital_write(1, cstate[1]*5 > x)
                pfd.digital_write(2, cstate[2]*5 > x)
                pfd.digital_write(3, cstate[3]*5 > x)
                #while time.time() < t+0.001:
                #    time.sleep(0)
        elif CHANGED:
            pfd.digital_write(0, 0)
            pfd.digital_write(1, 0)
            pfd.digital_write(2, 0)
            pfd.digital_write(3, 0)
            CHANGED = False

MOTOR_PWM_THREAD_task = MOTOR_PWM_THREAD.apply_async(MOTOR_PWM_THREAD_main, (MOTOR_PWM_THREAD_speeds,))
# ----------------------
# -- Flashing LEDs thread --
#FLASHING_LEDS_THREAD = multiprocessing.pool.ThreadPool(1)
#FLASHING_LEDS_THREAD_states = [(0, 0, 0, 0)]
#
#def FLASHING_LEDS_THREAD_main(states):
#    while True:
#        for x in range(7,3,-1):
#            state = states[0]
#            pfd.digital_write(4, x & int(2**state[0]/2))
#            pfd.digital_write(5, x & int(2**state[1]/2))
#            pfd.digital_write(6, x & int(2**state[2]/2))
#            pfd.digital_write(7, x & int(2**state[3]/2))
#            time.sleep(0.25)
#
#FLASHING_LEDS_THREAD_task = FLASHING_LEDS_THREAD.apply_async(FLASHING_LEDS_THREAD_main, (FLASHING_LEDS_THREAD_states,))
# --------------------------

def get_button_int():
    return sum([int(pfd.digital_read(x))<<x for x in range(4)])
def set_led_int(leds):
    for x in range(0, 4):
        pfd.digital_write(x+4, leds & (2**x)) # set pins 4-7

def get_wmbut_int():
    if WIIMOTE is None: return 0
    else: return WIIMOTE.state.get("buttons", 0)

def run_motors(m0=0, m1=0, m2=0, m3=0):
    MOTOR_PWM_THREAD_speeds[0] = (m0, m1, m2, m3)
    #pfd.digital_write(0, bool(m0))
    #pfd.digital_write(1, bool(m1))
    #pfd.digital_write(2, bool(m2))
    #pfd.digital_write(3, bool(m3))

def oled_write_menu(name, sel, btns="^v><"):
    oled.write_line(0, name.ljust(14)[:14]+btns[0]+btns[2])
    oled.write_line(1, sel.ljust(14)[:14]+btns[1]+btns[3])


def cmd_pass():
    oled.write_line(0, "Continuing...", 1)
    oled.write_line(1, "")
    time.sleep(1)
    return False

def cmd_run():
    if WIIMOTE is None:
        oled.write_line(0, "No wiimote", 1)
        oled.write_line(1, "conencted", 1)
        time.sleep(1.5)
        return False
    oled.write_line(0, "Press A", 1)
    oled.write_line(1, "for options", 1)
    time.sleep(1.5)
    but = WIIMOTE.state.get("buttons", 0)
    pwr = [0, 0] # L, R
    while not but & cwiid.BTN_HOME:
        s = WIIMOTE.state
        but, acc = s.get("buttons", 0), s.get("acc", [0,0,0])
        roll, pitch, accel = [x-y for (x,y) in zip(acc, ACC_CAL)]
        if but & cwiid.BTN_2:
            pwr = [1 - (pitch-2)/40. if pitch > 2 else 1,
                   1 + (pitch+2)/40. if pitch < -2 else 1]
        elif but & (cwiid.BTN_1 | cwiid.BTN_B): # brake - similar to else but more reduction
            pwr = [round(pwr[0]-0.8 - ((pitch-2)/40. if pitch > 2 else 0), 3),
                   round(pwr[1]-0.8 + ((pitch+2)/40. if pitch < -2 else 0), 3)]
        else: # reduce each by an amount and round to 3dp
            pwr = [round(pwr[0]-0.3 - ((pitch-2)/40. if pitch > 2 else 0), 3),
                   round(pwr[1]-0.3 + ((pitch+2)/40. if pitch < -2 else 0), 3)]
        if pwr[0] < 0: pwr[0] = 0
        if pwr[1] < 0: pwr[1] = 0
        oled.write_lines("{} ->".format(pitch),
                         "({}, {})".format(*[str(float(x)).ljust(5, "0") for x in pwr]))
        time.sleep(0.1)
        run_motors(m0=pwr[0], m1=pwr[0], m2=pwr[1], m3=pwr[1])
    run_motors() # stop all
    time.sleep(0.2)
    return False

def cmd_wconnect():
    global WIIMOTE, ACC_CAL
    if WIIMOTE is None:
        oled.write_line(0, "Connecting WM", 1)
        oled.write_line(1, "Press 1+2", 1)
        try:
            WIIMOTE = cwiid.Wiimote()
            WIIMOTE.led = 1
            WIIMOTE.rpt_mode = cwiid.RPT_ACC \
                             | cwiid.RPT_BTN \
                             | cwiid.RPT_MOTIONPLUS \
                             | cwiid.RPT_STATUS
            ACC_CAL = WIIMOTE.get_acc_cal(cwiid.EXT_NONE)[0]
            oled.write_line(0, "Connected", 1)
            oled.write_line(1, "")
            WIIMOTE.rumble = True
            time.sleep(0.5)
            WIIMOTE.rumble = False
            time.sleep(0.5)
            oled.write_line(0, "Hold the wiimote", 1)
            oled.write_line(1, "horizontally", 1)
            time.sleep(1.5)
        except RuntimeError:
            oled.write_line(0, "Failed to", 1)
            oled.write_line(1, "connect", 1)
            time.sleep(1.5)
    else:
        oled.write_lines(" Disconnect    Y",
                         "  wiimote?     N")
        btns = get_button_int()
        wmbut = get_wmbut_int()
        while btns not in [PFD_BTN_3, PFD_BTN_4] \
          and wmbut not in [cwiid.BTN_A, cwiid.BTN_B]:
            btns = get_button_int()
            wmbut = get_wmbut_int()
        if btns == PFD_BTN_3 or wmbut == cwiid.BTN_A: # 'Y'
            WIIMOTE.led = 0
            WIIMOTE.close()
            WIIMOTE = None
            time.sleep(0.1)
            oled.write_line(0, "Disconnected", 1)
            oled.write_line(1, "")
            time.sleep(1.5)
        else: # 'N'
            time.sleep(0.2)
    return False
def cmd_wcalibrate():
    global ACC_CAL
    if WIIMOTE is None:
        oled.write_line(0, "No wiimote", 1)
        oled.write_line(1, "conencted", 1)
        time.sleep(1.5)
        return False
    options = ["Default",
               "+^-        ",
               "    +^-    ",
               "        +^-"]
    loc = 0
    while True:
        #btns = get_button_int()
        s = WIIMOTE.state
        wmbut, acc = s.get("buttons", 0), s.get("acc", [0,0,0])
        roll, pitch, accel = [x-y for (x,y) in zip(acc, ACC_CAL)]
        oled_write_menu("{: 3},{: 3},{: 3}".format(roll, pitch, accel),
                        options[loc], "^v><")
        if wmbut & (cwiid.BTN_B | cwiid.BTN_UP):
            time.sleep(0.2)
            return False
        elif options == 0 and wmbut & cwiid.BTN_A:
            ACC_CAL = WIIMOTE.get_acc_cal(cwiid.EXT_NONE)[0]
            oled.write_line(1, "Cal -> default!")
            for x in range(10):
                s = WIIMOTE.state
                but, acc = s.get("buttons", 0), s.get("acc", [0,0,0])
                roll, pitch, accel = [x-y for (x,y) in zip(acc, ACC_CAL)]
                oled.write_line(0, "{: 3},{: 3},{: 3}".format(roll, pitch, accel))
                time.sleep(0.1)
        elif options > 0 and wmbut & cwiid.BTN_PLUS:
            ACC_CAL[options-1] += 1
            time.sleep(0.2)
        elif options > 0 and wmbut & cwiid.BTN_MINUS:
            ACC_CAL[options-1] -= 1
            time.sleep(0.2)
        elif wmbut & cwiid.BTN_LEFT:
            loc += 1
            time.sleep(0.2)
        elif wmbut & cwiid.BTN_RIGHT:
            loc -= 1
            time.sleep(0.2)
        loc %= 4
def cmd_wiimote():
    wm_items = [("Connect", cmd_wconnect),
                ("Calibration", cmd_wcalibrate)]
    loc = 0
    while True:
        oled_write_menu("WM menu:", wm_items[loc][0])
        btns = get_button_int()
        wmbut = get_wmbut_int()
        if btns == PFD_BTN_1 or wmbut == cwiid.BTN_RIGHT: # '^'; not &, so must be only one button pressed
            loc -= 1
            time.sleep(0.2)
        elif btns == PFD_BTN_2 or wmbut == cwiid.BTN_LEFT: # 'v'
            loc += 1
            time.sleep(0.2)
        elif btns == PFD_BTN_3 or wmbut in [cwiid.BTN_DOWN, cwiid.BTN_A]: # '>'
            time.sleep(0.2)
            r = wm_items[loc][1]()
            if r is True:
                return True
        elif btns == PFD_BTN_4 or wmbut in [cwiid.BTN_UP, cwiid.BTN_B]: # '<'
            return False
        loc %= len(wm_items)

def cmd_aexit():
    return True
def cmd_ashutdown(): # set CMD to shutdown and then quit
    global EXIT_CMD
    EXIT_CMD = ["sudo","shutdown","-h","now"]
    return True
def cmd_areboot(): # set CMD to reboot and then quit
    global EXIT_CMD
    EXIT_CMD = ["sudo","shutdown","-r","now"]
    return True
def cmd_admin():
    admin_items = [("Exit", cmd_aexit),
                   ("Shutdown", cmd_ashutdown),
                   ("Reboot", cmd_areboot)]
    loc = 0
    while True:
        oled_write_menu("Admin menu:", admin_items[loc][0])
        btns = get_button_int()
        wmbut = get_wmbut_int()
        if btns == PFD_BTN_1 or wmbut == cwiid.BTN_RIGHT: # '^'; not &, so must be only one button pressed
            loc -= 1
            time.sleep(0.2)
        elif btns == PFD_BTN_2 or wmbut == cwiid.BTN_LEFT: # 'v'
            loc += 1
            time.sleep(0.2)
        elif btns == PFD_BTN_3 or wmbut in [cwiid.BTN_DOWN, cwiid.BTN_A]: # '>'
            time.sleep(0.2)
            r = admin_items[loc][1]()
            if r is True:
                return True
        elif btns == PFD_BTN_4 or wmbut in [cwiid.BTN_UP, cwiid.BTN_B]: # '<'
            return False
        loc %= len(admin_items)

def cmd_tmotors():
    no = 0
    while True:
        state = list(MOTOR_PWM_THREAD_speeds[0])
        if no == 0:
            oled_write_menu("Test motors:", "Back", "^v <")
        else:
            oled_write_menu("Test motors:",
                            "Motor {} - {}".format(no, float(state[no-1])),
                            "^v{}{}".format(" " if state[no-1]>=1 else "+",
                                            " " if state[no-1]<=0 else "-"))
        btns = get_button_int()
        wmbut = get_wmbut_int()
        if btns == PFD_BTN_1 or wmbut == cwiid.BTN_RIGHT: # '^'; not &, so must be only one button pressed
            no -= 1
            time.sleep(0.2)
        elif btns == PFD_BTN_2 or wmbut == cwiid.BTN_LEFT: # 'v'
            no += 1
            time.sleep(0.2)
        elif (btns == PFD_BTN_3 or wmbut == cwiid.BTN_PLUS) \
         and no > 0 and state[no-1]<1: # '+'
            state[no-1] += 0.2
            if state[no-1] > 1: state[no-1] = 1
            state[no-1] = round(state[no-1], 1)
            run_motors(*state)
            time.sleep(0.2)
        elif (btns == PFD_BTN_4 or wmbut == cwiid.BTN_MINUS) \
         and no > 0 and state[no-1]>0: # '-'
            state[no-1] -= 0.2
            if state[no-1] < 0: state[no-1] = 0
            state[no-1] = round(state[no-1], 1)
            run_motors(*state)
            time.sleep(0.2)
        elif (btns == PFD_BTN_4 and no == 0) \
          or wmbut == cwiid.BTN_B: # '<'
            run_motors() # stop all
            time.sleep(0.2)
            return False
        no %= 5
def cmd_tleds():
    oled.write_line(1, "")
    for x in range(0, 16):
        oled.write_line(0, ("."*(x//4+1)).ljust(4), 1)
        set_led_int(x % 16)
        time.sleep(0.4)
    set_led_int(0)
    return False
def cmd_twiimote():
    if WIIMOTE is None:
        oled.write_line(0, "No wiimote", 1)
        oled.write_line(1, "conencted", 1)
        time.sleep(1.5)
    else:
        oled.write_line(0, "LEDs", 1)
        oled.write_line(1, "")
        for x in range(0, 16):
            WIIMOTE.led = x
            time.sleep(0.2)
        WIIMOTE.led = 1
        time.sleep(0.2)
        oled.write_line(0, "Rumble", 1)
        for x in range(0, 4):
            WIIMOTE.rumble = True
            time.sleep(0.5)
            WIIMOTE.rumble = False
            time.sleep(0.5)
        oled.write_line(0, "Accel & buttons", 1)
        oled.write_line(1, "(HOME to stop)", 1)
        time.sleep(1.5)
        s = WIIMOTE.state
        while not s.get("buttons", 0) & cwiid.BTN_HOME:
            s = WIIMOTE.state
            acc = s.get("acc", [0,0,0])
            roll, pitch, accel = [x-y for (x,y) in zip(acc, ACC_CAL)]
            sstr = "{0:3}, {1:3}, {2:3}".format(roll, pitch, accel)
            oled.write_line(0, sstr)
            oled.write_line(1, bin(s.get("buttons", 0))[2:].rjust(13, "0"))
            time.sleep(0.1)
        oled.clear_display()
        time.sleep(0.2)
    return False
def cmd_test():
    test_items = [("Motors", cmd_tmotors),
                  ("LEDs", cmd_tleds),
                  ("Wiimote", cmd_twiimote)]
    loc = 0
    while True:
        oled_write_menu("Test menu:", test_items[loc][0])
        btns = get_button_int()
        wmbut = get_wmbut_int()
        if btns == PFD_BTN_1 or wmbut == cwiid.BTN_RIGHT: # '^'; not &, so must be only one button pressed
            loc -= 1
            time.sleep(0.2)
        elif btns == PFD_BTN_2 or wmbut == cwiid.BTN_LEFT: # 'v'
            loc += 1
            time.sleep(0.2)
        elif btns == PFD_BTN_3 or wmbut in [cwiid.BTN_DOWN, cwiid.BTN_A]: # '>'
            time.sleep(0.2)
            r = test_items[loc][1]()
            if r is True:
                return True
        elif btns == PFD_BTN_4 or wmbut in [cwiid.BTN_UP, cwiid.BTN_B]: # '<'
            return False
        loc %= len(test_items)

try:
    oled.write_lines("Running...")
    for x in range(0, 3):
        set_led_int(8)
        time.sleep(0.5)
        set_led_int(0)
        time.sleep(0.5)

    menu_items = [("Run", cmd_run),
                  ("Test", cmd_test),
                  ("Wiimote", cmd_wiimote),
                  ("Admin", cmd_admin)]
    menu_loc = 0
    while True:
        oled_write_menu("Main menu:", menu_items[menu_loc][0], "^v> ")
        btns = get_button_int()
        wmbut = get_wmbut_int()
        if btns == PFD_BTN_1 or wmbut == cwiid.BTN_RIGHT: # '^'; not &, so must be only one button pressed
            menu_loc -= 1
            time.sleep(0.2)
        elif btns == PFD_BTN_2 or wmbut == cwiid.BTN_LEFT: # 'v'
            menu_loc += 1
            time.sleep(0.2)
        elif btns == PFD_BTN_3 or wmbut in [cwiid.BTN_DOWN, cwiid.BTN_A]: # '>'
            time.sleep(0.2)
            r = menu_items[menu_loc][1]()
            if r is True:
                break
        menu_loc %= len(menu_items)
        
    oled.write_line(0, "Goodbye!", 1)
    oled.write_line(1, "")
    set_led_int(15)
    time.sleep(2)
finally:
    logging.info("Stopping")
    oled.cleanup()
    if piface:
        run_motors()
        set_led_int(0)
        pfd.deinit()
    if WIIMOTE is not None:
        WIIMOTE.led = 0
        WIIMOTE.close()
    if EXIT_CMD is not None:
        subprocess.call(EXIT_CMD)
