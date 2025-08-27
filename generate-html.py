#!/usr/bin/env python3

# The Rules of Acquisition @ ferengi.bible
# HTML generator
# Copyright (C) 2024 Joey Parrish
# Licensed under CC0 1.0 (see LICENSE)

import jinja2
import subprocess


# Used to generate a sparse array, since not every rule is known.
LAST_RULE = 285
# Metadata that gets repeated in various places in the HTML.
TITLE = "The Rules of Acquisition"
DESCRIPTION = "The Ferengi Rules of Acquisition, as handed down by Grand Nagus Gint; every Ferengi business transaction is governed by these rules to ensure a fair and honest deal for all parties concerned."
URL = "https://ferengi.bible/"
THEME_COLOR = "#a5836a"
# Placeholder text for rules that don't exist.
PLACEHOLDERS = [
  "No such rule in Star Trek canon, but you can't see this because we blurred it. The upsell is a joke, hu-man! You can't subscribe.",
  "This rule has never been given in Trek canon, so the upsell offer is just a gag.",
  "Although this rule has never existed, this text may show up in search engines.",
  "Are you so determined to see what this is? It's fake.",
  "How do you translate \"lorem ipsum\" into Ferengi?",
]


def main():
  # Create a jinja2 environment.
  env = jinja2.Environment(
      loader=jinja2.FileSystemLoader('.'),
      autoescape=jinja2.select_autoescape())

  # Load the rules.
  extant_rules=[]
  with open('rules.txt', 'r') as f:
    rule_lines = f.read().strip().split('\n')
    rules = [None] * (LAST_RULE + 1)
    for line in rule_lines:
      number, rule = line.split('\t')
      number = int(number)
      rules[number] = rule
      extant_rules.append(number)

  # Load the HTML template.
  template = env.get_template('template.html')

  # Render to index.html
  with open('index.html', 'w') as f:
    f.write(template.render(
        extant_rules=extant_rules,
        rules=rules,
        title=TITLE,
        description=DESCRIPTION,
        url=URL,
        theme_color=THEME_COLOR,
        placeholders=PLACEHOLDERS))

  # Minify index.html.
  subprocess.run([
    'npx', '--yes', 'html-minifier-terser',
    '--collapse-whitespace',
    '--remove-comments',
    '--minify-css', 'true',
    '--minify-js', 'true',
    'index.html',
    '-o', 'index.html',
  ])

  # Prepend a license header to the minified index.html.
  with open('index.html', 'r') as f:
    content = f.read()
  with open('header', 'r') as f:
    content = f.read() + content
  with open('index.html', 'w') as f:
    f.write(content)


if __name__ == '__main__':
  main()
