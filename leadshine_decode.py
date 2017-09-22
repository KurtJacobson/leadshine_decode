#!/usr/bin/env python

#
# MIT License
#
# Copyright (c) 2016, 2017 Kent A. Vander Velden
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in all
# copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
# SOFTWARE.
#
# Kent A. Vander Velden
# kent.vandervelden@gmail.com
# Originally written August 23, 2016


# Important information on timing overhead
#
# On the test system, the overhead to read the samples from the drive was 130ms.
# The overhead is unavoidable, the samples must be read before the next sampling period can be begin.
# Reading the samples alone, not considering sending the request, will require at least 85 ms.
#     (405 bytes / sample read) * (8 bits / byte) / (38400 kilo bits / sec) = 85 ms / sample read
# Graph updates require > 150ms, but this is done between request and response readout, which
# will completely hide the graph update if the sampling time is at least 50ms.
# These are enormous overheads when the sampling duration is 100ms.
#
# There is ~12.8 overhead in sending and recogniznig the response is ready, add this to sample time.
# There is ~112.6ms overhead in receiving the response.
# Regardless of sampling duration, response is always 200 values.
# There is < 0.5ms additional overhead, typically.
# Response readout must be completed before new request is sent, unable to overlap the two.
# Graphing should create no additional overhead, it's performed while waiting for a response
# for "continous" readout.
# Choose a sampling duration that is not dominated by the response readout, but frequent
# enough to have a decent sampling frequency to cover desired event.
# There's only 200 values returned regardless of sampling duration, and a short enough
# duration to allow regular graph updates


import sys
import serial
import time
import matplotlib.pyplot as plt
import numpy as np

# ignore the warning: MatplotlibDeprecationWarning: Using default event loop until function specific to this GUI is implemented
# older systems will not have the warning to ignore
import matplotlib
import warnings

try:
    warnings.filterwarnings("ignore", category=matplotlib.cbook.mplDeprecation)
except AttributeError:
    pass

from timing import *


serial_port = '/dev/ttyUSB0'


ylimits_max = [0, 0]
ylimits = [-1, 1]
position_error_label = 'position error (mm)'
line_error = None
ax = None

def setup_graph(es):
    global line_error
    global ax
    global line_min, line_max, line_avg
    global text_min, text_max, text_avg

    ns = 200

    fig = plt.figure()
    fig.canvas.set_window_title('Following-error')
    ax = fig.add_subplot(1, 1, 1)
    ax.set_xlabel('time (s)')
    ax.set_ylabel(position_error_label)
    # using a linestyle='' and a marker, we have a faster scatter plot than plt.scatter
    line_error, = ax.plot(range(ns), range(ns), linestyle='', marker='.') #, marker='o', markersize=4)
    # scatter plot helps to see the communication overhead, but is many times slower than line plot
    #sct_error = ax.scatter(range(ns), range(ns), marker='o')
    plt.ion()
    plt.show()

    line_min = plt.axhline(y=ylimits_max[0], color='r', linestyle='-')
    line_max = plt.axhline(y=ylimits_max[1], color='r', linestyle='-')
    line_avg = plt.axhline(y=0, color='g', linestyle='-')
    text_min = plt.text(0, 0, '')
    text_max = plt.text(0, 0, '')
    text_avg = plt.text(0, 0, '')
    fe_lims = {'-fe limit': -es.fe_max * es.step_scale, '+fe limit': es.fe_max * es.step_scale}
    for k,v in fe_lims.items():
        plt.axhline(y=v, color='b', linestyle='-')
        plt.text(0, v, k)

    # experimenting with histogram
    if False:
        plt.close()
        fig = plt.figure()


def plot_error(cummul_error, cummul_error_x):
    if cummul_error != []:
        # experimenting with histogram
        if False:
            plt.clf()
            n, bins, patches = plt.hist(cummul_error, 50) #, 50, normed=1, facecolor='green', alpha=0.75)
            plt.ion()
            plt.show()
            plt.pause(0.001)
            return

        #ylimits[0] = min(ylimits[0], (min(cummul_error)/50-1)*50)
        #ylimits[1] = max(ylimits[1], (max(cummul_error)/50+1)*50)
        avg_error = sum(cummul_error) / len(cummul_error)
        #avg_error = np.mean(cummul_error)
        #avg_error = np.median(cummul_error)

        ylimits[0] = min(cummul_error)
        ylimits[1] = max(cummul_error)
        ylimits[0] = min(ylimits[0], ylimits_max[0])
        ylimits[1] = max(ylimits[1], ylimits_max[1])
        ylimits_max[0] = min(ylimits[0], ylimits_max[0])
        ylimits_max[1] = max(ylimits[1], ylimits_max[1])
        ylimits[0] = min(ylimits[0], 0, -abs(ylimits[1]))
        ylimits[1] = max(ylimits[1], 0, abs(ylimits[0]))
        if ylimits[0] == ylimits[1]:
            ylimits[0] = -.01
            ylimits[1] = .01

        if LeadshineEasyServo.zoom_plot_fe_max:
            ylimits[0] = min(ylimits[0], fe_lims['-fe limit'])
            ylimits[1] = max(ylimits[1], fe_lims['+fe limit'])

        #line_error.set_xdata(range(len(error)))
        #line_error.set_ydata(error)
        #line_error.set_data(range(len(error)), error)

        if cummul_error_x == []:
            line_error.set_data(range(len(cummul_error)), cummul_error)
            ax.set_xlim(0, len(cummul_error))
        else:
            cummul_error_x2 = np.asarray(cummul_error_x)
            cummul_error_x2 -= cummul_error_x2[0]

            line_error.set_data(cummul_error_x2, cummul_error)

            #dat = np.vstack((cummul_error_x2, cummul_error)).T
            #print dat.shape, cummul_error_x[-1] - cummul_error_x[0], cummul_error_x2[0], cummul_error_x2[-1]
            #sct_error.set_offsets(dat)

            ax.set_xlim(cummul_error_x2[0], cummul_error_x2[-1])

        line_min.set_data(line_min.get_data()[0], [ylimits_max[0]] * 2)
        line_max.set_data(line_min.get_data()[0], [ylimits_max[1]] * 2)
        line_avg.set_data(line_avg.get_data()[0], [avg_error] * 2)
        #fig.canvas.draw()
        ax.set_ylim(ylimits[0] * 1.05, ylimits[1] * 1.05)

        for obj, v in zip([text_min, text_max, text_avg], [ylimits_max[0], ylimits_max[1], avg_error]):
            obj.set_y(v)
            obj.set_text('{0:.3f} mm'.format(v))

        #time.sleep(0.05)
        #plt.pause(0.0001)
        plt.pause(0.001)


class LeadshineEasyServo:
    zoom_plot_fe_max = False

    # retain only the last X seconds of data when graphing
    last_x_sec = 5


    def __init__(self):
        self.serial_port = None
        # scaling value to convert following error to millimeters
        # 4000 encoder pulses per revolution, and 5mm pitch ballscrew
        # updated after reading parameters
        self.leadscrew_pitch = 5.
        self.step_scale = 1. / 4000. * self.leadscrew_pitch

        # maximum allowed following-error
        # updated after reading parameters
        self.fe_max = 1000


    @staticmethod
    def modbus_crc(dat):
        crc = 0xffff

        for c in dat:
            crc ^= c

            for i in range(8):
                if (crc & 0x00001):
                    crc >>= 1
                    crc ^= 0xa001
                else:
                    crc >>= 1

        crc = bytearray([0x00ff & crc, (0xff00 & crc) >> 8])
        return crc


    def check_crc(shelf, dat):
        msg = dat[:-2]
        crc1 = dat[-2:]
        crc2 = LeadshineEasyServo.modbus_crc(msg)
        if crc1 != crc2:
            print 'failed crc', map(hex, crc1), map(hex, crc2)
        return crc1 == crc2


    def check_header(shelf, dat): # ct = 0x03 or 0x06
        header = dat[:2]
        known_headers = [bytearray([0x01, 0x03]), bytearray([0x01, 0x06])]
        return header in known_headers


    def read_response(self, expected_len=-1):
        # read using a sliding window to find the start
        v = self.ser.read(1)
        while True:
            v += self.ser.read(1)
            if len(v) < 2:
                return None
            if v in ['\x01\x03', '\x01\x06']:
                break
            else:
                print 'read_response(): discarding:', hex(bytearray(v)[0])
                v = v[1:]

        # read length (number of bytes) and append to message
        # this does not appear to actually be the length
        n = self.ser.read(1)
        if len(n) == 0:
            print 'read_response(): zero length read'
            return None
        v += n
        n = bytearray(n)
        n = int(n[0])

        # read remainder of message and checksum
        v += self.ser.read(expected_len - len(v))
        if expected_len != -1 and len(v) != expected_len:
            print 'read_response(): n != expected_len', n, expected_len
            return None
        v = bytearray(v)

        #print map(hex, v)

        if not self.check_header(v):
            print 'read_response(): failed header', map(hex, v)
            sys.exit(1)
        if not self.check_crc(v):
            print 'read_response(): failed crc', map(hex, v)

        v = v[3:-2]

        return v


    def send_introduction(self):
        introduction = [0x01, 0x03, 0x00, 0xFD, 0x00, 0x01]
        introduction = bytearray(introduction) # 0x15, 0xFA
        introduction += LeadshineEasyServo.modbus_crc(introduction)

        n = self.ser.write(introduction)
        if n != len(introduction):
            print 'send_introduction(): introduction was truncated'
            sys.exit(1)

        response = self.read_response(7)

        return response[-1] == 0x82


    def run_cmd(self, cmd, do_read_response=True, expected_len=-1):
        if cmd == None:
            time.sleep(.1)
            return None

        desc, default_v, rng, cmd = cmd
        cmd = bytearray(cmd)
        cmd += LeadshineEasyServo.modbus_crc(cmd)

        n = self.ser.write(cmd)
        if n != len(cmd):
            print 'run_cmd(): incomplete serial write', cmd
            sys.exit(1)

        if not do_read_response:
            return None

        if expected_len == -1:
            ct = cmd[1]
            if ct == 0x03:
                response = self.read_response(7)
            elif ct == 0x06:
                response = self.read_response(8)
            else:
                print 'run_cmd(): not sure what to do'
                sys.exit(1)

        if response == None:
            print 'run_cmd(): empty_response'
            return None

        if ct == 0x03:
            if len(response) != 2:
                print 'run_cmd(): unexpected response1 len', response

            #d = response[0] << 8 | response[1]
            #print desc, n, map(hex, response), hex(d), d
        elif ct == 0x06:
            #if len(response) != 4:
            if len(response) != 3:
                print 'run_cmd(): unexpected response2 len ', len(response), 'to', map(hex, cmd), map(hex, response)
                return None

            #d1 = response[0] << 8 | response[1]
            #d2 = response[2] << 8 | response[3]
            #print desc, n, map(hex, response), hex(d1), d1, hex(d2), d2

        return response


    def run_cmds(self, cmds, print_response=False):
        rv = {}

        for cmd in cmds:
            response = self.run_cmd(cmd)

            if print_response:
                if len(response) != 2:
                    print 'unexpected length for', cmd
                    continue
                d = response[0] << 8 | response[1]
                print cmd[0], d
                rv[cmd[0]] = d

        return rv


    def read_parameters(self):
        # combined commands seen on parameters, motor settings, and inputs/outputs screens

        cmds = [
          ['current loop kp',                 641,   [0, 32766], [0x01, 0x03, 0x00, 0x00, 0x00, 0x01]],
          ['current loop ki',                 291,   [0, 32766], [0x01, 0x03, 0x00, 0x01, 0x00, 0x01]],
          ['pulses / revolution',            4000, [200, 51200], [0x01, 0x03, 0x00, 0x0E, 0x00, 0x01]],
          ['encoder resolution (ppr)',       4000, [200, 51200], [0x01, 0x03, 0x00, 0x0F, 0x00, 0x01]],
          ['position error limit (pulses)',  1000,   [0, 65535], [0x01, 0x03, 0x00, 0x12, 0x00, 0x01]],
          ['position loop kp',               2000,   [0, 32767], [0x01, 0x03, 0x00, 0x06, 0x00, 0x01]],
          ['position loop ki',                500,   [0, 32767], [0x01, 0x03, 0x00, 0x07, 0x00, 0x01]],
          ['position loop kd',                200,   [0, 32767], [0x01, 0x03, 0x00, 0x08, 0x00, 0x01]],
          ['position loop kvff',               30,   [0, 32767], [0x01, 0x03, 0x00, 0x0D, 0x00, 0x01]],
          ['holding current (%)',              40,     [0, 100], [0x01, 0x03, 0x00, 0x50, 0x00, 0x01]],
          ['open-loop current (%)',            50,     [0, 100], [0x01, 0x03, 0x00, 0x51, 0x00, 0x01]],
          ['closed-loop current (%)',         100,     [0, 100], [0x01, 0x03, 0x00, 0x52, 0x00, 0x01]],
          ['anti-interference time',         1000,    [0, 1000], [0x01, 0x03, 0x00, 0x53, 0x00, 0x01]],
          ['enable control',                    1,       [0, 1], [0x01, 0x03, 0x00, 0x96, 0x00, 0x01]], # 0 = high level, 1 = low level
          ['fault output',                      0,       [0, 1], [0x01, 0x03, 0x00, 0x97, 0x00, 0x01]], # 0 = active high, 1 = active low
          ['filtering enable',                  0,       [0, 1], [0x01, 0x03, 0x00, 0x54, 0x00, 0x01]], # 0 = disabled, 1 = enabled
          ['filtering time (us)',           25600,  [50, 25600], [0x01, 0x03, 0x00, 0x55, 0x00, 0x01]],
          ['reserved (pulse mode)?',            0,       [0, 1], [0x01, 0x03, 0x00, 0x4F, 0x00, 0x01]], # reported value = 0
          ['pulse active edge',                 4,       [4, 6], [0x01, 0x03, 0x00, 0xFF, 0x00, 0x01]], # 4 = rising, 6 = falling
          ['reserved (direction)?',           130,       [0, 1], [0x01, 0x03, 0x00, 0xFD, 0x00, 0x01]], # reported value = 130
          ['reserved (bandwidth)?',             1,       [0, 1], [0x01, 0x03, 0x00, 0x90, 0x00, 0x01]], # reported value = 1
          ['current loop auto-configuration?',  1,       [0, 1], [0x01, 0x03, 0x00, 0x40, 0x00, 0x01]]
        ]

        rv = self.run_cmds(cmds, True)

        fe_max = rv['position error limit (pulses)']
        ppr = rv['pulses / revolution']
        step_scale = 1. / ppr * self.leadscrew_pitch
        print
        print 'Following-error limit updated to', fe_max, 'mm'
        print 'Step scale factor updated to', step_scale, 'mm/step'


    def scope_setup(self):
        # see notes at top of file regarding timing limitations and overhead

        cmds = [
          # the last word sets the duration in 10ms increments, i.e. 0x000a = 10 -> 10 * 10ms = 100ms
          #['scope_setup1', None, None, [0x01, 0x06, 0x00, 0xD0, 0x01, 0x2C]], # 3000 ms sampling (~3097 ms total)
          #['scope_setup1', None, None, [0x01, 0x06, 0x00, 0xD0, 0x00, 0x64]], # 1000 ms sampling (~1119 ms total)
          #['scope_setup1', None, None, [0x01, 0x06, 0x00, 0xD0, 0x00, 0x28]], # 400 ms sampling (~527 ms total)
          ['scope_setup1', None, None, [0x01, 0x06, 0x00, 0xD0, 0x00, 0x14]], # 200 ms sampling (~328 ms total)
          #['scope_setup1', None, None, [0x01, 0x06, 0x00, 0xD0, 0x00, 0x0a]], # 100 ms sampling (~230 ms total)
          ['scope_setup2', None, None, [0x01, 0x06, 0x00, 0x41, 0x00, 0x01]],
          ['scope_setup3', None, None, [0x01, 0x06, 0x00, 0x42, 0x00, 0x00]]
        ]

        #'k4', None, None, [0x01, 0x06, 0x00, 0xD0, 0x00, 0x64]], # 1000 ms

        self.run_cmds(cmds)


    def scope_exec(self, repeat=-1):
        cmds = [
          ['scope_begin', None, None, [0x01, 0x06, 0x00, 0x14, 0x00, 0x01]], # begin
          ['scope_check', None, None, [0x01, 0x03, 0x00, 0xDA, 0x00, 0x01]], # repeat until response[-1] == 0x02, waiting 100 millisec or so between
          ['scope_end',   None, None, [0x01, 0x03, 0x00, 0x14, 0x00, 0xc8]]  # end
        ]

        # there are 200 samples regardless of sampling duration, each reading is a word
        ns = 200

        cummul_error = []
        cummul_error_x = []

        t1 = timing() # request through response
        t2 = timing() # response only
        t3 = timing() # update to update
        t4 = timing() # graphing
        timing.enable()

        # see notes at top of file regarding timing limitations and overhead
        while repeat == -1 or repeat > 0:
            # request sampling of data of configured duration
            t1.start()
            rt_s = time.time()
            self.run_cmd(cmds[0])

            # overlap the sampling with the updating of the graph
            t4.start()
            plot_error(cummul_error, cummul_error_x)
            t4.lap()

            # loop until the response indicates the sampling is complete
            while True:
                time.sleep(.001)
                response = self.run_cmd(cmds[1])
                if response == None:
                    print 'scope_exec(): empty_response'
                    continue
                #print 'R', len(response), map(hex, response)

                # check if sampling is complete
                if response[-1]  == 0x02:
                    rt_e = time.time()
                    self.run_cmd(cmds[2], False)
                    t1.lap()

                    # each reading is a word, so ns*2 bytes to read
                    t2.start()
                    msg = self.read_response(3+ns*2+2)
                    t2.lap()

                    # starting the new sampling period immediately does not decrease the perceived overhead
                    #run_cmd(ser, cmds[0])
                    #print time.time()
                    #continue

                    # error = []
                    def h(v):
                        v = (v[0] << 8) | (v[1])
                        if v & 0x8000:
                            v = -(v ^ 0xffff)
                        return v
                    # join bytes of each word, and then convert to desired units
                    error = map(h, zip(msg[0::2], msg[1::2]))
                    error = map(lambda x: x * self.step_scale, error)
                    #print time.time(), dt, len(error), error
                    t3.lap()
                    if timing.enabled:
                        print 'last,min,avg,max', 'req:', t1, 'resp:', t2, 'total:', t3, 'graph:', t4

                    cummul_error += error
                    cummul_error_x += list(np.linspace(rt_s, rt_e, num=ns, endpoint=True))
                    # remove data from the front of the buffers until only the last_x seconds remain
                    while cummul_error_x[-1] - cummul_error_x[0] > LeadshineEasyServo.last_x_sec:
                        cummul_error = cummul_error[100:]
                        cummul_error_x = cummul_error_x[100:]

                    break

            if repeat >= 0:
                repeat -= 1


    def motion_test(self):
        cmds = [
          ['velocity (rpm)',       None, None, [0x01, 0x03, 0x00, 0x16, 0x00, 0x01]],
          ['acceleration (r/s/s)', None, None, [0x01, 0x03, 0x00, 0x15, 0x00, 0x01]],
          ['intermission (ms)?',   None, None, [0x01, 0x03, 0x00, 0x1B, 0x00, 0x01]],
          ['distance?',            None, None, [0x01, 0x03, 0x00, 0x19, 0x00, 0x01]],
          ['trace time?',          None, None, [0x01, 0x03, 0x00, 0x18, 0x00, 0x01]],
          ['motion direction?',    None, None, [0x01, 0x03, 0x00, 0x1A, 0x00, 0x01]],
          ['motion mode?',         None, None, [0x01, 0x03, 0x00, 0x1C, 0x00, 0x01]]
        ]

        # f1 2 ['0x0', '0x3c'] 0x3c 60
        # f2 2 ['0x7', '0xd0'] 0x7d0 2000
        # f3 2 ['0x0', '0x64'] 0x64 100
        # f4 2 ['0x0', '0x1'] 0x1 1
        # f5 2 ['0x0', '0x64'] 0x64 100
        # f6 2 ['0x0', '0x1'] 0x1 1
        # f7 2 ['0x0', '0x1'] 0x1 1

        # read motion test parameters
        self.run_cmds(cmds)

        cmds = [
          ['motion_test1',   None, None, [0x01, 0x06, 0x00, 0x15, 0x07, 0xD0]],
          ['motion_test2',   None, None, [0x01, 0x06, 0x00, 0x18, 0x00, 0x64]],
          ['motion_test3',   None, None, [0x01, 0x06, 0x00, 0x1B, 0x00, 0x64]],
          ['motion_test4',   None, None, [0x01, 0x06, 0x00, 0x19, 0x00, 0x01]],
          ['motion_test5',   None, None, [0x01, 0x06, 0x00, 0x16, 0x00, 0x3C]],

          ['motion_test6',   None, None, [0x01, 0x06, 0x00, 0xD0, 0x00, 0x64]], # identical to scope setup
          ['motion_test7',   None, None, [0x01, 0x06, 0x00, 0x41, 0x00, 0x01]], # identical to scope setup
          ['motion_test8',   None, None, [0x01, 0x06, 0x00, 0x42, 0x00, 0x00]], # identical to scope setup

          ['motion_test9',   None, None, [0x01, 0x06, 0x00, 0x09, 0x00, 0x01]] # unique
        ]

        # execute motion test
        self.run_cmds(cmds)
        self.scope_exec()


    def current_test(self):
        cmds = [
          ['current_test1',    None, None, [0x01, 0x06, 0x00, 0x00, 0x02, 0x85]], #        -16.32us        1.779ms [0x01, 0x06, 0x00, 0x00, 0x02, 0x85, 0x49, 0x09]
          ['current_test2',    None, None, [0x01, 0x06, 0x00, 0x01, 0x01, 0x25]], #        52.85ms 54.64ms         [0x01, 0x06, 0x00, 0x01, 0x01, 0x25, 0x18, 0x41]
          ['current_test3',    None, None, [0x01, 0x06, 0x00, 0x04, 0x02, 0x00]], #        115.3ms 117.2ms         [0x01, 0x06, 0x00, 0x04, 0x02, 0x00, 0xC9, 0x6B]
          ['current_test4',    None, None, [0x01, 0x06, 0x00, 0x41, 0x00, 0x08]], #        177.6ms 272.7ms         [0x01, 0x06, 0x00, 0x41, 0x00, 0x08, 0xD8, 0x18, 0x01, 0x06, 0x00, 0x02, 0x00, 0x01, 0xE9, 0xCA]
          ['current_test5',    None, None, [0x01, 0x03, 0x00, 0x05, 0x00, 0xC8]], #        370.4ms 463.4ms         [0x01, 0x03, 0x90, 0x00, 0x20, 0x00, 0x20, 0x00, 0x2B, 0x00, 0x15, 0x00, 0x15, 0x00, 0x2B, 0x00, 0x20, 0x00, 0x2B, 0x00, 0x20, 0x00, 0x0A, 0x00, 0x20, 0x00, 0x2B, 0x00, 0xD0, 0x01, 0x5F, 0x01, 0xB7, 0x01, 0xF9, 0x02, 0x04, 0x02, 0x04, 0x01, 0xF9, 0x02, 0x04, 0x02, 0x04, 0x02, 0x04, 0x02, 0x0F, 0x01, 0xEE, 0x02, 0x04, 0x02, 0x04, 0x02, 0x0F, 0x02, 0x04, 0x02, 0x0F, 0x01, 0xF9, 0x01, 0xF9, 0x02, 0x0F, 0x01, 0xF9, 0x01, 0xF9, 0x02, 0x0F, 0x01, 0xF9, 0x01, 0xF9, 0x01, 0xF9, 0x02, 0x04, 0x01, 0xF9, 0x02, 0x04, 0x02, 0x04, 0x02, 0x04, 0x01, 0xF9, 0x01, 0xF9, 0x01, 0xF9, 0x01, 0xF9, 0x01, 0xF9, 0x01, 0xF9, 0x01, 0xEE, 0x01, 0xEE, 0x01, 0xF9, 0x01, 0xF9, 0x02, 0x04, 0x01, 0xEE, 0x01, 0xEE, 0x01, 0xF9, 0x01, 0xE3, 0x01, 0xEE, 0x01, 0xEE, 0x01, 0xEE, 0x01, 0xEE, 0x01, 0xEE, 0x01, 0xEE, 0x01, 0xEE, 0x01, 0xEE, 0x01, 0xEE, 0x01, 0xEE, 0x01, 0xEE, 0x01, 0xEE, 0x01, 0xF9, 0x01, 0xF9, 0x01, 0xEE, 0x01, 0xF9, 0x01, 0xEE, 0x01, 0xEE, 0x01, 0xE3, 0x01, 0xD8, 0x01, 0xE3, 0x01, 0xF9, 0x01, 0xEE, 0x01, 0xEE, 0x01, 0xEE, 0x02, 0x04, 0x01, 0xEE, 0x01, 0xEE, 0x01, 0xE3, 0x01, 0xEE, 0x01, 0xD8, 0x01, 0xEE, 0x01, 0xF9, 0x01, 0xE3, 0x01, 0xF9, 0x01, 0xF9, 0x01, 0xF9, 0x01, 0xEE, 0x01, 0xEE, 0x01, 0xF9, 0x01, 0xF9, 0x01, 0xE3, 0x01, 0xF9, 0x02, 0x04, 0x02, 0x04, 0x02, 0x0F, 0x01, 0xF9, 0x01, 0xE3, 0x01, 0xF9, 0x01, 0xEE, 0x01, 0xF9, 0x01, 0xF9, 0x01, 0xF9, 0x01, 0xF9, 0x02, 0x04, 0x01, 0xF9, 0x01, 0xF9, 0x02, 0x04, 0x02, 0x1A, 0x01, 0xEE, 0x01, 0xF9, 0x02, 0x04, 0x02, 0x04, 0x02, 0x04, 0x01, 0xEE, 0x02, 0x04, 0x01, 0xF9, 0x02, 0x0F, 0x01, 0xEE, 0x01, 0xEE, 0x01, 0xEE, 0x01, 0xEE, 0x02, 0x0F, 0x02, 0x1A, 0x02, 0x1A, 0x01, 0xE3, 0x01, 0xF9, 0x02, 0x04, 0x02, 0x04, 0x02, 0x0F, 0x02, 0x04, 0x02, 0x04, 0x02, 0x04, 0x01, 0xE3, 0x01, 0xF9, 0x02, 0x04, 0x01, 0x49, 0x00, 0xAF, 0x00, 0x4C, 0x00, 0x2B, 0x00, 0x20, 0x00, 0x20, 0x00, 0x15, 0x00, 0x0A, 0x00, 0x0A, 0x00, 0x20, 0x00, 0x20, 0x00, 0x20, 0x00, 0x15, 0x00, 0x15, 0x00, 0x20, 0x00, 0x15, 0x00, 0x20, 0x00, 0x20, 0x00, 0x41, 0x00, 0x15, 0x00, 0x00, 0x00, 0x0A, 0x00, 0x15, 0x00, 0x0A, 0x00, 0x0A, 0x00, 0x0A, 0x00, 0x0A, 0x00]
          ['current_test end', None, None, [0x01, 0x06, 0x00, 0x02, 0x00, 0x00]] #       5.752s  5.754s          [0x01, 0x06, 0x00, 0x02, 0x00, 0x00, 0x28, 0x0A]
        ]

        self.run_cmd(cmds[0], False)
        msg = self.read_response(8)
        print map(hex, msg)

        self.run_cmd(cmds[1], False)
        msg = self.read_response(8)
        print map(hex, msg)

        self.run_cmd(cmds[2], False)
        msg = self.read_response(8)
        print map(hex, msg)

        self.run_cmd(cmds[3], False)
        msg = self.read_response(8)
        print map(hex, msg)
        msg = self.read_response(8)
        if msg:
            print map(hex, msg)

        self.run_cmd(cmds[4], False)
        msg = self.read_response(405)
        #print map(hex, msg)

        def h(v):
            v = (v[0] << 8) | (v[1])
            if v & 0x8000:
                v = -(v ^ 0xffff)
            return v
        # combine bytes into words and convert to signed integers
        error = map(h, zip(msg[0::2], msg[1::2]))
        print error

        self.run_cmd(cmds[5], False)
        msg = self.read_response(8)
        print map(hex, msg)


    def scope(self):
        self.scope_setup()
        self.scope_exec()


    def open_serial(self, serial_port):
        self.serial_port = serial_port

        self.ser = serial.Serial(port=self.serial_port, baudrate=38400, bytesize=serial.EIGHTBITS, parity=serial.PARITY_NONE, stopbits=serial.STOPBITS_ONE, timeout=1, xonxoff=False, rtscts=False, dsrdtr=False) #, write_timeout=None, dsrdtr=False) #, inter_byte_timeout=None)

        #ser.reset_input_buffer()
        #ser.reset_output_buffer()
        self.ser.flushInput()
        self.ser.flushOutput()

        # clear input (what do the previous flush command actually do?)
        while True:
            v = self.ser.read(1)
            if len(v) == 0:
                break


    def other_cmds(self):
        #cmds = [
        #['g1', None, None, [0x01, 0x03, 0x00, 0x10, 0x00, 0x0A]],
        #['g2', None, None, [0x01, 0x03, 0x00, 0x10, 0x00, 0x01]]
        #]

        #self.run_cmds(ser, cmds)

        cmds = [
        ['h1', None, None, [0x01, 0x03, 0x00, 0x16, 0x00, 0x01]],
        ['h2', None, None, [0x01, 0x03, 0x00, 0x15, 0x00, 0x01]],
        ['h3', None, None, [0x01, 0x03, 0x00, 0x1B, 0x00, 0x01]],
        ['h4', None, None, [0x01, 0x03, 0x00, 0x19, 0x00, 0x01]],
        ['h5', None, None, [0x01, 0x03, 0x00, 0x18, 0x00, 0x01]],
        ['h6', None, None, [0x01, 0x03, 0x00, 0x1A, 0x00, 0x01]],
        ['h7', None, None, [0x01, 0x03, 0x00, 0x1C, 0x00, 0x01]]
        ]

        self.run_cmds(self.ser, cmds)


def main():
    es = LeadshineEasyServo()
    es.open_serial(serial_port)

    if not es.send_introduction():
        print 'main(): failed introduction'
        sys.exit(1)

    if True:
        es.read_parameters()

    if True:
        setup_graph(es)
        es.motion_test()

    if False:
        es.current_test()

    if True:
        setup_graph(es)
        es.scope()

    #es.latest_cmds(ser)


if __name__ == "__main__":
    main()
