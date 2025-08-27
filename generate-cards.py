#!/usr/bin/env python3

# The Rules of Acquisition @ ferengi.bible
# Business card generator
# Copyright (C) 2025 Joey Parrish
# Licensed under CC0 1.0 (see LICENSE)

import math
import subprocess


def balance(text, max_chars_per_line, initial_leftovers=0):
  if len(text) <= max_chars_per_line:
    return text

  words = text.split(' ')

  num_lines = 1
  accumulated_len = -1
  for word in words:
    accumulated_len += len(word) + 1
    if accumulated_len > max_chars_per_line:
      accumulated_len = len(word)
      num_lines += 1

  ideal_line_len = math.ceil(len(text) / num_lines)
  lines = []
  current_line = ''
  leftovers = initial_leftovers

  for word in words:
    this_line_max_len = min(ideal_line_len + leftovers, max_chars_per_line)

    if len(current_line) + len(word) > this_line_max_len:
      leftovers = this_line_max_len - len(current_line)
      lines.append(current_line)
      current_line = ''

    if current_line:
      current_line += ' '
    current_line += word

  if current_line:
    lines.append(current_line)

  if len(lines) > num_lines:
    if initial_leftovers >= max_chars_per_line:
      raise RuntimeError('Line overflow! ' + repr(text))
    else:
      return balance(text, max_chars_per_line, initial_leftovers + 1)

  return '\n'.join(lines)


def generate_image(text, font_size, url, output):
      subprocess.check_call([
        'magick',
        # White business card sized thing.
        # 3.34 x 1.84 inches @ 300 DPI (safe area)
        '-size', '1002x552',
        'xc:white',
        # Settings for future stages
        '-background', 'transparent',
        '-fill', 'black',
        '-font', 'cards/RobotoCondensed-Bold.ttf',
        # The rule itself
        '-gravity', 'center',
        '-pointsize', str(font_size),
        '-size', '1002x552',
        'caption:{}'.format(text),
        '-gravity', 'none', '-composite',
        # The URL
        '-gravity', 'south',
        '-pointsize', '50',
        '-size', '1002x534',
        'caption:{}'.format(url),
        '-gravity', 'none', '-composite',
        # Expand to the full bleed size, centering the previous stage
        '-gravity', 'center',
        '-background', 'white',
        '-extent', '1098x648',
        # Add a border overlay
        'cards/border.png',
        '-gravity', 'none', '-composite',
        # Output with palette for smallest possible image size
        '-colors', '4',
        'png8:{}'.format(output),
      ])

      # Further optimize the image.
      subprocess.check_call([
        'optipng', '-o2', output,
      ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def main():
  # Load the rules.
  with open('rules.txt', 'r') as f:
    rule_lines = f.read().strip().split('\n')

    for line in rule_lines:
      number, rule = line.split('\t')
      print('\r#{}...'.format(number), end='')

      balanced_rule = balance(rule, 20)
      font_size = 100

      if len(balanced_rule.split('\n')) > 4:
        balanced_rule = balance(rule, 30)
        font_size = 70
      elif len(balanced_rule.split('\n')) > 2:
        balanced_rule = balance(rule, 25)
        font_size = 80

      output = 'cards/backs/{:03d}.png'.format(int(number))
      url = 'https://ferengi.bible/#{}'.format(number)

      # Use ImageMagick to generate an image for this rule.
      generate_image(balanced_rule, font_size, url, output)

    # Use ImageMagick to generate an image for the front of the card.
    generate_image(
        'The Rules of Acquisition', 150, '',
        'cards/front.png')

    print('\r       \rDone!')


if __name__ == '__main__':
  main()
