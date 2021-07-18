import os, sys, re
import fcntl, termios, struct
try:
    from StringIO import StringIO
except ImportError:
    from io import StringIO

if os.isatty(sys.stdout.fileno()):
    # Unpack the current terminal width/height
    data = fcntl.ioctl(sys.stdout.fileno(), termios.TIOCGWINSZ, '1234')
    HEIGHT, WIDTH = struct.unpack('hh',data)

BLACK, RED, GREEN, YELLOW, BLUE, MAGENTA, CYAN, WHITE = range(8)

def format(fg=None, bg=None, bright=False, bold=False, dim=False, reset=False):
    # Manually derived from http://en.wikipedia.org/wiki/ANSI_escape_code#Codes
    codes = []
    if reset: codes.append("0")
    else:
        if not fg is None: codes.append("3%d" % (fg))
        if not bg is None:
            if not bright: codes.append("4%d" % (bg))
            else: codes.append("10%d" % (bg))
        if bold: codes.append("1")
        elif dim: codes.append("2")
        else: codes.append("22")
    return "\033[%sm" % (";".join(codes))


def indent_wrap(message, indent=0, width=80):
    wrap_area = width - indent
    messagebuf = StringIO()
    current = 0
    while current < len(message):
        next = min(current + wrap_area, len(message))
        messagebuf.write(message[current:next])
        if next < len(message):
            messagebuf.write("\n%s" % (" " * indent))
        current = next
    return messagebuf.getvalue()


LAST_USED = [RED,GREEN,YELLOW,BLUE,MAGENTA,CYAN,WHITE]
KNOWN_TAGS = {
    "dalvikvm": BLUE,
    "Process": BLUE,
    "ActivityManager": CYAN,
    "ActivityThread": CYAN,
}

def allocate_color(tag):
    # This will allocate a unique format for the given tag
    # Since we dont have very many colors, we always keep track of the LRU
    if not tag in KNOWN_TAGS:
        KNOWN_TAGS[tag] = LAST_USED[0]
    color = KNOWN_TAGS[tag]
    LAST_USED.remove(color)
    LAST_USED.append(color)
    return color

def regex_match(line):
    log_type = LOG_TYPE_UNKNOWN
    tagtype, tag, owner, message, time = '','','','',''
    match = retag.match(line)
    if match:
            log_type = LOG_TYPE_BRIEF
            tagtype, tag, owner, message = match.groups()
    else:
        match = retag_threadtime.match(line)
        if match:
            log_type = LOG_TYPE_THREADTIME
            time, owner, tid, tagtype, tag, message = match.groups()
    return log_type, tagtype, tag, owner, message, time

# Don't use it, we need do it one everyline.
def set_log_type(line):
    match = retag.match(line)
    if match:
        LOG_TYPE = LOG_TYPE_BRIEF
    else:
        match = retag_threadtime.match(line)
        if match:
            LOG_TYPE = LOG_TYPE_THREADTIME
        else:
            LOG_TYPE = LOG_TYPE_UNKNOWN

RULES = {
    #re.compile(r"([\w\.@]+)=([\w\.@]+)"): r"%s\1%s=%s\2%s" % (format(fg=BLUE), format(fg=GREEN), format(fg=BLUE), format(reset=True)),
}

TIME_WIDTH = 20
TAGTYPE_WIDTH = 3
TAG_WIDTH = 20
PROCESS_WIDTH = 8 # 8 or -1
HEADER_SIZE = TAGTYPE_WIDTH + 1 + TAG_WIDTH + 1 + PROCESS_WIDTH + 1
HEADER_SIZE_THREADTIME = TAGTYPE_WIDTH + 1 + TAG_WIDTH + 1 + PROCESS_WIDTH + 1 + TIME_WIDTH + 1

TAGTYPES = {
    "V": "%s%s%s " % (format(fg=WHITE, bg=BLACK), "V".center(TAGTYPE_WIDTH), format(reset=True)),
    "D": "%s%s%s " % (format(fg=BLACK, bg=BLUE), "D".center(TAGTYPE_WIDTH), format(reset=True)),
    "I": "%s%s%s " % (format(fg=BLACK, bg=GREEN), "I".center(TAGTYPE_WIDTH), format(reset=True)),
    "W": "%s%s%s " % (format(fg=BLACK, bg=YELLOW), "W".center(TAGTYPE_WIDTH), format(reset=True)),
    "E": "%s%s%s " % (format(fg=BLACK, bg=RED), "E".center(TAGTYPE_WIDTH), format(reset=True)),
}

LOG_TYPE_UNKNOWN = 0
LOG_TYPE_BRIEF = 1
LOG_TYPE_THREADTIME = 2

LOG_TYPE = LOG_TYPE_UNKNOWN

# retag = re.compile("^([A-Z])/([^\(]+)\(([^\)]+)\): (.*)$")
retag = re.compile("^([A-Z])/(.+)\(([^\)]+)\): (.*)$")
retag_threadtime = re.compile("^(.*\ .*)\s+(\d+)\s+(\d+)\s+([A-Z])\s+([^:]+|.+): (.*)$")

# To pick up -d or -e
adb_args = ' '.join(sys.argv[1:])

# If someone is piping in to us, use stdin as input.  if not, invoke adb logcat
if os.isatty(sys.stdin.fileno()):
    input = os.popen("adb %s logcat" % adb_args)
else:
    input = sys.stdin

while True:
    try:
        line = input.readline()
    except KeyboardInterrupt:
        break

    result = regex_match(line)
    if result[0] != LOG_TYPE_UNKNOWN and os.isatty(sys.stdout.fileno()):
        tagtype, tag, owner, message, time = result[1:]
        # print(line)
        # print(tagtype)
        # print(tag)
        # print(owner)
        # print(message)
        linebuf = StringIO()

        if len(time) >0:
            time = time.strip().ljust(TIME_WIDTH)
            linebuf.write("%s%s%s" % (format(fg=CYAN, bright=True), time, format(reset=True)))
        # Center process info
        if PROCESS_WIDTH > 0:
            owner = owner.strip().center(PROCESS_WIDTH)
            # owner = owner.strip().ljust(5)
            linebuf.write("%s%s%s " % (format(fg=BLACK, bg=BLACK, bright=True), owner, format(reset=True)))

        # Right-align tag title and allocate color if needed
        tag = tag.strip()
        color = allocate_color(tag)
        tag = tag[-TAG_WIDTH:].ljust(TAG_WIDTH)
        linebuf.write("%s%s %s" % (format(fg=color, dim=False), tag, format(reset=True)))

        # Write out tagtype colored edge
        if not tagtype in TAGTYPES: break
        linebuf.write(TAGTYPES[tagtype])

        # Insert line wrapping as needed
        if result[0] == LOG_TYPE_BRIEF:
            message = indent_wrap(message, HEADER_SIZE, WIDTH)
        else:
            message = indent_wrap(message, HEADER_SIZE_THREADTIME, WIDTH)
        # Format tag message using rules
        for matcher in RULES:
            replace = RULES[matcher]
            message = matcher.sub(replace, message)

        linebuf.write(message)
        line = linebuf.getvalue()
        print(line)
    else:
        sys.stdout.write(line)
    if len(line) == 0: break
