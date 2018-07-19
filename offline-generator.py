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
import yaml, sys, requests
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
handler_config = None
default_bucket_config =  {}
analysis_output_file = None

CONFIG_FILE = 'input.yml'
DEFAULT_VERSION = '1.0'

DEFAULT_RESOURCES_PATH = 'resources'

input_config_file = None
offline_pipeline = None
src_pipeline = None
RUN_NAME = None
param_file = None
process_resource_jobs = []
final_input_resources = []
final_output_resources = []

git_resources = {}
git_task_list = {}
docker_image_for_git_task_list = {}
full_docker_ref = []
docker_image_analysis_map = None

DEFAULT_GITHUB_RAW_CONTENT = 'raw.githubusercontent.com'
github_raw_content = None

def init():
	parser = argparse.ArgumentParser()

	parser.add_argument('target_pipeline', type=str,
		help='path to the target pipeline git repo dir')
	parser.add_argument('input_yml', type=str,
		help='path to the input yml file')
	parser.add_argument('-kickoff',
		action='store_true',
		help='kickoff offline-gen first phase')
	parser.add_argument('-analyze',
		action='store_true',
		help='docker dependency analysis only of tasks in github resources')
	return parser.parse_args()

def main():
	global repo, handler_config, input_config_file, pipeline, params, default_bucket_config, github_raw_content, analysis_output_file, RUN_NAME

	args = init()
	input_config_file = args.input_yml if args.input_yml is not None else CONFIG_FILE
	#print ' Git is True?? :{}'.format(args.git)
	print 'General Settings from: {}\n'.format(input_config_file)

	# repo_path=args.repo
	# pipeline = args.pipeline
	analysis_only = args.analyze
	kickoff_only = args.kickoff

	handler_config = read_config(input_config_file)

	repo = args.target_pipeline if args.target_pipeline is not None else handler_config['repo']
	pipeline = handler_config['pipeline']
	default_bucket_config = handler_config['s3_blobstore']
	pipeline_name_tokens = pipeline.split('/')
	target_pipeline_name = pipeline_name_tokens[len(pipeline_name_tokens) - 1]

	RUN_NAME = handler_config['run_name'] if handler_config.get('run_name') is not None else 'Run1'

	github_raw_content = handler_config.get('github_raw_content')
	if github_raw_content is None:
		github_raw_content = DEFAULT_GITHUB_RAW_CONTENT

	analysis_output_file = 'analysis-' + target_pipeline_name

	if kickoff_only:
		handle_kickoff_pipeline_generation()
	elif analysis_only:
		handle_docker_analysis_of_pipelines()
	else:
		handle_pipelines()


# def create_offline_repo_converter_as_resource():
# 	offline_gen_resource = { 'name': 'offline-gen-repo-converter'}
# 	offline_gen_resource['type'] = 's3'
# 	offline_gen_resource['source'] = copy.copy(default_bucket_config)
# 	offline_gen_resource['source']['regexp'] = '%s/%s/%s.(.*)' % ( RUN_NAME, DEFAULT_RESOURCES_PATH, 'offline-gen/utils/python/pipeline_repo_converter')
#
# 	return offline_gen_resource

# def create_offline_stemcell_downloader_as_resource():
# 	offline_gen_resource = { 'name': 'offline-gen-stemcell-downloader'}
# 	offline_gen_resource['type'] = 's3'
# 	offline_gen_resource['source'] = copy.copy(default_bucket_config)
# 	offline_gen_resource['source']['regexp'] = '%s/%s/%s(.*).sh' % ( RUN_NAME, DEFAULT_RESOURCES_PATH, 'offline-gen/utils/shell/find_and_download')
#
# 	return offline_gen_resource

# def add_docker_image_as_resource(pipeline):
# 	new_docker_resource = { 'name': 'test-ubuntu-docker'}
# 	new_docker_resource['type'] = 'docker-image'
# 	new_docker_resource['source'] = { 'repository' : 'ubuntu', 'tag' : '17.04' }
# 	pipeline['resources'].append(new_docker_resource)
# 	final_input_resources.append(new_docker_resource)

def handle_docker_analysis_of_pipelines():
	global src_pipeline, offline_pipeline

	#print('Repo Path:     {}\nPipeline file: {}'.format(repo, pipeline))
	src_pipeline = read_config(repo + '/' + pipeline )
	offline_pipeline = copy.copy(src_pipeline)

	docker_analysis_map = analyze_pipeline_for_docker_images(None, src_pipeline)
	write_config( docker_analysis_map, analysis_output_file)

	#print ''
	#print 'Created docker image analysis of pipeline: ' + analysis_output_file
	return docker_analysis_map

def handle_kickoff_pipeline_generation():
	global src_pipeline

	print('Repo Path:     {}\nPipeline file: {}'.format(repo, pipeline))
	src_pipeline = read_config(repo + '/' + pipeline )

	#print 'Got src pipeline: {}'.format(src_pipeline)
	pipeline_name_tokens = pipeline.split('/')
	target_pipeline_name = pipeline_name_tokens[len(pipeline_name_tokens) - 1]

	git_only_pipeline_filename= 'kickoff-full-offline-gen-' + target_pipeline_name

	try:
		git_input_resources = handle_git_only_resources()
		save_kickoff_pipeline(	git_input_resources,
								git_only_pipeline_filename
							)

		print '\nFinished git_only pipeline generation!!\n\n'

	except Exception as e:
		print('Error : {}'.format(e))
		print(traceback.format_exc())
		print >> sys.stderr, 'Error occured.'
		sys.exit(1)

def save_kickoff_pipeline(git_input_resources, git_only_pipeline_filename):

	print 'Input git resources:{}'.format(git_input_resources)

	offlinegen_param_file_source = copy.copy(default_bucket_config)
	pipeline_param_file_source = copy.copy(default_bucket_config)
	analysis_results_filesource = copy.copy(default_bucket_config)
	blobstore_upload_pipeline_source = copy.copy(default_bucket_config)
	offline_pipeline_source = copy.copy(default_bucket_config)

	OFFLINE_GEN_RESOURCE_BASE_PATH             = '%s/%s/%s' % ( RUN_NAME, DEFAULT_RESOURCES_PATH, 'offline-gen')
	offlinegen_param_file_source['regexp']     = '%s/offline-gen-params-*(.*).yml' % ( OFFLINE_GEN_RESOURCE_BASE_PATH)
	pipeline_param_file_source['regexp']       = '%s/pipeline-params-*(.*).yml' % ( OFFLINE_GEN_RESOURCE_BASE_PATH)
	analysis_results_filesource['regexp']      = '%s/analysis-*(.*).yml' % ( OFFLINE_GEN_RESOURCE_BASE_PATH)
	offline_pipeline_source['regexp']          = '%s/offline-*(.*).yml' % ( OFFLINE_GEN_RESOURCE_BASE_PATH)
	blobstore_upload_pipeline_source['regexp'] = '%s/blobstore-upload-*(.*).yml' % ( OFFLINE_GEN_RESOURCE_BASE_PATH)

	try:
		context = {}
		resource_context = {
			'context': context,
			'source_resource_types': [],
			#'process_resource_jobs': process_resource_jobs,
			'offline_gen_param_file_source': offlinegen_param_file_source,
			'pipeline_param_file_source': pipeline_param_file_source,
			'git_resources': git_input_resources,
			'target_pipeline_branch': handler_config['target_pipeline_branch'],
			'target_pipeline_uri': handler_config['target_pipeline_uri'],
			'analysis_results_filesource': analysis_results_filesource,
			'blobstore_upload_pipeline_source': blobstore_upload_pipeline_source,
			'offline_pipeline_source': offline_pipeline_source
		}

		git_only_pipeline = template.render_as_config(
			os.path.join('.', 'blobstore/full_offline_generation.v1.yml' ),
			resource_context
		)
		write_config(git_only_pipeline, git_only_pipeline_filename)

		print ''
		#print 'Created full offline analysis pipeline: ' + git_only_pipeline_filename
	except Exception as e:
		print('Error during git only pipeline generation : {}'.format(e))
		print(traceback.format_exc())
		print >> sys.stderr, 'Error occured.'
		sys.exit(1)

# def handle_git_only_pipeline_generation():
# 	global src_pipeline
#
# 	print('Repo Path:     {}\nPipeline file: {}'.format(repo, pipeline))
# 	src_pipeline = read_config(repo + '/' + pipeline )
#
# 	#print 'Got src pipeline: {}'.format(src_pipeline)
# 	pipeline_name_tokens = pipeline.split('/')
# 	target_pipeline_name = pipeline_name_tokens[len(pipeline_name_tokens) - 1]
#
# 	git_only_pipeline_filename= 'build-git-repos-' + target_pipeline_name
#
# 	try:
# 		git_input_resources = handle_git_only_resources()
# 		save_git_only_pipeline(	git_input_resources,
# 								git_only_pipeline_filename
# 							)
#
# 		print '\nFinished git_only pipeline generation!!\n\n'
#
# 	except Exception as e:
# 		print('Error : {}'.format(e))
# 		print(traceback.format_exc())
# 		print >> sys.stderr, 'Error occured.'
# 		sys.exit(1)
#
# def save_git_only_pipeline(git_input_resources, git_only_pipeline_filename):
#
# 	print 'Input git resources:{}'.format(git_input_resources)
#
# 	offlinegen_param_file_source = copy.copy(default_bucket_config)
# 	pipeline_param_file_source = copy.copy(default_bucket_config)
# 	build_git_repos_source = copy.copy(default_bucket_config)
#
# 	offlinegen_param_file_source['regexp'] = '%s/%s/offline-gen/offline-gen-params-*(.*).yml' % ( RUN_NAME, DEFAULT_RESOURCES_PATH)
# 	pipeline_param_file_source['regexp'] = '%s/%s/offline-gen/pipeline-params-*(.*).yml' % ( RUN_NAME, DEFAULT_RESOURCES_PATH)
# 	build_git_repos_source['regexp'] = '%s/%s/offline-gen/build-git-repos-*(.*).yml' % ( RUN_NAME, DEFAULT_RESOURCES_PATH)
#
# 	try:
# 		context = {}
# 		resource_context = {
# 	        'context': context,
# 			'source_resource_types': [],
# 	        #'process_resource_jobs': process_resource_jobs,
# 			'offlinegen_param_file_source': offlinegen_param_file_source,
# 			'pipeline_param_file_source': pipeline_param_file_source,
# 			'git_resources': git_input_resources,
# 			'git_repos_source': build_git_repos_source
# 	    }
#
# 		git_only_pipeline = template.render_as_config(
# 	        os.path.join('.', 'blobstore/parse_git_repos.v1.yml' ),
# 	        resource_context
# 	    )
# 		write_config(git_only_pipeline, git_only_pipeline_filename)
#
# 		print ''
# 		print 'Created git only pipeline: ' + git_only_pipeline_filename
# 	except Exception as e:
# 		print('Error during git only pipeline generation : {}'.format(e))
# 		print(traceback.format_exc())
# 		print >> sys.stderr, 'Error occured.'
# 		sys.exit(1)



def handle_pipelines():
	global src_pipeline, offline_pipeline

	print('Repo Path:     {}\nPipeline file: {}'.format(repo, pipeline))
	src_pipeline = read_config(repo + '/' + pipeline )
	offline_pipeline = copy.copy(src_pipeline)

	#print 'Got src pipeline: {}'.format(src_pipeline)
	pipeline_name_tokens = pipeline.split('/')
	target_pipeline_name = pipeline_name_tokens[len(pipeline_name_tokens) - 1]

	offline_pipeline_filename= 'offline-' + target_pipeline_name
	blobstore_upload_pipeline_filename = 'blobstore-upload-' + target_pipeline_name

	try:
		handle_resources()
		save_blobuploader_pipeline(	final_input_resources,
									final_output_resources,
									blobstore_upload_pipeline_filename
								)
		save_offline_pipeline(offline_pipeline_filename)

		print '\nFinished offline generation!!\n\n'

	except Exception as e:
		print('Error : {}'.format(e))
		print(traceback.format_exc())
		print >> sys.stderr, 'Error occured.'
		sys.exit(1)


def save_offline_pipeline(offline_pipeline_filename):
	try:
		handle_offline_tasks()

		if "true" == handler_config.get('parameterize_s3_bucket_params'):
			handle_inline_parameterization_of_s3blobstore(offline_pipeline)

		write_config(offline_pipeline, offline_pipeline_filename, useNoAliasDumper=False)
		print 'Created offline pipeline: ' + offline_pipeline_filename
	except Exception as e:
		print('Error during offline pipeline generation : {}'.format(e))
		print(traceback.format_exc())
		print >> sys.stderr, 'Error occured.'
		sys.exit(1)

# Change parameters in final generated offline pipeline s3 source to be s3_blobstore_parameterized_tokens
# for porting across S3 blobstore_source. This will allow replacement of actual s3 configs to parameterized list
# Sample generated S3 source
#source: {access_key_id: my_access_id, bucket: offline-bucket, endpoint: 'http://10.85.24.5:9000/',
#    regexp: test1/resources/docker/czero-cflinuxfs2-latest-docker.(.*), secret_access_key: my_secret_access_key}
# Modified to
#source: {access_key_id: ((final_s3_access_key_id)), bucket: ((final_s3_bucket)), endpoint: ((final_s3_endpoint)),
#  regexp: test1/resources/docker/czero-cflinuxfs2-latest-docker.(.*), secret_access_key: ((final_s3_secret_access_key))}
def handle_inline_parameterization_of_s3blobstore(content):
	s3blobstore_replacement_token_map = handler_config.get('s3_blobstore_parameterized_tokens')
	if s3blobstore_replacement_token_map is None:
		return

	if type(content) == list:
		for item in content:
			handle_inline_parameterization_of_s3blobstore(item)
	elif type(content) == dict:
		for key in content.keys():
			if key == 'source':
				source = content[key]
				if 'access_key_id' not in source.keys():
					return

				for key in s3blobstore_replacement_token_map:
					source[key] = '((%s))' % (s3blobstore_replacement_token_map[key])
			else:
				handle_inline_parameterization_of_s3blobstore(content[key])

def save_blobuploader_pipeline(input_resources, output_resources, blobstore_upload_pipeline_filename):

	if src_pipeline.get('resource_types') is None:
		src_pipeline['resource_types'] = []

	try:
		context = {}
		resource_context = {
			'context': context,
			'source_resource_types': src_pipeline.get('resource_types'),
			#'process_resource_jobs': process_resource_jobs,
			'resources': src_pipeline['resources'],
			'final_input_resources': input_resources,
			'final_output_resources': output_resources,
			'files': []
		}

		blobstore_upload_pipeline = template.render_as_config(
			os.path.join('.', 'blobstore/blobstore_upload_pipeline.v1.yml' ),
			resource_context
		)

		if "true" == handler_config.get('parameterize_s3_bucket_params'):
			handle_inline_parameterization_of_s3blobstore(blobstore_upload_pipeline)

		write_config(blobstore_upload_pipeline, blobstore_upload_pipeline_filename)

		print ''
		print 'Created blobstore upload pipeline: ' + blobstore_upload_pipeline_filename
	except Exception as e:
		print('Error during blobuploader pipeline generation : {}'.format(e))
		print(traceback.format_exc())
		print >> sys.stderr, 'Error occured.'
		sys.exit(1)



def analyze_pipeline_for_docker_images(pipeline_repo_path, target_pipeline):
	global docker_image_analysis_map

	if target_pipeline is None:
		target_pipeline = read_config(pipeline_repo_path)

	task_files = identify_all_task_files(target_pipeline)

	identify_associated_docker_image_for_task(git_task_list)

	print '\nFinal Docker dependency list'
	pprint(full_docker_ref)
	print '\nDependency graph of Github Repos, tasks and docker images references\n'
	pprint(docker_image_for_git_task_list)

	docker_image_analysis_map = { 'docker_list': full_docker_ref, 'pipeline_task_docker_references':  docker_image_for_git_task_list }
	write_config( docker_image_analysis_map, analysis_output_file)
	print ''
	print 'Created docker image analysis of pipeline: ' + analysis_output_file

	return docker_image_analysis_map

def identify_all_task_files(target_pipeline):
	task_files = []
	for resource in target_pipeline['resources']:
		if resource['type'] == 'git':
			print 'Input Resource: {}'.format(resource)
			branch = resource['source'].get('branch')
			if branch is None:
				branch = 'master'
			uri = resource['source']['uri'].replace('.git', '').replace('github.com', 'raw.githubusercontent.com')

			git_resources[resource['name']] = {'uri' : uri, 'branch' : branch }
			git_task_list[resource['name']] = []

	docker_image_task_entry = { 'git_path': 'pipeline' }
	docker_image_task_entry['task_defns'] = []
	docker_image_task_entry['docker_references'] = []
	docker_image_task_entry['job_tasks_references'] = []

	for job in target_pipeline['jobs']:
		job_tasks = []
		for plan in job['plan']:
			for plan_key in plan.keys():
				if str(plan_key) in [ 'aggregate', 'do' ]:
					aggregate = plan[plan_key]
					for entry in aggregate:
						for nested_entry_key in entry:
							if nested_entry_key == 'task':
								task_file = entry.get('file')
								if task_file is None:
									continue

								if task_file is not None:
									git_resource_id = task_file.split('/')[0]

								job_tasks.append( { 'task': entry.get('task'), 'file': task_file, 'git_resource' : git_resource_id } )

								if 	task_file is not None and task_file not in task_files:
									task_files.append(task_file)
									git_task_list[git_resource_id].append({ 'task': entry.get('task'), 'file': task_file } )

				elif str(plan_key) == 'task':
					task_file = plan.get('file')
					if task_file is None:
						continue

					if task_file is not None:
						git_resource_id = task_file.split('/')[0]

					job_tasks.append( { 'task': plan[plan_key], 'file': task_file, 'git_resource' : git_resource_id  } )
					if task_file is not None and task_file not in task_files:
						task_files.append(task_file)
						git_task_list[git_resource_id].append({ 'task': plan.get('task'), 'file': task_file })
					elif task_file is None:
						image_source = plan['config']['image_resource']
						if image_source is not None and 'docker' in image_source['type']:
							docker_repo = image_source['source']
							docker_image_task_entry['task_defns'].append( { plan.get('task') : { 'image': docker_repo } } )
							if docker_repo not in full_docker_ref:
								full_docker_ref.append(docker_repo)
							if docker_repo not in docker_image_task_entry['docker_references']:
								docker_image_task_entry['docker_references'].append(docker_repo)

		docker_image_task_entry['job_tasks_references'].append( { job['name'] : job_tasks } )


	docker_image_for_git_task_list['target-pipeline'] = docker_image_task_entry
	# print '\nComplete task list\n'
	# pprint(task_files)
	# print '\nComplete git task list\n'
	# pprint(git_task_list)
	# print '\n'
	return task_files

def identify_associated_docker_image_for_task(git_task_list):

	for git_repo_id in git_resources:
		git_resource = git_resources[git_repo_id]
		git_repo_path = '%s/%s/' % (git_resource['uri'], git_resource['branch'])
		git_repo_path = git_repo_path.replace('git@%s/' % (github_raw_content), 'https://%s/' % (github_raw_content) )
		if git_resource.get('username') is not None:
			git_repo_path = git_repo_path.replace('https://',
							'https://%s:%s@' % (git_resource.get('username') , git_resource.get('password') ))

		docker_image_task_entry = { 'git_path': git_repo_path }
		docker_image_task_entry['task_defns'] = []
		docker_image_task_entry['docker_references'] = []
		task_list = git_task_list[git_repo_id]
		for task in task_list:
			index = task['file'].index('/')
			task_path = task['file'][index+1:]
			task_defn = load_github_resource(git_repo_id, git_repo_path, task_path)
			image_source = task_defn.get('image_source')
			if image_source is None:
				image_source = task_defn.get('image_resource')

			if image_source is not None and 'docker' in image_source['type']:
				docker_repo = image_source['source']
				docker_image_task_entry['task_defns'].append( {
													task.get('task'): {
																		'file': task_path,
																		'image': docker_repo ,
																		'script': task_defn['run']['path'] ,
																		'inputs': task_defn.get('inputs'),
																		'outputs': task_defn.get('outputs'),
																		'params': task_defn.get('params')
																		}
																}
															)
				if docker_repo not in docker_image_task_entry['docker_references']:
					docker_image_task_entry['docker_references'].append(docker_repo)

				if docker_repo not in full_docker_ref:
					full_docker_ref.append(docker_repo)

		docker_image_for_git_task_list[git_repo_id] = docker_image_task_entry

def load_github_resource(git_repo_id, git_remote_uri, task_file_path):
	try:
		# First try with local file path
		input_file = git_repo_id + '/' + task_file_path

		with open(input_file) as task_file:
			yamlcontent = yaml.safe_load(task_file)
			print 'Successful reading task as local file: {}\n'.format(input_file)
			return yamlcontent
	except IOError as e:
		try:
			print >> sys.stderr, 'Problem with reading task as local file: {}'.format(input_file)
			response = requests.get(git_remote_uri + task_file_path)
			yamlcontent = yaml.safe_load(response.content)
			print 'Went with Remote url for task: {}\n'.format(git_remote_uri + task_file_path)
			return yamlcontent
		except IOError as e:
			print e
			print >> sys.stderr, 'Not able to load content from : ' + uri
			sys.exit(1)


def handle_resources():

	global docker_image_analysis_map

	#task_list = identify_all_task_files(src_pipeline)
	# Identify all tasks and docker images used in the final pipeline
	# Add docker images as resources in source pipeline
	# Then rejigger the resources to be input and output in the blobuploader pipeline

	# Try to use saved default docker image analysis map file
	docker_image_analysis_map = read_config( analysis_output_file, abort=False)

	# Else handle full parsing
	if docker_image_analysis_map is None:
		docker_image_analysis_map = analyze_pipeline_for_docker_images(None, offline_pipeline)
	#else:
	#	print 'Used existing docker image analysis map of pipeline from: ' + analysis_output_file

	for docker_image_ref in docker_image_analysis_map['docker_list']:
		version = 'latest' if docker_image_ref.get('tag') is None else docker_image_ref.get('tag')
		docker_image_ref['tag'] = version
		docker_image_name = '%s-%s-%s' % (docker_image_ref['repository'].replace('/', '-'), version, 'docker')
		src_pipeline['resources'].append( { 'name': docker_image_name, 'type' : 'docker-image', 'source' : docker_image_ref})

	# Reset all resources in the offline pipeline
	offline_pipeline['resources'] = []
	offline_pipeline['resource_types'] = []

	# Then add the modified resources to the offline_pipeline
	for resource in src_pipeline['resources']:
		res_type = resource['type']
		res_name = resource['name']
		resource_process_job = None

		if res_type == 's3':
			resource_process_job = handle_s3_resource(copy.copy(resource))
		elif res_type == 'git':
			resource_process_job = handle_git_resource(resource, src_pipeline, docker_image_analysis_map['pipeline_task_docker_references'][res_name])
		elif 'docker' in res_type:
			resource_process_job = handle_docker_image(resource)
		elif res_type == 'pivnet':
			if resource['source']['product_slug'] in [ 'ops-manager' ]:
				resource_process_job = handle_pivnet_non_tile_resource(resource)
			else:
				resource_process_job = handle_pivnet_tile_resource(resource)
		else:
			resource_process_job = handle_default_resource(resource)

	print '\nFinished handling of all resource jobs\n'

def handle_git_only_resources():

	#task_list = identify_all_task_files(src_pipeline)
	# Identify all tasks and docker images used in the final pipeline
	# Add docker images as resources in source pipeline
	# Then rejigger the resources to be input and output in the blobuploader pipeline

	git_only_resources = []

	# Then add the modified resources to the offline_pipeline
	for resource in src_pipeline['resources']:
		res_type = resource['type']
		res_name = resource['name']
		resource_process_job = None

		if res_type == 'git':
			git_only_resources.append(resource)

	print '\nFinished handling of all git only resource jobs\n'
	return git_only_resources


def find_match_in_list(list, name):
	for entry in list:
		if entry['name'] == name + '-tarball':
			return entry
		elif entry['name'] == name:
			return entry

	return None

def create_resource_map(resource_list):
	resource_map = {}
	for entry in resource_list:
		name = entry['name']
		resource_map[entry['name']] = entry
		name_without_tarball = name.replace('-tarball', '')
		if resource_map.get(name_without_tarball) is None:
			resource_map[name_without_tarball] =  entry

	return resource_map

def handle_offline_tasks():

	alias_resource_map = {}

	job_tasks_references = docker_image_analysis_map['pipeline_task_docker_references']['target-pipeline']['job_tasks_references']
	for offline_job in offline_pipeline['jobs']:

		found_job_tasks_reference = False
		target_task_name = None
		target_task_file = None
		ref_map_target_job_name = None

		for job_tasks_reference in job_tasks_references:
			ref_map_target_job_name = job_tasks_reference.keys()[0]
			if offline_job['name'] == ref_map_target_job_name:
				found_job_tasks_reference = True
				break

		plan_index = 0
		saved_plan_inputs = []

		for plan in offline_job['plan']:
			#print '## Offline job: {}, job_tasks_reference: {}, set of keys inside plan: {} and type: {}\n\n\n'.format(
											# offline_job['name'], job_tasks_reference, plan.keys(), type(plan))

			non_resource_related_entry_map = {}
			last_saved_plan_entry_map = {}

			for plan_key in plan:

				plan_entry = plan[plan_key]
				if plan_key in ['aggregate' , 'do' ]:

					original_aggregate = copy.copy(plan_entry)
					handle_aggregated_plan_entry(plan, plan_key, original_aggregate, alias_resource_map, job_tasks_reference)

					for new_entry in plan[plan_key]:
						for entry_key, entry_value in new_entry.items():
							if entry_key == 'get' and entry_value not in saved_plan_inputs:
								saved_plan_inputs.append(entry_value)

				elif plan_key in [ 'file', 'task' ]:
					inline_task_details(plan, alias_resource_map, ref_map_target_job_name, saved_plan_inputs)

				elif 'get' == plan_key:

					for plan_entry in plan.keys():
						if plan_entry != 'get':
							# Skip non-get attributes
							continue

						original_get_resource_name = plan[plan_entry]
						new_nested_plan_entries = handle_get_resource_details(original_get_resource_name, job_tasks_reference)
						if new_nested_plan_entries is not None:
							plan['aggregate'] = new_nested_plan_entries

							for nested_plan_entry in new_nested_plan_entries:
								(entry_key, entry_value), = nested_plan_entry.items()
								if entry_key == 'get' and entry_value not in saved_plan_inputs:
									saved_plan_inputs.append(entry_value)
							#print 'Saved Plan Inputs: {}'.format(saved_plan_inputs)
						plan.pop('get', None)
				else:
					# Just save the entry as is (we are only worried abt tasks and gets that need modification)
					# Check if the task has already been processed!!
					embedded_task = plan.get('task')

			# Pop off any image references from the plan
			# We want to purely go with image_resource and not image
			plan.pop('image', None)
			#print 'Finally modified Plan: {}'.format(plan)

			plan_index += 1
	print 'Finished handling of all jobs in offline pipeline'

def handle_aggregated_plan_entry(plan, aggregate_key, original_aggregate, alias_resource_map, job_tasks_reference):

	non_resource_related_entry_map = {}
	last_saved_plan_entry_map = {}

	original_aggregate_list = plan[aggregate_key]
	new_aggregate_list = []

	offline_resource_map = create_resource_map(offline_pipeline['resources'])

	for entry in original_aggregate_list:

		for nested_entry_key, nested_entry_value in entry.items():
			if nested_entry_key == 'get':
				original_get_resource_name = nested_entry_value

				# Rare cases where the get is tagged as pivnet-prodcut
				# - get: pivnet-product
				#   resource: pivotal-container-service
				#   params: {globs: ["pivotal-container-service*.pivotal"]}

				matching_resource = offline_resource_map.get(original_get_resource_name)
				if matching_resource is None:
					aliased_resource_name = original_get_resource_name
					if entry.get('resource') is not None:
						original_get_resource_name = entry.get('resource')
						entry.pop('resource', None)
						alias_resource_map[aliased_resource_name] = original_get_resource_name

				new_nested_entries = handle_get_resource_details(original_get_resource_name, job_tasks_reference)
				#print 'Got nested plan entries as {} '.format(new_nested_entries)
				if new_nested_entries is not None:
					for new_nested_entry  in new_nested_entries:
						for new_nested_entry_key, new_nested_entry_value  in new_nested_entry.items():

							if 'docker' not in new_nested_entry_key:
								last_saved_plan_entry_map[new_nested_entry_key] = new_nested_entry_value

								# Close out previously saved current_plan_entry_map entry
								if last_saved_plan_entry_map:
									new_aggregate_list.append(last_saved_plan_entry_map )
									last_saved_plan_entry_map = { }
							else:
								new_aggregate_list.append( { new_nested_entry_key : new_nested_entry_value } )
			else:
				if nested_entry_key == 'resource':
					continue

				last_saved_plan_entry_map[nested_entry_key] = nested_entry_value

	if last_saved_plan_entry_map:
		new_aggregate_list.append(last_saved_plan_entry_map)

	# Save this as the new plan entry against the aggregate key
	plan[aggregate_key] = new_aggregate_list

def handle_get_resource_details(get_resource_name, job_tasks_reference):

	new_nested_plan_entries = []
	resource_type = 'file'

	src_resource_map = create_resource_map(src_pipeline['resources'])
	offline_resource_map = create_resource_map(offline_pipeline['resources'])

	matching_tarballed_resource = None

	matching_orginal_resource = src_resource_map[get_resource_name]
	if matching_orginal_resource is not None:
		resource_type = matching_orginal_resource['type']
	else:
		print 'Error!! Unable to find matching resource: {} from src pipeline!'.format(get_resource_name)
		return None

	matching_offline_resource = offline_resource_map.get(get_resource_name)
	if matching_offline_resource is not None:
		matching_tarballed_resource = matching_offline_resource

	if resource_type in [ 'file-url', 'file', 's3' ]:
		# Add original input resource as is
		new_nested_plan_entries.append(  { 'get' :  get_resource_name } )

	elif resource_type in [ 'docker', 'docker-image', 'git' ]:

		# Add the github tarball as input if its a match against git resources in offline pipeline
		if matching_tarballed_resource is None:
			print 'Unable to find matching resource: {}'.format(get_resource_name + '-tarball')
			return None

		resource_id = get_resource_name
		job_name = job_tasks_reference.keys()[0]

		# print 'COMPLETE JOB TASKS REFERENCE: {} , JOB NAME ***** :{} before \
		# 	adding docker reference'.format(job_tasks_reference.keys(), job_name)

		# Sample job_tasks_ref
		# {'standalone-install-nsx-t': [{'file': 'nsx-t-gen-pipeline/tasks/install-nsx-t/task.yml',
		#                                'git_resource': 'nsx-t-gen-pipeline',
		#                                'task': 'install-nsx-t'}]},

		docker_image_tarball_name = None
		original_task_input_params = None
		for job_task in job_tasks_reference[job_name]:
			#print 'Job tasks is {} and Task is {}'.format(job_tasks_reference, job_task)
			matching_task_name = job_task['task']

			for task_defn_map in docker_image_analysis_map['pipeline_task_docker_references'][resource_id]['task_defns']:
				for key in task_defn_map:
					if key == matching_task_name:
						docker_image_ref = task_defn_map[key]['image']

						version = 'latest' if docker_image_ref.get('tag') is None else docker_image_ref.get('tag')
						docker_image_ref['tag'] = version
						docker_image_tarball_name = '%s-%s-%s-tarball' % (docker_image_ref['repository'].replace('/', '-'), version, 'docker')

						break

		new_git_plan_entry = { 'get' : matching_tarballed_resource['name'] }
		new_docker_plan_entry = { 'get' :  docker_image_tarball_name }

		if new_git_plan_entry not in new_nested_plan_entries:
			new_nested_plan_entries.append( new_git_plan_entry)

		if docker_image_tarball_name is not None and new_docker_plan_entry not in new_nested_plan_entries:
			new_nested_plan_entries.append( new_docker_plan_entry )

	elif resource_type in [ 'pivnet' ]:
		# Special handling for Pivnet Tiles
		new_nested_plan_entries.append( { 'get' :  get_resource_name } )

		# # Check for stemcells associated with the tile
		# matching_stemcell_resource = None
		# matching_stemcell_resource = offline_resource_map.get(get_resource_name + '-stemcell')
		# if matching_stemcell_resource is not None:
		# 	new_nested_plan_entries.append( { 'get' :  matching_stemcell_resource['name'] } )

		# Check for tarball associated with the tile
		matching_tile_tarball_resource = None
		matching_tile_tarball_resource = offline_resource_map.get(get_resource_name + '-tarball')
		if matching_tile_tarball_resource is not None:
			new_nested_plan_entries.append( { 'get' :  matching_tile_tarball_resource['name'] } )

	return new_nested_plan_entries


# Pipeline tasks might not specify all expected keys for a given tasks
# So, add those back into the inlined params for a task so the actual task execution does not barf
def merge_param_names(given_task_params, original_task_input_params):
	for expected_key in original_task_input_params.keys():
		if expected_key not in given_task_params.keys():
			given_task_params[expected_key] = None

def inline_task_details(plan, alias_resource_map, ref_map_target_job_name, saved_plan_inputs):

	given_task_name = plan.get('task')
	given_task_file = plan.get('file')
	given_task_params = plan.get('params')

	original_task_inputs = []
	for entry in saved_plan_inputs:
		original_task_inputs.append( { 'name' : entry } )

	# If the plan task has already been inlined, return
	if given_task_file is None and 'offlined-' in given_task_name:
		return

	if given_task_file is None:
		#handle_preinlined_task_details(plan, saved_plan_inputs)
		original_task_script = plan['config']['run']['args'][1]
		original_task_outputs = plan.get('outputs')
		docker_image_tarball_input_name = None

		inline_remaining_plan_config(plan,
									alias_resource_map,
									docker_image_tarball_input_name,
									original_task_inputs,
									original_task_outputs,
									original_task_script)
		return

	index = given_task_file.index('/')
	git_resource_id = given_task_file[:index]

	# If the task is a match, then proceed with updating the task reference to use tarballed docker image
	# and special handling

	original_task_outputs = None
	original_task_script = None
	docker_image_tarball_name = None

	offline_resource_map = create_resource_map(offline_pipeline['resources'])

	# print 'Inline Task details for Ref map Job name:{}, for plan:{}, for task: {} with file:{} \
	# 		and given plan level inputs:{} \n\n'.format( \
	# 				ref_map_target_job_name, plan, given_task_name, \
	# 				given_task_file, saved_plan_inputs)

	task_defn_found = False
	for task_defn_map in docker_image_analysis_map['pipeline_task_docker_references'][git_resource_id]['task_defns']:
		if task_defn_found:
			break

		for key in task_defn_map:
			task_defn = task_defn_map[key]

			if task_defn['file'] in given_task_file:
				docker_image_ref = task_defn['image']

				if task_defn['inputs'] is not None:
					original_task_inputs.extend(task_defn['inputs'])

				original_task_outputs = task_defn['outputs']
				original_task_script = task_defn['script']
				original_task_input_params = task_defn['params']
				if original_task_input_params is not None:
					merge_param_names(given_task_params, original_task_input_params)
					plan['params'] = given_task_params

				version = 'latest' if docker_image_ref.get('tag') is None else docker_image_ref.get('tag')
				docker_image_tarball_name = '%s-%s-%s-tarball' %  (
																	docker_image_ref['repository'].replace('/', '-'),
																	version,
																	'docker'
																)
				matching_tarballed_docker_resource = offline_resource_map.get(docker_image_tarball_name)

				source_bucket_details = copy.copy(default_bucket_config)
				source_bucket_details['regexp'] = matching_tarballed_docker_resource['source']['regexp']

				task_defn_found = True
				break

	docker_image_source = {
						'type': 's3',
						'source' : source_bucket_details,
						'params' : { 'unpack': True }
					}

	plan['config'] = { 'platform' : 'linux', 'image_resource': docker_image_source }

	# Pass the docker image tarball as input
	inline_remaining_plan_config(plan,
								alias_resource_map,
								docker_image_tarball_name,
								original_task_inputs,
								original_task_outputs,
								original_task_script)

	#print '\n## Task: {} Original Task Inputs: {} and original_task_script: {}\n'.format(given_task_name,
	# 														given_task_inputs, given_task_script)


def inline_remaining_plan_config(plan,
								alias_resource_map,
								docker_image_tarball_input_name,
								original_task_inputs,
								original_task_outputs,
								original_task_script):

	# If the plan task has already been inlined, return
	if 'offlined-' in plan.get('task'):
		return

	# print '\nInline_remaining_plan_config Task details top plan:{} and plan level inputs:{} abd docker_image_tarball_input_name:{} \n\n'.format(
	#  				plan, original_task_inputs, docker_image_tarball_input_name)

	new_task_input_names = [ ]
	offline_resource_map = create_resource_map(offline_pipeline['resources'])

	docker_image_source = None
	matching_tarballed_docker_resource = None
	if docker_image_tarball_input_name is not None:
		new_task_input_names = [ docker_image_tarball_input_name ]
		matching_tarballed_docker_resource = offline_resource_map.get(docker_image_tarball_input_name)
		source_bucket_details = copy.copy(default_bucket_config)
		source_bucket_details['regexp'] = matching_tarballed_docker_resource['source']['regexp']
		docker_image_source = {
							'type': 's3',
							'source' : source_bucket_details,
							'params' : { 'unpack': True }
						}

	new_task_outputs = original_task_outputs if original_task_outputs is not None else []

	tarball_resources_to_extract_map = {}
	file_resources_to_move_map = {}

	final_matching_resource = None
	#print 'Starting off with orignal_task_inputs:{} and offline resoruce map: {}'.format(original_task_inputs, offline_resource_map)
	for original_input in original_task_inputs:

		matching_resource = None
		matching_tarballed_resource = None

		# Check for tarballed resource from offline resources
		matching_tarballed_resource = offline_resource_map.get( original_input['name'] + '-tarball')

		if matching_tarballed_resource is not None:
			# Add the github tarball as input if its a match against git resources in offline pipeline
			new_task_input_names.append( matching_tarballed_resource['name'] )
			new_task_outputs.append( { 'name' : original_input['name'] } )

			# Use same input name in the map as coming with its registered name
			tarball_resources_to_extract_map[original_input['name'] ] = original_input['name']
			final_matching_resource = matching_tarballed_resource

		# Check for normal resource from offline resources
		if matching_tarballed_resource is None:
			matching_resource = offline_resource_map.get(original_input['name'])
			if matching_resource is not None:
				# add the input as is
				new_task_input_names.append( original_input['name'] )
				final_matching_resource = matching_resource

		# Check for aliased resource for matching tarballed resource
		if matching_tarballed_resource is None and matching_resource is None:
			aliased_resource_name = original_input['name']
			original_underlying_resource = alias_resource_map[aliased_resource_name]
			if original_underlying_resource is not None:

				matching_tarballed_resource = offline_resource_map.get(original_underlying_resource + '-tarball')
				if matching_tarballed_resource is not None:
					new_task_input_names.append( matching_tarballed_resource['name'] )
					new_task_outputs.append( { 'name' : aliased_resource_name } )
					# Map the aliased name against registered resource name
					tarball_resources_to_extract_map[aliased_resource_name ] = original_underlying_resource
					final_matching_resource = matching_tarballed_resource
				else:
					new_task_input_names.append( original_underlying_resource )
					new_task_outputs.append( { 'name' : aliased_resource_name } )
					file_resources_to_move_map[aliased_resource_name] = original_underlying_resource
					final_matching_resource = original_underlying_resource

			else:
				# Give up as we are unable to locate any matching direct or tarballed or aliased resource
				print '\n## Unable to find associated Resource for : {}'.format(original_input['name'])

	plan.pop('file', None)
	plan['task'] = 'offlined-' + plan['task']

	if docker_image_source is not None:
		plan['config'] = {
							'platform' : 'linux',
							'image_resource': docker_image_source
						}
	else:
		plan['config'] = {
							'platform' : 'linux',
							'image_resource': {
										'params': { 'unpack' : True } ,
										'type': 's3',
										'source' : final_matching_resource['source']
									}
						}

	# The docker image is not required to be part of the task input list
	new_task_input_names = normalize_list(new_task_input_names)
	for resource_name in copy.copy(new_task_input_names):
		if 'docker' in resource_name:
			new_task_input_names.remove(resource_name)

	plan['config']['inputs'] = normalize_into_named_list(new_task_input_names)
	plan['config']['run'] = create_full_run_command(tarball_resources_to_extract_map,
													file_resources_to_move_map,
													matching_tarballed_resource,
													original_task_script)

	if new_task_outputs is not None and new_task_outputs:
		plan['config']['outputs'] = normalize_list(new_task_outputs)


def create_full_run_command(tarball_dependent_resources_map, file_resources_to_move_map, ignore_resource, task_script):

	run_command_str = ''
	run_command_str_list = list(run_command_str)
	run_command_str_list.append('find . -name "version" -exec rm {} \; ;')
	run_command_str_list.append('find . -name "url" -exec rm {} \; ;')
	run_command_str_list.append('for file in $(find . -name "*-1.0");')
	run_command_str_list.append('do new_file=$(echo $file | sed -e \'s/-1.0$//g\');')
	run_command_str_list.append('mv ${file} ${new_file};')
	run_command_str_list.append('done;')
	run_command_str_list.append('ls -R;')

	for resource in tarball_dependent_resources_map.keys():
		if ignore_resource is None or (ignore_resource['name'] not in resource):
			run_command_str_list.append('cd %s; tar -zxf ../%s-tarball/*.tgz; cd ..;'
					% (resource, tarball_dependent_resources_map[resource]))

	for resource in file_resources_to_move_map.keys():
		if ignore_resource is None or (ignore_resource['name'] not in resource):
			run_command_str_list.append('cd %s; mv ../%s/* .; cd ..;'
					% (resource, file_resources_to_move_map[resource]))

	run_command_str_list.append("for token in $(env | grep '=' | grep \"^[A-Z]*\" | grep '=null' | sed -e 's/=.*//g');")
	run_command_str_list.append('do export ${token}="";  done;')
	run_command_str_list.append('echo Starting main task execution!!;')
	run_command_str_list.append(task_script)

	full_run_command = { 'path' : '/bin/bash'}
	full_run_command['args'] = [ '-exc' , "".join(run_command_str_list) ]

	return full_run_command

def normalize_list(given_list):

	final_list = []
	for entry in given_list:
		if entry not in final_list:
			final_list.append(entry)

	return final_list

def normalize_into_named_list(given_list):

	resource_names = list(set(given_list))
	for name in copy.copy(resource_names):
		if name + '-tarball' in resource_names:
			resource_names.remove(name)

	cleanedup_list = []
	for name in resource_names:
		cleanedup_list.append( { 'name' : name })

	return cleanedup_list

def add_inout_resources(resource):
	input_resource = copy.copy(resource)
	output_resource = copy.copy(resource)

	input_resource['name'] = 'input-%s-%s' % (resource['base_type'], resource['name'])
	output_resource['name'] = 'output-%s-%s' % (resource['base_type'], resource['name'])

	output_resource['source'] = copy.copy(default_bucket_config)
	output_resource['source']['regexp'] = output_resource['regexp']

	final_input_resources.append(input_resource)
	final_output_resources.append(output_resource)

	offline_resource = { 'name' : resource['name'] , 'type': 's3' , 'source': copy.copy(default_bucket_config) }
	offline_resource['source']['regexp'] = copy.copy(resource['regexp'])
	# For git or docker resource, change name to *-tarball
	if resource['base_type'] in ['git', 'docker' ]:
		offline_resource['name'] = '%s-tarball' % (resource['name'])

	offline_pipeline['resources'].append(offline_resource)

def handle_docker_image(resource):

	resource['base_type'] = 'docker'
	tag = resource['source'].get('tag')
	if tag is None:
		tag = 'latest'

	resource['tag'] = tag
	tagged_docker = '%s-docker' % tag

	# If the tag + 'docker' is already in the resource name, dont add it again
	if tagged_docker in resource['name']:
		resource['regexp'] = '%s/%s/docker/%s.(.*)' % ( RUN_NAME, DEFAULT_RESOURCES_PATH, resource['name'])
	else:
		resource['regexp'] = '%s/%s/docker/%s-%s-docker.(.*)' % ( RUN_NAME, DEFAULT_RESOURCES_PATH, resource['name'], tag)

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

	# Register the in/out resources
	add_inout_resources(resource)
	return docker_job_resource

def handle_git_resource(resource, src_pipeline, task_list):

	res_name = resource['name']
	resource['base_type'] = 'git'
	resource['regexp'] = '%s/%s/%s/%s-tar(.*).tgz' % ( RUN_NAME, DEFAULT_RESOURCES_PATH, 'git', resource['name'])

	matching_task_files = []
	for task_file in task_list:
		if task_file.startswith(res_name):
			matching_task_files.append(task_file.replace(res_name + '/', ''))

	#print '####### Task list for git resource: {}'.format(matching_task_files)

	# Jinja template would barf against single quote. so change to double quotes
	task_list_arr = str(matching_task_files)#.replace('\'', '"')
	bucket_config = str(default_bucket_config)#.replace('\'', '"')

	resource['task_list'] = task_list_arr
	resource['blobstore_source'] = bucket_config

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

	# # Register the docker images list also
	# output_docker_images_json_resource = copy.copy(resource)
	# output_docker_images_json_resource['name'] = 'output-%s-%s' % ('git-docker-images', resource['name'], )
	# output_docker_images_json_resource['regexp'] = '%s/%s/%s-docker-(.*).json' % ( 'resources', 'docker-images', resource['name'])
	#
	# final_output_resources.append(output_docker_images_json_resource)
	#
	# output_docker_images_resource = copy.copy(resource)
	# output_docker_images_resource['name'] = 'output-%s-%s' % ('docker-images', resource['name'], )
	# output_docker_images_resource['regexp'] = '%s/%s/%s-docker-(.*).tar' % ( 'resources', 'docker-images', resource['name'])
	# final_output_resources.append(output_docker_images_resource)

	#print '###### Job for Git resource: {}'.format(git_job_resource)
	return git_job_resource

def handle_pivnet_tile_resource(resource):

	resource['base_type'] = 'tile'
	resource['regexp'] = '%s/%s/pivnet-tile/%s/(.*).pivotal' % ( RUN_NAME, DEFAULT_RESOURCES_PATH, resource['name'])

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


	# stemcell_regexp = '%s/%s/pivnet-tile/%s-stemcell/bosh-(.*).tgz' % ( RUN_NAME, DEFAULT_RESOURCES_PATH, resource['name'])
	# output_stemcell_resource = { 'type': 's3' , 'source': default_bucket_config }
	# output_stemcell_resource['name'] = 'output-%s-%s' % ('stemcell', resource['name'])
	# output_stemcell_resource['source']['regexp'] = stemcell_regexp
	# final_output_resources.append(output_stemcell_resource)

	# Register the combined tile + stemcell also
	combined_tile_stemcell_regexp = '%s/%s/pivnet-tile/%s-tarball/%s-(.*).tgz' % ( RUN_NAME, DEFAULT_RESOURCES_PATH, resource['name'], resource['name'])
	output_tile_stemcell_resource = { 'type': 's3' , 'source': default_bucket_config }
	output_tile_stemcell_resource['name'] = 'output-%s-%s' % ('tile-stemcell', resource['name'])
	output_tile_stemcell_resource['source']['regexp'] = combined_tile_stemcell_regexp
	final_output_resources.append(output_tile_stemcell_resource)

	# offline_stemcell_resource = { 'name' : resource['name'] , 'type': 's3' , 'source': default_bucket_config }
	# offline_stemcell_resource['source']['regexp'] = stemcell_regexp
	# offline_stemcell_resource['name'] = '%s-%s' % (resource['name'], 'stemcell')
	#
	# offline_pipeline['resources'].append(offline_stemcell_resource)

	tile_tarball_regexp = '%s/%s/pivnet-tile/%s-tarball/(.*).tgz' % ( RUN_NAME, DEFAULT_RESOURCES_PATH, resource['name'])
	offline_tile_tarball_resource = { 'name' : '%s-tarball' % resource['name'] , 'type': 's3' , 'source': default_bucket_config }
	offline_tile_tarball_resource['source']['regexp'] = tile_tarball_regexp
	offline_tile_tarball_resource['name'] = '%s-%s' % (resource['name'], 'tarball')

	offline_pipeline['resources'].append(offline_tile_tarball_resource)

	return pivnet_tile_job_resource

def handle_pivnet_non_tile_resource(resource):

	resource['base_type'] = 'pivnet-non-tile'
	resource['regexp'] = '%s/%s/pivnet-non-tile/%s-(.*)' % ( RUN_NAME, DEFAULT_RESOURCES_PATH, resource['name'])

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

	#print 'Job for Pivnet non-Tile resource: {}'.format(non_pivnet_job_resource)
	return non_pivnet_job_resource

def handle_s3_resource(resource):

	# If the source and destination are the same s3 buckets/access keys,
	# then just simply copy the resource into offline pipeline
	resource['base_type'] = 's3'

	if resource['source']['endpoint'] == default_bucket_config['endpoint'] \
	  and resource['source']['bucket'] == default_bucket_config['bucket'] \
	  and resource['source']['access_key_id'] == \
	  default_bucket_config['access_key_id'] \
	  and resource['source']['secret_access_key'] == \
	  default_bucket_config['secret_access_key']:
		# Just add to the offline resource list
		offline_pipeline['resources'].append(resource)
		return None

	# Requires modification
	resource['base_type'] = 's3'
	resource['regexp'] = '%s/%s/s3/%s-(.*)' % ( RUN_NAME, DEFAULT_RESOURCES_PATH, resource['name'])

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

	#print 'Job for S3 resource: {}'.format(s3_job_resource)
	return s3_job_resource

def handle_default_resource(resource):

	resource['base_type'] = 'file'
	resource['regexp'] = '%s/%s/file/%s-*-(.*)' % ( RUN_NAME, DEFAULT_RESOURCES_PATH, resource['name'])

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

	#print 'Job for File resource: {}'.format(file_job_resource)
	return file_job_resource

def read_config(input_file, abort=True):
	try:
		with open(input_file) as config_file:
			yamlcontent = yaml.safe_load(config_file)
			return yamlcontent
	except IOError as e:
		print('Error : {}'.format(e))
		print >> sys.stderr, 'Problem with file!'
		if abort:
			print >> sys.stderr, 'Aborting!!'
			sys.exit(1)
	except Exception as ce:
		print ce
		print >> sys.stderr, 'Not a yaml config file.'
		print >> sys.stderr, 'Attempting to modify {{ ... }} to (( ... )) and retry'
		with open(input_file) as config_file:
			data = config_file.read().replace('{{', '))').replace('}}', '))')
			yamlcontent = yaml.load(data)
			return yamlcontent

def write_config(content, destination, useNoAliasDumper=True):
	dumper = NoAliasDumper if useNoAliasDumper else None
	try:
		with open(destination, 'w') as output_file:
			if useNoAliasDumper:
				yaml.dump(content, output_file,  Dumper=dumper)
			else:
				yaml.dump(content, output_file)

	except IOError as e:
		print('Error : {}'.format(e))
		print >> sys.stderr, 'Problem with writing out a yaml file.'
		sys.exit(1)

class NoAliasDumper(yaml.Dumper):
	def ignore_aliases(self, data):
		return True

if __name__ == '__main__':
	main()
