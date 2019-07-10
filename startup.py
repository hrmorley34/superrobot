#!/usr/bin/python3.5
import OLED_driver as oled
import pifacedigitalio as pfd
import subprocess
import logging
import time
import re

logging.basicConfig(filename="/home/pi/startup.log",
                    level=logging.DEBUG,
                    format="%(asctime)s: %(levelname)s: %(message)s",
                    datefmt='%Y-%m-%d %H:%M:%S')

logging.info("Started")

# -- get system information --
def run_cmd(cmd):
    p = subprocess.Popen(cmd, shell=True, stdout=subprocess.PIPE)
    output = p.communicate()[0]
    return output.decode()

def get_ipl_data(ipl):
    IPL_RE = re.compile(r"^ *inet( ([\d\.]+)|6 ([\da-fA-F\:]+))/(\d+) (brd ([\d\.]+|[\da-fA-F:]+) )?scope (\w+) (\w*)$")
    m = IPL_RE.match(ipl)
    if m is None:
        return None

    if m.group(1)[0] == "6": ipv=6; addr=m.group(3)
    else: ipv=4; addr=m.group(2)
    masksize = m.group(4)
    if m.group(5) is None: brd=None
    else: brd=m.group(6)
    scope = m.group(7)
    scopename = m.group(8)

    return {"ipv":ipv, "addr":addr, "masksize":masksize,
            "brd":brd, "scope":scope, "scopename":scopename}
def get_ips():
    ips = run_cmd("ip addr | grep inet").splitlines(False)
    ips = [get_ipl_data(ipl) for ipl in ips]
    return ips
def get_good_ips():
    ips = get_ips()
    ips = filter(lambda x: re.match("^(eth|wlan)\d+$", x["scopename"]), ips)
    return list(ips)

def get_model():
    return run_cmd("cat /proc/device-tree/model").rstrip("\x00")

def get_git_revision():
    return run_cmd("git rev-parse --short HEAD").rstrip("\x00")
# ----------------------------

oled.init()
try:
    pfd.init()
    piface = True
except pfd.NoPiFaceDigitalDetectedError:
    piface = False

try:
    logging.debug("OLED: 'Running in rc.local'")
    oled.write_line(0, "Running in", 1)
    oled.write_line(1, "rc.local", 1)
    if piface:
        for x in range(3):
            pfd.digital_write(7, 1)
            time.sleep(0.5)
            pfd.digital_write(7, 0)
            time.sleep(0.5)
    else:
        time.sleep(3)

    logging.debug("OLED: Displaying code revision")
    git_rev = get_git_revision()
    oled.write_line(0, "Code revision:", 1)
    oled.write_line(1, git_rev, 1)
    time.sleep(2)

    logging.debug("OLED: Displaying model")
    model = get_model()
    model = model.replace(" Model ", "\nModel ") # split onto two lines in approx. the middle
    if len(model.splitlines()) == 1:
        model = model[0:oled.LCD_WIDTH].strip()+"\n"+model[oled.LCD_WIDTH:].strip()
    oled.write_lines(*model.splitlines(False)) # show model
    if piface:
        for x in range(3):
            pfd.digital_write(7, 1)
            time.sleep(0.5)
            pfd.digital_write(7, 0)
            time.sleep(0.5)
    else:
        time.sleep(3)

    logging.debug("OLED: Displaying IPs")
    iplist = get_ips()
    iplist = list(filter(lambda i:i["scope"] not in ["host", "link"], iplist)) # ignore 'host' (127.0.0.1, ::1) and 'link' (useless IPv6)
    if len(iplist): # if there are some IPs
        oled.write_line(0, "IPs:")
        oled.write_line(1, "")
        time.sleep(1)

        for ip in iplist:
            sc,scn,addr = ip["scope"],ip["scopename"],ip["addr"] # get important info
            logging.debug("OLED: IPs: "+sc+" ('"+scn+"') - "+addr) # log currently printing IP
            if scn: iple = scn#+" ("+sc+")"
            else: iple = sc
            ipl = "IPs: "+iple
            oled.write_line(0, ipl)
            oled.write_line(1, addr)
            if max((len(addr),len(ipl))) > oled.LCD_WIDTH: # at least one line is too long
                time.sleep(1.5)
                offset = 1
                while max((len(addr),len(ipl)))-offset >= oled.LCD_WIDTH: # until it is all visible
                    if len("IPs: "+iple[offset:]) >= oled.LCD_WIDTH: # until whole line is visible, 'IPs: ' stays still
                        oled.write_line(0, "IPs: "+iple[offset:])
                    if len(addr[offset:]) >= oled.LCD_WIDTH: # until whole line is visible
                        oled.write_line(1, addr[offset:])
                    time.sleep(0.4)
                    offset += 1
                time.sleep(1.5)
            else: # all fits on display
                time.sleep(3)
    else:
        oled.write_line(0, "IPs:")
        oled.write_line(1, "None")
        time.sleep(3)

    #oled.write_line(0, "", 1)
    #oled.write_line(1, "", 1)
    #time.sleep(3)
finally:
    logging.info("Stopping")
    oled.cleanup()
    if piface:
        pfd.deinit()
