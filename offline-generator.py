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
import json
import copy
import yaml, sys
from pprint import pprint
import argparse
import traceback

PATH = os.path.dirname(os.path.realpath(__file__))
LIB_PATH = os.path.realpath(os.path.join(PATH, 'lib'))
TEMPLATE_PATH = os.path.realpath(os.path.join(PATH, 'templates'))

#sys.path.append(REPO_PATH)
sys.path.append(LIB_PATH)

import template
from utils import *

repo = '.'
pipeline = None
params = None
default_bucket_config =  {}

CONFIG_FILE = 'input.yml'
DEFAULT_VERSION = '1.0'

input_config_file = None

src_pipeline = None

process_resource_jobs = []
final_input_resources = []
final_output_resources = []

def init():
	parser = argparse.ArgumentParser()
	# parser.add_argument('repo', type=str,
	#         help='path to the pipeline repo')
	# parser.add_argument('pipeline', type=str,
	#         help='path to the execution pipeline')
	# parser.add_argument('params', type=str,
	#         help='path to the params file for the pipeline')
	parser.add_argument('input_yml', type=str,
		help='path to the input yml file')
	return parser.parse_args()

def main():
	global repo, pipeline, params, default_bucket_config

	args = init()
	input_config_file = args.input_yml if args.input_yml is not None else CONFIG_FILE
	# repo_path=args.repo
	# pipeline = args.pipeline

	print 'Got input as : ' + input_config_file
	handler_config = read_config(input_config_file)
	repo = handler_config['repo']
	pipeline = handler_config['pipeline']
	params = handler_config['params']
	default_bucket_config = handler_config['s3_blobstore']
	handle_pipeline()

# def add_task_handler_as_resource(pipeline):
# 	task_handler_resource = { 'name': 'task_handler'}
# 	task_handler_resource['type'] = 's3'
# 	task_handler_resource['source'] = copy.copy(default_bucket_config)
# 	task_handler_resource['source']['regexp'] = '%s/handlers/%s' % ( 'resources', 'task_handler(.*)')
# 	pipeline['resources'].append(task_handler_resource)

def create_offline_repo_converter_as_resource():
	offline_gen_resource = { 'name': 'offline-gen-repo-converter'}
	offline_gen_resource['type'] = 's3'
	offline_gen_resource['source'] = copy.copy(default_bucket_config)
	offline_gen_resource['source']['regexp'] = '%s/%s.(.*)' % ( 'resources', 'offline-gen/utils/python/pipeline_repo_converter')

	return offline_gen_resource

def create_offline_stemcell_downloader_as_resource():
	offline_gen_resource = { 'name': 'offline-gen-stemcell-downloader'}
	offline_gen_resource['type'] = 's3'
	offline_gen_resource['source'] = copy.copy(default_bucket_config)
	offline_gen_resource['source']['regexp'] = '%s/%s(.*).sh' % ( 'resources', 'offline-gen/utils/shell/find_and_download')

	return offline_gen_resource

# def add_docker_image_as_resource(pipeline):
# 	new_docker_resource = { 'name': 'test-ubuntu-docker'}
# 	new_docker_resource['type'] = 'docker-image'
# 	new_docker_resource['source'] = { 'repository' : 'ubuntu', 'tag' : '17.04' }
# 	pipeline['resources'].append(new_docker_resource)
# 	final_input_resources.append(new_docker_resource)

def handle_pipeline():

	print('Got repo: {} and pipeline: {}'.format(repo, pipeline))
	src_pipeline = read_config(repo + '/' + pipeline )
	#print 'Got src pipeline: {}'.format(src_pipeline)
	pipeline_name_tokens = pipeline.split('/')
	target_pipeline_name = pipeline_name_tokens[len(pipeline_name_tokens) - 1]

	offline_pipeline_filename= 'offline-' + target_pipeline_name
	blobstore_upload_pipeline_filename = 'blobstore-upload-' + target_pipeline_name

	try:

		handle_resources(src_pipeline)

		final_input_resources.append(create_offline_repo_converter_as_resource())
		final_input_resources.append(create_offline_stemcell_downloader_as_resource())

		print 'Going to render final blobstore upload pipeline with inputs: {}\n\n'.format(process_resource_jobs)
		context = {}
		resource_context = {
	        'context': context,
			'source_resource_types': src_pipeline['resource_types'],
	        #'process_resource_jobs': process_resource_jobs,
			'resources': src_pipeline['resources'],
			'final_input_resources': final_input_resources,
			'final_output_resources': final_output_resources,
	        'files': []
	    }

		blobstore_upload_pipeline = template.render_as_config(
	        os.path.join('.', 'blobstore/blobstore_upload_pipeline.yml' ),
	        resource_context
	    )
		print 'Job for blobstore_upload_pipeline : {}'.format(blobstore_upload_pipeline)

		print 'Target Resource types is : {}'.format(blobstore_upload_pipeline['resource_types'])
		write_config(blobstore_upload_pipeline, blobstore_upload_pipeline_filename)

		print ''
		print 'Created blobstore upload pipeline: ' + blobstore_upload_pipeline_filename

	except Exception as e:
		print('Error : {}'.format(e))
		print(traceback.format_exc())
		print >> sys.stderr, 'Error occured.'
		sys.exit(1)

def identify_all_task_files(src_pipeline):
	task_files = []

	for key in src_pipeline.keys():
		print 'Src pipeline key :{}'.format(key)
	for job in src_pipeline['jobs']:
		for plan in job['plan']:
			for plan_key in plan.keys():
				print '#### Plan key: {}'.format(plan_key)
				if str(plan_key) == 'aggregate':
					print 'Aggregate: {}'.format(plan[plan_key])
					aggregate = plan[plan_key]
					for entry in aggregate:
						# print 'Entry within aggregate: {}'.format(entry)
						# print 'Entry keys within aggregate: {}'.format(entry.keys)
						for nested_entry_key in entry:
							if nested_entry_key == 'task':
								print '### nested_task_within_aggregate: {}'.format(entry['task'])
								print('### Matching task file: {}'.format(entry['file']))
								if entry['file'] not in task_files:
									task_files.append(entry['file'])

				elif str(plan_key) == 'task':
				 	print '^^^^ Found Task: {}'.format(plan[plan_key])
					print('^^^^ Matching task file: {}'.format(plan['file']))
					if plan['file'] not in task_files:
						task_files.append(plan['file'])

	print 'Complete task list: {}'.format(task_files)
	return task_files

# def get_inout_resources_from_job(process_resource_job, state):
# 	resources = []
# 	for entry in process_resource_job['plan']:
# 		if 'get' in entry.keys() and state == 'input':
# 			resource = entry['get']
# 			resources.append(resource)
# 		elif 'put' in entry.keys() and state == 'output':
# 			resource = entry['put']
# 			resources.append(resource)
# 	return resources

def handle_resources(src_pipeline):

	task_list = identify_all_task_files(src_pipeline)

	for resource in src_pipeline['resources']:
		print '\n\n######## Handling resource : {}\n\n'.format(resource)
		res_type = resource['type']
		res_name = resource['name']
		resource_process_job = None

		#resource_process_job = handle_default_resource(resource)
		#
		if res_type == 's3':
			#resource_process_job['type'] = 's3'
			resource_process_job = handle_s3_resource(resource)

		elif res_type == 'git':
			#resource_process_job['type'] = 'git'
			resource_process_job = handle_git_resource(resource, src_pipeline, task_list)

		elif res_type == 'docker-image':
			#resource_process_job['type'] = 'docker'
			resource_process_job = handle_docker_image(resource)
		elif res_type == 'pivnet':
			if resource['source']['product_slug'] in [ 'ops-manager' ]:
				#resource_process_job['type'] = 'pivnet-non-tile'
				resource_process_job = handle_pivnet_non_tile_resource(resource)
			else:
				#resource_process_job['type'] = 'tile'
				resource_process_job = handle_pivnet_tile_resource(resource)
		else:
			#resource_process_job['type'] = 'file'
			resource_process_job = handle_default_resource(resource)

		#if resource_process_job is None:
			# We need the resource as is - no transformation
		#	final_input_resources.append(resource)
		#else:
		#	process_resource_jobs.append(resource_process_job)

	print 'Finished handling of all resource jobs__________________\n\n'


def add_inout_resources(resource):
	input_resource = copy.copy(resource)
	output_resource = copy.copy(resource)

	input_resource['name'] = 'input-%s-%s' % (resource['base_type'], resource['name'])
	output_resource['name'] = 'output-%s-%s' % (resource['base_type'], resource['name'])

	final_input_resources.append(input_resource)
	final_output_resources.append(output_resource)

def handle_docker_image(resource, resource_jobs):
	print 'Handling docker image'

	resource['base_type'] = 'docker'
	resource['tag'] = resource['source']['tag']
	resource['regexp'] = '%s/docker/%s' % ( 'resources', resource['name'] + '-(.*).tgz')

	context = {}
	resource_context = {
        'context': context,
        'resource': resource,
        'files': []
    }

	docker_job_resource = template.render_as_config(
        os.path.join('.', 'blobstore/handle_docker_image.yml' ),
        resource_context
    )
	print 'Job for Docker  resource: {}'.format(docker_job_resource)

	# Register the in/out resources
	add_inout_resources(resource)

	return docker_job_resource

def handle_git_resource(resource, src_pipeline, task_list):
	print 'Handling git image'

	res_name = resource['name']
	resource['base_type'] = 'git'
	resource['regexp'] = '%s/%s/%s-(.*).tgz' % ( 'resources', 'git', resource['name'])

	matching_task_files = []
	for task_file in task_list:
		if task_file.startswith(res_name):
			matching_task_files.append(task_file.replace(res_name + '/', ''))

	#print 'Task list: {}'.format(matching_task_files)

	# Jinja template would barf against single quote. so change to double quotes
	task_list_arr = str(matching_task_files).replace('\'', '"')
	bucket_config = str(default_bucket_config).replace('\'', '"')
	context = {}
	resource_context = {
        'context': context,
        'resource': resource,
		'task_list': task_list_arr,
		'blobstore_source' : bucket_config,
        'files': []
    }

	git_job_resource = template.render_as_config(
        os.path.join('.', 'blobstore/handle_git_resource.yml' ),
        resource_context
    )

	# Register the in/out resources
	add_inout_resources(resource)

	# Register the docker images list also
	output_docker_images_resource = copy.copy(resource)
	output_docker_images_resource['name'] = 'output-%s-%s' % ('git-docker-images', resource['name'], )
	output_docker_images_resource['regexp'] = '%s/%s/%s-docker-(.*).yml' % ( 'resources', 'docker-images', resource['name'])

	final_output_resources.append(output_docker_images_resource)

	print '###### Job for Git resource: {}'.format(git_job_resource)
	return git_job_resource

def handle_pivnet_tile_resource(resource):
	print 'Handling pivnet tile image'

	resource['base_type'] = 'tile'
	resource['regexp'] = '%s/pivnet-tile/%s-(.*)' % ( 'resources', resource['name'])

	context = {}
	resource_context = {
        'context': context,
        'resource': resource,
        'files': []
    }

	pivnet_tile_job_resource = template.render_as_config(
        os.path.join('.', 'blobstore/handle_pivnet_tile.yml' ),
        resource_context
    )

	# Register the default in/out resources
	add_inout_resources(resource)

	# Register the stemcell also
	output_stemcell_resource = copy.copy(resource)
	output_stemcell_resource['name'] = 'output-%s-%s' % (resource['name'], 'stemcell')

	final_output_resources.append(output_stemcell_resource)

	print 'Job for Pivnet Tile resource: {}'.format(pivnet_tile_job_resource)
	return pivnet_tile_job_resource

def handle_pivnet_non_tile_resource(resource):
	print 'Handling Pivnet non-tile image'

	resource['base_type'] = 'pivnet-non-tile'
	resource['regexp'] = '%s/pivnet-non-tile/%s-(.*)' % ( 'resources', resource['name'])

	context = {}
	resource_context = {
        'context': context,
        'resource': resource,
        'files': []
    }

	non_pivnet_job_resource = template.render_as_config(
        os.path.join('.', 'blobstore/handle_non_pivnet_tile.yml' ),
        resource_context
    )

	# Register the in/out resources
	add_inout_resources(resource)

	print 'Job for Pivnet non-Tile resource: {}'.format(non_pivnet_job_resource)
	return non_pivnet_job_resource

def handle_s3_resource(resource):
	print 'Handling s3 resource'

	# If the source and destination are the same s3 buckets/access keys,
	# then just simply copy the resource into offline pipeline

	if resource['source']['endpoint'] == default_bucket_config['endpoint'] \
	  and resource['source']['bucket'] == default_bucket_config['bucket'] \
	  and resource['source']['access_key_id'] == \
	  default_bucket_config['access_key_id'] \
	  and resource['source']['secret_access_key'] == \
	  default_bucket_config['secret_access_key']:
		return None

	# Requires modification
	resource['base_type'] = 's3'
	resource['regexp'] = '%s/s3/%s-(.*)' % ( 'resources', resource['name'])

	context = {}
	resource_context = {
        'context': context,
        'resource': resource,
        'files': []
    }

	s3_job_resource = template.render_as_config(
        os.path.join('.', 'blobstore/handle_file_resource.yml' ),
        resource_context
    )

	# Register the in/out resources
	add_inout_resources(resource)

	print 'Job for S3 resource: {}'.format(s3_job_resource)
	return s3_job_resource

def handle_default_resource(resource):
	print 'Default handling of resource'

	resource['base_type'] = 'file'
	resource['regexp'] = '%s/file/%s-*-(.*)' % ( 'resources', resource['name'])

	context = {}
	resource_context = {
        'context': context,
        'resource': resource,
        'files': []
    }

	file_job_resource = template.render_as_config(
        os.path.join('.', 'blobstore/handle_file_resource.yml' ),
        resource_context
    )

	# Register the in/out resources
	add_inout_resources(resource)

	print 'Job for File resource: {}'.format(file_job_resource)
	return file_job_resource




def read_config(input_file):
	try:
		with open(input_file) as config_file:
			yamlcontent = yaml.safe_load(config_file)
			return yamlcontent
	except IOError as e:
		print >> sys.stderr, 'Not a yaml config file.'
		sys.exit(1)

def write_config(content, destination):
	try:
		with open(destination, 'w') as output_file:
			yaml.dump(content, output_file,  Dumper=NoAliasDumper)

	except IOError as e:
		print('Error : {}'.format(e))
		print >> sys.stderr, 'Problem with writing out a yaml file.'
		sys.exit(1)

class NoAliasDumper(yaml.Dumper):
    def ignore_aliases(self, data):
        return True

if __name__ == '__main__':
	main()
