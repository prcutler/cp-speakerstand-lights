
# SPDX-FileCopyrightText: 2021 Phil Burgess for Adafruit Industries
#
# SPDX-License-Identifier: MIT

"""NeoPixel Featherwing with rp2040 Feather Audio Reactive Lights"""

"""Based on AUDIO SPECTRUM LIGHT SHOW for Adafruit EyeLights (LED Glasses + Driver). 
From https://github.com/adafruit/Adafruit_Learning_System_Guides/blob/main/EyeLights_Audio_Spectrum/EyeLights_Audio_Spectrum_CircuitPython/code.py
"""

from array import array
from math import log
import board
import neopixel
from audiobusio import PDMIn
from ulab import numpy as np
from ulab.scipy.signal import spectrogram
from supervisor import reload
from rainbowio import colorwheel
import time 


# Digital Audio 
import audiocore
import audiobusio

# Import PixelFramebuffer
# import helper
from adafruit_pixel_framebuf import PixelFramebuffer
from adafruit_led_animation.helper import PixelMap

# Import from featherwing example
from adafruit_led_animation import helper


# FFT/SPECTRUM CONFIG ----

fft_size = 256  # Sample size for Fourier transform, MUST be power of two
spectrum_size = fft_size // 2  # Output spectrum is 1/2 of FFT result
# Bottom of spectrum tends to be noisy, while top often exceeds musical
# range and is just harmonics, so clip both ends off:
# Original low = 10 and high = 75 - cut the spectrum down for better 
# pixel sound reactions on a smaller screen than the orginal
low_bin = 35  # Lowest bin of spectrum that contributes to graph
high_bin = 55  # Highest bin "

# Set NeoPixel
pixel_pin = board.D6  # NeoPixel LED strand is connected to GPIO #0 / D0
pixels = 32  # Number of pixels you are using


# Add Neopixel Featherwing vertical and horizontal functions
pixel_width = 8
pixel_height = 4

pixels = neopixel.NeoPixel(
    pixel_pin,
    pixel_width * pixel_height,
    brightness=0.1,
    auto_write=False,
)

pixel_framebuf = PixelFramebuffer(
    pixels,
    pixel_width,
    pixel_height,
    alternating=False,
)


# Set up digial mic
mic = audiobusio.PDMIn(board.D10, board.D9,
                       sample_rate=16000, bit_depth=16)
rec_buf = array("H", [0] * fft_size)  # 16-bit audio samples

# FFT/SPECTRUM SETUP -----

# To keep the display lively, tables are precomputed where each column of
# the matrix (of which there are few) is the sum value and weighting of
# several bins from the FFT spectrum output (of which there are many).
# The tables also help visually linearize the output so octaves are evenly
# spaced, as on a piano keyboard, whereas the source spectrum data is
# spaced by frequency in Hz.
column_table = []

spectrum_bits = log(spectrum_size, 2)  # e.g. 7 for 128-bin spectrum
# Scale low_bin and high_bin to 0.0 to 1.0 equivalent range in spectrum
low_frac = log(low_bin, 2) / spectrum_bits
frac_range = log(high_bin, 2) / spectrum_bits - low_frac

for column in range(pixel_width):
    # Determine the lower and upper frequency range for this column, as
    # fractions within the scaled 0.0 to 1.0 spectrum range. 0.95 below
    # creates slight frequency overlap between columns, looks nicer.
    lower = low_frac + frac_range * (column / pixel_width * 0.95)
    upper = low_frac + frac_range * ((column + 1) / pixel_width)
    mid = (lower + upper) * 0.5  # Center of lower-to-upper range
    half_width = (upper - lower) * 0.5  # 1/2 of lower-to-upper range
    # Map fractions back to spectrum bin indices that contribute to column
    first_bin = int(2 ** (spectrum_bits * lower) + 1e-4)
    last_bin = int(2 ** (spectrum_bits * upper) + 1e-4)
    bin_weights = []  # Each spectrum bin's weighting will be added here
    for bin_index in range(first_bin, last_bin + 1):
        # Find distance from column's overall center to individual bin's
        # center, expressed as 0.0 (bin at center) to 1.0 (bin at limit of
        # lower-to-upper range).
        bin_center = log(bin_index + 0.5, 2) / spectrum_bits
        dist = abs(bin_center - mid) / half_width
        if dist < 1.0:  # Filter out a few math stragglers at either end
            # Bin weights have a cubic falloff curve within range:
            dist = 1.0 - dist  # Invert dist so 1.0 is at center
            bin_weights.append(((3.0 - (dist * 2.0)) * dist) * dist)
    # Scale bin weights so total is 1.0 for each column, but then mute
    # lower columns slightly and boost higher columns. It graphs better.
    total = sum(bin_weights)
    bin_weights = [
        (weight / total) * (0.8 + idx / pixel_width * 1.4)
        for idx, weight in enumerate(bin_weights)
        ]
    # List w/five elements is stored for each column:
    # 0: Index of the first spectrum bin that impacts this column.
    # 1: A list of bin weights, starting from index above, length varies.
    # 2: Color for drawing this column on the LED matrix. The 225 is on
    #    purpose, providing hues from red to purple, leaving out magenta.
    # 3: Current height of the 'falling dot', updated each frame
    # 4: Current velocity of the 'falling dot', updated each frame
    column_table.append(
        [
            first_bin - low_bin,
            bin_weights,
            colorwheel(225 * column / pixel_width),
            pixel_height,
            0.0,
        ]
    )
print(column_table)


# MAIN LOOP -------------
# Original dynamic_level = 10
dynamic_level = 35  # For responding to changing volume levels
frames, start_time = 0, time.monotonic()  # For frames-per-second calc

while True:
    # The try/except here is because VERY INFREQUENTLY the I2C bus will
    # encounter an error when accessing the LED driver, whether from bumping
    # around the wires or sometimes an I2C device just gets wedged. To more
    # robustly handle the latter, the code will restart if that happens.
    try:
        mic.record(rec_buf, fft_size)  # Record batch of 16-bit samples
        samples = np.array(rec_buf)  # Convert to ndarray
        # Compute spectrogram and trim results. Only the left half is
        # normally needed (right half is mirrored), but we trim further as
        # only the low_bin to high_bin elements are interesting to graph.
        spectrum = spectrogram(samples)[low_bin : high_bin + 1]
        # Linearize spectrum output. spectrogram() is always nonnegative,
        # but add a tiny value to change any zeros to nonzero numbers
        # (avoids rare 'inf' error)
        spectrum = np.log(spectrum + 1e-7)
        # Determine minimum & maximum across all spectrum bins, with limits
        lower = max(np.min(spectrum), 4)
        upper = min(max(np.max(spectrum), lower + 6), 20)

        # Adjust dynamic level to current spectrum output, keeps the graph
        # 'lively' as ambient volume changes. Sparkle but don't saturate.
        if upper > dynamic_level:
            # Got louder. Move level up quickly but allow initial "bump."
            dynamic_level = upper * 0.7 + dynamic_level * 0.3
        else:
            # Got quieter. Ease level down, else too many bumps.
            dynamic_level = dynamic_level * 0.5 + lower * 0.5

        # Apply vertical scale to spectrum data. Results may exceed
        # matrix height...that's OK, adds impact!
        data = (spectrum - lower) * (7 / (dynamic_level - lower))

        for column, element in enumerate(column_table):
            # Start BELOW matrix and accumulate bin weights UP, saves math
            first_bin = element[0]
            column_top = pixel_height + 1
            for bin_offset, weight in enumerate(element[1]):
                column_top -= data[first_bin + bin_offset] * weight

            if column_top < element[3]:  #       Above current falling dot?
                element[3] = column_top - 0.5  # Move dot up
                element[4] = 0  #                and clear out velocity
            else:
                element[3] += element[4]  #      Move dot down
                element[4] += 0.2  #             and accelerate

            column_top = int(column_top)  #      Quantize to pixel space
            for row in range(column_top):  #     Erase area above column
                pixel_framebuf.pixel(column, row, 0)
                # glasses.pixel(column, row, 0)
            for row in range(column_top, 5):  #  Draw column
                pixel_framebuf.pixel(column, row, element[2])

            pixel_framebuf.pixel(column, int(element[3]), 0xE08080)  # Draw peak dot

        # glasses.show()  # Buffered mode MUST use show() to refresh matrix
        pixel_framebuf.display()

        frames += 1
        # print(frames / (monotonic() - start_time), "FPS")

    except OSError:  # See "try" notes above regarding rare I2C errors.
        print("Restarting")
        reload()
