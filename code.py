'''Adapted from the FFT Example: Waterfall Spectrum Analyzer
by Jeff Epler
https://learn.adafruit.com/ulab-crunch-numbers-fast-with-circuitpython/overview '''

'''Also adapted from Mini LED Matrix Audio Visualizer by Liz Clark
https://learn.adafruit.com/mini-led-matrix-audio-visualizer/code-the-mini-led-matrix-audio-visualizer '''

import array
import board
import neopixel
from analogio import AnalogIn
from ulab import numpy as np
from ulab.scipy.signal import spectrogram

# Digital Audio 
import audiobusio

# Import PixelFramebuffer
from adafruit_pixel_framebuf import PixelFramebuffer

# Import from featherwing example
from adafruit_led_animation import helper


# Set-up NeoPixel
pixel_pin = board.D6  # NeoPixel LED strand is connected to GPIO #0 / D0

# Add Neopixel Featherwing vertical and horizontal functions
pixel_width = 8
pixel_height = 4

# Assign pixels and framebuf
pixels = neopixel.NeoPixel(
    pixel_pin,
    pixel_width * pixel_height,
    brightness=0.05,
    auto_write=False,
)

pixel_framebuf = PixelFramebuffer(
    pixels,
    pixel_width,
    pixel_height,
    alternating=False,
)

#  array of colors for the LEDs
#  goes from purple to red
#  gradient generated using https://colordesigner.io/gradient-generator
heatmap = [0xb000ff,0xa600ff,0x9b00ff,0x8f00ff,0x8200ff,
           0x7400ff,0x6500ff,0x5200ff,0x3900ff,0x0003ff,
           0x0003ff,0x0047ff,0x0066ff,0x007eff,0x0093ff,
           0x00a6ff,0x00b7ff,0x00c8ff,0x00d7ff,0x00e5ff,
           0x00e0ff,0x00e6fd,0x00ecf6,0x00f2ea,0x00f6d7,
           0x00fac0,0x00fca3,0x00fe81,0x00ff59,0x00ff16,
           0x00ff16,0x45ff08,0x62ff00,0x78ff00,0x8bff00,
           0x9bff00,0xaaff00,0xb8ff00,0xc5ff00,0xd1ff00,
           0xedff00,0xf5eb00,0xfcd600,0xffc100,0xffab00,
           0xff9500,0xff7c00,0xff6100,0xff4100,0xff0000,
           0xff0000,0xff0000]


# Set up digial mic
mic = audiobusio.PDMIn(board.D10, board.D9,
                       sample_rate=16000, bit_depth=16)

# Size of the FFT data sample
fft_size = 64

#  Use some extra sample to account for the mic startup
samples_bit = array.array('H', [0] * (fft_size+3))
# print("Samples bit: ", samples_bit)

#  sends visualized data to the RGB matrix with colors
def waves(data, y):
    offset = max(0, (13-len(data))//2)

    for x in range(min(13, len(data))):
        # is31.pixel(x+offset, y, heatmap[int(data[x])])
        pixel_framebuf.pixel(x+offset, y, heatmap[int(data[x])])
        pixel_framebuf.display()

# Main loop
def main():

    #  value for audio samples
    max_all = 10

    #  variable to move data along the matrix
    scroll_offset = 0

    #  setting the y axis value to equal the scroll_offset
    y = scroll_offset

    while True:
        #  record the audio sample
        mic.record(samples_bit, len(samples_bit))
        
        #  send the sample to the ulab array
        samples = np.array(samples_bit[3:])
        
        #  creates a spectogram of the data
        spectrogram1 = spectrogram(samples)
        # print("Spec1", spectrogram1)
        
        # spectrum() is always nonnegative, but add a tiny value
        # to change any zeros to nonzero numbers
        spectrogram1 = np.log(spectrogram1 + 1e-7)
        spectrogram1 = spectrogram1[1:(fft_size//2)-1]
        
        #  sets range of the spectrogram
        min_curr = np.min(spectrogram1)
        max_curr = np.max(spectrogram1)
        
        #  resets values
        if max_curr > max_all:
            max_all = max_curr
        else:
            max_curr = max_curr-1
        
        min_curr = max(min_curr, 3)
        
        # stores spectrogram in data
        # Does the 51  here come from the heatmap?
        data = (spectrogram1 - min_curr) * (51. / (max_all - min_curr))
        
        # sets negative numbers to zero
        data = data * np.array((data > 0))
        # print("Data", data)
        
        #  resets y
        y = scroll_offset

        #  runs waves to write data to the LED's
        waves(data, y)
        
        #  updates scroll_offset to move data along matrix
        scroll_offset = (y + 1) % 9
        
        # Does not print to the display here like the original code
        #pixel_framebuf.pixel(waves, y)
        #pixel_framebuf.display()

main()