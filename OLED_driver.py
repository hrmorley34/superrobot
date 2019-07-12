import RPi.GPIO as GPIO
import time
import subprocess

OLED_RS = 18
OLED_RW = 23
OLED_E  = 24
OLED_D4 = 17
OLED_D5 = 27
OLED_D6 = 22
OLED_D7 = 25

LCD_WIDTH = 16                     # Max line char width
LCD_CHR = True
LCD_CMD = False

LCD_LINE_1 = 0x80                      # LCD RAM address for the 1st line
LCD_LINE_2 = 0xC0                      # LCD RAM address for the 2nd line

# Timing constants for low level write operations
# NOTE: Enable cycle time must be at least 1 microsecond
# NOTE2: Actually, these can be zero and the LCD will typically still work OK
EDEL_TAS =  0.00001                 # Address setup time (TAS)
EDEL_PWEH = 0.00001                 # Pulse width of enable (PWEH)
EDEL_TAH =  0.00001                 # Address hold time (TAH)

# Timing constraints for initialisation steps - IMPORTANT!
# Note that post clear display must be at least 6.2ms for OLEDs, as opposed
# to only 1.4ms for HD44780 LCDs. This has caused confusion in the past.
DEL_INITMID = 0.01                  # middle of initial write (min 4.1ms)
DEL_INITNEXT = 0.0002               # post ssecond initial write (min 100ns)
DEL_POSTCLEAR = 0.01                # post clear display step (busy, min 6.2ms)

def init():
    # Configure the GPIO to drive the LCD display correctly
    GPIO.setmode(GPIO.BCM)             # Use BCM GPIO numbers

    # setup all output pins for driving LCD display
    GPIO.setup(OLED_D4, GPIO.OUT)     # DB4
    GPIO.setup(OLED_D5, GPIO.OUT)     # DB5
    GPIO.setup(OLED_D6, GPIO.OUT)     # DB6
    GPIO.setup(OLED_D7, GPIO.OUT)     # DB7
    GPIO.setup(OLED_E, GPIO.OUT)      # E
    GPIO.setup(OLED_RW, GPIO.OUT)     # E
    GPIO.setup(OLED_RS, GPIO.OUT)     # RS

    GPIO.output(OLED_RW, False)       # Write only mode

    # Initialise display into 4 bit mode, using recommended delays
    lcd_byte(0x33,LCD_CMD, DEL_INITNEXT, DEL_INITMID)
    lcd_byte(0x32,LCD_CMD, DEL_INITNEXT)

    # Now perform remainder of display init in 4 bit mode - IMPORTANT!
    # These steps MUST be exactly as follows, as OLEDs in particular are rather fussy
    lcd_byte(0x28,LCD_CMD, DEL_INITNEXT)    # two lines and correct font
    lcd_byte(0x08,LCD_CMD, DEL_INITNEXT)    # display OFF, cursor/blink off
    lcd_byte(0x01,LCD_CMD, DEL_POSTCLEAR)   # clear display, waiting for longer delay
    lcd_byte(0x06,LCD_CMD, DEL_INITNEXT)    # entry mode set

    # Extra steps required for OLED initialisation (no effect on LCD)
    lcd_byte(0x17,LCD_CMD, DEL_INITNEXT)    # character mode, power on


    # Now turn on the display, ready for use - IMPORTANT!
    lcd_byte(0x0C,LCD_CMD, DEL_INITNEXT)    # display on, cursor/blink off

def lcd_string(message):
    # Send string to display
    message = message.ljust(LCD_WIDTH," ") 

    for i in range(LCD_WIDTH):
        lcd_byte(ord(message[i]),LCD_CHR)

def lcd_byte(byteVal, mode, post_delay = 0, mid_delay = 0):
    # convert incoming value into 8 bit array, padding as required
    bits = bin(byteVal)[2:].zfill(8)

    # generate an array of pin numbers to write out
    lcdPins = [OLED_D7, OLED_D6, OLED_D5, OLED_D4]

    # set mode = True  for character, False for command
    GPIO.output(OLED_RS, mode) # RS

    # Output the four High bits
    for i in range(4):
        GPIO.output(lcdPins[i], int(bits[i]))

    # Toggle 'Enable' pin, wrapping with minimum delays
    time.sleep(EDEL_TAS)   
    GPIO.output(OLED_E, True) 
    time.sleep(EDEL_PWEH)
    GPIO.output(OLED_E, False) 
    time.sleep(EDEL_TAH)     

    # Wait for extra mid delay if specified (special case)
    if mid_delay > 0:
        time.sleep(mid_delay)

    # Output the four Low bits
    for i in range(4,8):
        GPIO.output(lcdPins[i-4], int(bits[i]))

    # Toggle 'Enable' pin, wrapping with minimum delays
    time.sleep(EDEL_TAS)   
    GPIO.output(OLED_E, True) 
    time.sleep(EDEL_PWEH)
    GPIO.output(OLED_E, False) 
    time.sleep(EDEL_TAH)   

    # Wait for extra post delay if specified (covers busy period)
    if post_delay > 0:
        time.sleep(post_delay)

def write_line(line=0, text="", just=0):
    "Just: 0-left; 1-centre; 2-right"
    if line == 0:
        lcd_byte(LCD_LINE_1, LCD_CMD)
    elif line == 1:
        lcd_byte(LCD_LINE_2, LCD_CMD)
    else:
        raise IndexError("Bad no. of lines")
    if just == 1:
        text = text.center(LCD_WIDTH)
    elif just == 2:
        text = text.rjust(LCD_WIDTH)
    lcd_string(text)

def write_lines(*lines):
    for no, text in enumerate(lines, 0):
        write_line(no, text)

def clear_display():
    for line in range(0, 2):
        write_line(line, "")

def main():
    # Initialise GPIO port and display
    init()

    # Send some text
    show_model()

    time.sleep(3) # 3 second delay

    # Send some more text
    show_ip()

    time.sleep(3)

    clear_display()

def run_cmd(cmd):
    p = subprocess.Popen(cmd, shell=True, stdout=subprocess.PIPE)
    output = p.communicate()[0]
    return output.decode()

def get_ip():
    return run_cmd("ip addr show wlan0 | grep inet | awk '{print $2}' | cut -d/ -f1")
def get_model():
    return run_cmd("cat /proc/device-tree/model").rstrip("\x00")

def show_model():
    model = get_model()
    print(model)
    model = model.split(" Model"); model[1] = "Model"+model[1]
    write_lines(*model)
def show_ip():
    ipaddr = get_ip()
    ipv4 = ipaddr.split('\n')
    write_lines("IP:",
                ipv4[0])
    print(ipv4[0])

def cleanup():
    clear_display()
    GPIO.cleanup()

if __name__ == '__main__':
    try:
        main()
    finally:
        cleanup()
