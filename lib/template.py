#!/usr/bin/env python

# offline-gen
#
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#    http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

__author__ = 'Sabha Parameswaran'

import os
import sys
import errno
import base64
import shutil
import yaml
from utils import *

from jinja2 import Environment, FileSystemLoader, exceptions, select_autoescape

PATH = os.path.dirname(os.path.realpath(__file__))
TEMPLATE_PATH = os.path.realpath(os.path.join(PATH, '..', 'templates'))

def render_hyphens(input):
    return input.replace('_','-')

def render_yaml(input):
    return yaml.safe_dump(input, default_flow_style=False)


TEMPLATE_ENVIRONMENT = Environment(trim_blocks=True, lstrip_blocks=True, autoescape=select_autoescape( disabled_extensions=('yml',)))
TEMPLATE_ENVIRONMENT.loader = FileSystemLoader(TEMPLATE_PATH)
TEMPLATE_ENVIRONMENT.filters['hyphens'] = render_hyphens
TEMPLATE_ENVIRONMENT.filters['yaml'] = render_yaml

def render_as_stream(template_file, config):
    TEMPLATE_ENVIRONMENT.get_template(template_file).render(config)

def render_as_config(template_file, config):
    stream = TEMPLATE_ENVIRONMENT.get_template(template_file).render(config)
    gen_output = yaml.safe_load(stream)
    #print 'Gen output: {}'.format(gen_output)
    return gen_output

def render(target_path, template_file, config):
    # print('** TEMPLATE_PATH: {}'.format(TEMPLATE_PATH))
    # print('** target_path: {}'.format(target_path))
    # print('** template_file: {}'.format(template_file))

    target_dir = os.path.dirname(target_path)

    if target_dir != '':
        mkdir_p(target_dir)

    with open(target_path, 'wb') as target:
        target.write(TEMPLATE_ENVIRONMENT.get_template(template_file).render(config))

def myexists(template_file):
    #print 'calling exists on template file path as : {} and result:{}'.format(template_file, path(template_file))
    return os.exists(path(template_file))

def path(template_file):
    file_path = os.path.join(TEMPLATE_PATH, template_file)
    #print 'Returning file path as : ' + file_path
    return file_path
