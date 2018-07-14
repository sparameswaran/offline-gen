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
params = None
default_bucket_config =  {}

CONFIG_FILE = 'input.yml'
DEFAULT_VERSION = '1.0'

input_config_file = None
offline_pipeline = None
src_pipeline = None

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
	global repo, pipeline, params, default_bucket_config, github_raw_content

	args = init()
	input_config_file = args.input_yml if args.input_yml is not None else CONFIG_FILE
	# repo_path=args.repo
	# pipeline = args.pipeline

	print 'General Settings from: {}\n'.format(input_config_file)

	handler_config = read_config(input_config_file)
	repo = handler_config['repo']
	pipeline = handler_config['pipeline']
	params = handler_config['params']
	default_bucket_config = handler_config['s3_blobstore']

	github_raw_content = handler_config.get('github_raw_content')
	if github_raw_content is None:
		github_raw_content = DEFAULT_GITHUB_RAW_CONTENT

	handle_pipelines()

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

def create_privileged_docker_image_resource_as_resource_type():
	privileged_docker_image_resource = { 'name': 'privileged-docker-image-resource'}
	privileged_docker_image_resource['type'] = 'docker-image'
	privileged_docker_image_resource['privileged'] = True
	privileged_docker_image_resource['source']['repository'] = 'concourse/docker-image-resource'
	privileged_docker_image_resource['source']['tag'] = 'latest'

	return privileged_docker_image_resource

# def add_docker_image_as_resource(pipeline):
# 	new_docker_resource = { 'name': 'test-ubuntu-docker'}
# 	new_docker_resource['type'] = 'docker-image'
# 	new_docker_resource['source'] = { 'repository' : 'ubuntu', 'tag' : '17.04' }
# 	pipeline['resources'].append(new_docker_resource)
# 	final_input_resources.append(new_docker_resource)

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
		write_config(offline_pipeline, offline_pipeline_filename, useNoAliasDumper=False)
		print 'Created offline pipeline: ' + offline_pipeline_filename
	except Exception as e:
		print('Error during offline pipeline generation : {}'.format(e))
		print(traceback.format_exc())
		print >> sys.stderr, 'Error occured.'
		sys.exit(1)


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
	#write_config( docker_image_analysis_map, analysis_output_file)

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
	print '\nComplete task list\n'
	pprint(task_files)
	print '\nComplete git task list\n'
	pprint(git_task_list)
	print '\n'
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
			task_defn = load_github_resource(git_repo_path + task_path)
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
																		'outputs': task_defn.get('outputs')
																		}
																}
															)
				if docker_repo not in docker_image_task_entry['docker_references']:
					docker_image_task_entry['docker_references'].append(docker_repo)

				if docker_repo not in full_docker_ref:
					full_docker_ref.append(docker_repo)

		docker_image_for_git_task_list[git_repo_id] = docker_image_task_entry

def load_github_resource(uri):
	try:
		response = requests.get(uri)
		yamlcontent = yaml.safe_load(response.content)
		return yamlcontent
	except IOError as e:
		print e
		print >> sys.stderr, 'Not able to load content from ' + uri
		sys.exit(1)


def handle_resources():

	#task_list = identify_all_task_files(src_pipeline)
	# Identify all tasks and docker images used in the final pipeline
	# Add docker images as resources in source pipeline
	# Then rejigger the resources to be input and output in the blobuploader pipeline

	docker_image_analysis_map = analyze_pipeline_for_docker_images(None, offline_pipeline)
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

def find_match_in_list(list, name):
	for entry in list:
		if entry['name'] == name + '-tarball':
			return entry
		elif entry['name'] == name:
			return entry

	return None



	# Sample docker_image_analysis_map
	# {'pcf-pipelines': {'docker_references': [{'repository': 'pcfnorm/rootfs'}],
	#                    'git_path': 'https://raw.githubusercontent.com/pivotal-cf/pcf-pipelines/master/',
	#                    'task_defns': [{'create-terraform-state': {'file': 'install-pcf/azure/tasks/create-initial-terraform-state/task.yml',
	#                                                               'image': {'repository': 'pcfnorm/rootfs'},
	#                                                               'inputs': [{'name': 'pcf-pipelines'}],
	#                                                               'script': 'pcf-pipelines/install-pcf/azure/tasks/create-initial-terraform-state/task.sh'}},
	#                                   {'wipe-env': {'file': 'install-pcf/azure/tasks/wipe-env/task.yml',
	#                                                 'image': {'repository': 'pcfnorm/rootfs'},
	#                                                 'inputs': [{'name': 'pcf-pipelines'},
	#                                                            {'name': 'terraform-state'}],
	#                                                 'script': 'pcf-pipelines/install-pcf/azure/tasks/wipe-env/task.sh'}},
	#                                   {'create-infrastructure': {'file': 'install-pcf/azure/tasks/create-infrastructure/task.yml',
	#                                                              'image': {'repository': 'pcfnorm/rootfs'},
	#                                                              'inputs': [{'name': 'pcf-pipelines'},
	#                                                                         {'name': 'opsman-metadata'},
	#                                                                         {'name': 'terraform-state'}],
	#                                                              'script': 'pcf-pipelines/install-pcf/azure/tasks/create-infrastructure/task.sh'}},
	#                                   {'upload-tile': {'file': 'tasks/upload-product-and-stemcell/task.yml',
	#                                                    'image': {'repository': 'pcfnorm/rootfs'},
	#                                                    'inputs': [{'name': 'pivnet-product'},
	#                                                               {'name': 'pcf-pipelines'}],
	#                                                    'script': 'pcf-pipelines/tasks/upload-product-and-stemcell/task.sh'}},
	#                                   {'stage-tile': {'file': 'tasks/stage-product/task.yml',
	#                                                   'image': {'repository': 'pcfnorm/rootfs'},
	#                                                   'inputs': [{'name': 'pcf-pipelines'},
	#                                                              {'name': 'pivnet-product'}],
	#                                                   'script': 'pcf-pipelines/tasks/stage-product/task.sh'}},
	#                                   {'configure-ert': {'file': 'tasks/config-ert/task.yml',
	#                                                      'image': {'repository': 'pcfnorm/rootfs'},
	#                                                      'inputs': [{'name': 'pcf-pipelines'}],
	#                                                      'script': 'pcf-pipelines/tasks/config-ert/task.sh'}},
	#                                   {'deploy-ert': {'file': 'tasks/apply-changes/task.yml',
	#                                                   'image': {'repository': 'pcfnorm/rootfs'},
	#                                                   'inputs': [{'name': 'pcf-pipelines'}],
	#                                                   'script': 'pcf-pipelines/tasks/apply-changes/task.sh'}}]},
	 # 'target-pipeline': {'docker_references': [{'repository': 'czero/cflinuxfs2'}],
	 #                     'git_path': 'pipeline',
	 #                     'job_tasks_references': [{'bootstrap-terraform-state': [{'file': 'pcf-pipelines/install-pcf/azure/tasks/create-initial-terraform-state/task.yml',
	 #                                                                              'git_resource': 'pcf-pipelines',
	 #                                                                              'task': 'create-terraform-state'}]},
	 #                                              {'wipe-env': [{'file': 'pcf-pipelines/install-pcf/azure/tasks/wipe-env/task.yml',
	 #                                                             'git_resource': 'pcf-pipelines',
	 #                                                             'task': 'wipe-env'}]},
	 #                                              {'create-infrastructure': [{'file': None,
	 #                                                                          'git_resource': 'pcf-pipelines',
	 #                                                                          'task': 'upload-opsman'},
	 #                                                                         {'file': 'pcf-pipelines/install-pcf/azure/tasks/create-infrastructure/task.yml',
	 #                                                                          'git_resource': 'pcf-pipelines',
	 #                                                                          'task': 'create-infrastructure'}]},
	 #                                              {'config-opsman-auth': [{'file': None,
	 #                                                                       'git_resource': 'pcf-pipelines',
	 #                                                                       'task': 'config-opsman'}]},
	 #                                              {'config-director': [{'file': None,
	 #                                                                    'git_resource': 'pcf-pipelines',
	 #                                                                    'task': 'config-director'}]},
	 #                                              {'deploy-director': [{'file': None,
	 #                                                                    'git_resource': 'pcf-pipelines',
	 #                                                                    'task': 'deploy-director'}]},
	 #                                              {'upload-ert': [{'file': 'pcf-pipelines/tasks/upload-product-and-stemcell/task.yml',
	 #                                                               'git_resource': 'pcf-pipelines',
	 #                                                               'task': 'upload-tile'},
	 #                                                              {'file': 'pcf-pipelines/tasks/stage-product/task.yml',
	 #                                                               'git_resource': 'pcf-pipelines',
	 #                                                               'task': 'stage-tile'}]},
	 #                                              {'configure-ert': [{'file': 'pcf-pipelines/tasks/config-ert/task.yml',
	 #                                                                  'git_resource': 'pcf-pipelines',
	 #                                                                  'task': 'configure-ert'}]},
	 #                                              {'deploy-ert': [{'file': 'pcf-pipelines/tasks/apply-changes/task.yml',
	 #                                                               'git_resource': 'pcf-pipelines',
	 #                                                               'task': 'deploy-ert'}]}],
	 #                     'task_defns': [{'upload-opsman': {'image': {'repository': 'czero/cflinuxfs2'}}},
	 #                                    {'config-opsman': {'image': {'repository': 'czero/cflinuxfs2'}}},
	 #                                    {'config-director': {'image': {'repository': 'czero/cflinuxfs2'}}},
	 #                                    {'deploy-director': {'image': {'repository': 'czero/cflinuxfs2'}}}]}}
	#
	# Another sample output
	#
	# {'nsx-t-gen-pipeline': {'docker_references': [{'repository': 'nsxedgegen/nsx-t-gen-worker'}],
	#                         'git_path': 'https://raw.githubusercontent.com/sparameswaran/nsx-t-gen/master/',
	#                         'task_defns': [{'install-nsx-t': {'file': 'tasks/install-nsx-t/task.yml',
	#                                                           'image': {'repository': 'nsxedgegen/nsx-t-gen-worker'},
	#                                                           'inputs': [{'name': 'nsx-t-gen-pipeline'},
	#                                                                      {'name': 'nsx-mgr-ova'},
	#                                                                      {'name': 'nsx-ctrl-ova'},
	#                                                                      {'name': 'nsx-edge-ova'},
	#                                                                      {'name': 'nsxt-ansible'},
	#                                                                      {'name': 'ovftool'}],
	#                                                           'script': 'nsx-t-gen-pipeline/tasks/install-nsx-t/task.sh'}},
	#                                        {'add-nsx-t-routers': {'file': 'tasks/add-nsx-t-routers/task.yml',
	#                                                               'image': {'repository': 'nsxedgegen/nsx-t-gen-worker'},
	#                                                               'inputs': [{'name': 'nsx-t-gen-pipeline'},
	#                                                                          {'name': 'nsxt-ansible'}],
	#                                                               'script': 'nsx-t-gen-pipeline/tasks/add-nsx-t-routers/task.sh'}},
	#                                        {'config-nsx-t-extras': {'file': 'tasks/config-nsx-t-extras/task.yml',
	#                                                                 'image': {'repository': 'nsxedgegen/nsx-t-gen-worker'},
	#                                                                 'inputs': [{'name': 'nsx-t-gen-pipeline'}],
	#                                                                 'script': 'nsx-t-gen-pipeline/tasks/config-nsx-t-extras/task.sh'}}]},
	 # 'target-pipeline': {'docker_references': [],
	 #                     'git_path': 'pipeline',
	 #                     'job_tasks_references': [{'install-nsx-t': [{'file': 'nsx-t-gen-pipeline/tasks/install-nsx-t/task.yml',
	 #                                                                  'git_resource': 'nsx-t-gen-pipeline',
	 #                                                                  'task': 'install-nsx-t'}]},
	 #                                              {'add-nsx-t-routers': [{'file': 'nsx-t-gen-pipeline/tasks/add-nsx-t-routers/task.yml',
	 #                                                                      'git_resource': 'nsx-t-gen-pipeline',
	 #                                                                      'task': 'add-nsx-t-routers'}]},
	 #                                              {'config-nsx-t-extras': [{'file': 'nsx-t-gen-pipeline/tasks/config-nsx-t-extras/task.yml',
	 #                                                                        'git_resource': 'nsx-t-gen-pipeline',
	 #                                                                        'task': 'config-nsx-t-extras'}]},
	 #                                              {'standalone-install-nsx-t': [{'file': 'nsx-t-gen-pipeline/tasks/install-nsx-t/task.yml',
	 #                                                                             'git_resource': 'nsx-t-gen-pipeline',
	 #                                                                             'task': 'install-nsx-t'}]},
	 #                                              {'standalone-add-nsx-t-routers': [{'file': 'nsx-t-gen-pipeline/tasks/add-nsx-t-routers/task.yml',
	 #                                                                                 'git_resource': 'nsx-t-gen-pipeline',
	 #                                                                                 'task': 'add-nsx-t-routers'}]},
	 #                                              {'standalone-config-nsx-t-extras': [{'file': 'nsx-t-gen-pipeline/tasks/config-nsx-t-extras/task.yml',
	 #                                                                                   'git_resource': 'nsx-t-gen-pipeline',
	 #                                                                                   'task': 'config-nsx-t-extras'}]}],
	 #                     'task_defns': []}}
	 #

def handle_offline_tasks():

	resource_lookup_map = {}
	job_tasks_references = docker_image_analysis_map['pipeline_task_docker_references']['target-pipeline']['job_tasks_references']
	for offline_job in offline_pipeline['jobs']:

		found_job_tasks_reference = False
		for job_tasks_reference in job_tasks_references:
			ref_map_target_job_name = job_tasks_reference.keys()[0]
			for job_inner_task in job_tasks_reference[ref_map_target_job_name]:

				target_task_name = job_inner_task.get('task')
				target_task_file = job_inner_task.get('file')

				if offline_job['name'] == ref_map_target_job_name:
					found_job_tasks_reference = True
					break

		plan_index = 0
		saved_plan_inputs = []

		for plan in offline_job['plan']:
			#print '## Current job: {}, set of keys inside plan: {} and type: {}\n\n\n'.format(ref_map_target_job_name, plan.keys(), type(plan))

			non_resource_related_entry_map = {}
			last_saved_plan_entry_map = {}

			#print '\n^^^^^ STARTING OFF: JOB: {}, PLAN : {}, Saved INPUTS: {} '.format(ref_map_target_job_name, plan, saved_plan_inputs)
			for plan_key in plan:

				plan_entry = plan[plan_key]
				if plan_key in ['aggregate' , 'do' ]:

					original_aggregate = copy.copy(plan_entry)
					handle_aggregated_plan_entry(plan, plan_key, original_aggregate, resource_lookup_map, job_tasks_reference)

					for new_entry in plan[plan_key]:
						for entry_key, entry_value in new_entry.items():
							if entry_key == 'get' and entry_value not in saved_plan_inputs:
								saved_plan_inputs.append(entry_value)


					#print 'Final plan entry: {} and plan:{}'.format(plan[plan_key], plan)
				elif plan_key in [ 'file', 'task' ]:
					inline_task_details(plan, resource_lookup_map, ref_map_target_job_name, saved_plan_inputs)

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

						plan.pop('get', None)
				else:
					# Just save the entry as is (we are only worried abt tasks and gets that need modification)
					# Check if the task has already been processed!!
					embedded_task = plan.get('task')
					# if embedded_task is not None and 'offlined' not in embedded_task:
					# 	print 'WARNING!! Inlined task : {} in Job: {} needs to be handled!!'.format(embedded_task, ref_map_target_job_name )

					#plan[plan_key][nested_entry_key] = plan_entry[nested_entry_key]
					#print 'Updated Plan : {} , plan_key: {} and plan entry is : {}'.format(plan, plan_key, plan_entry)
					#print '####### \n\nPlan getting skipped over: {}\n\n'.format(plan)

			# Pop off any image references from the plan
			# We want to purely go with image_resource and not image
			plan.pop('image', None)

			plan_index += 1
	print 'Finished handling of all jobs in offline pipeline'

def handle_aggregated_plan_entry(plan, aggregate_key, original_aggregate, resource_lookup_map, job_tasks_reference):

	non_resource_related_entry_map = {}
	last_saved_plan_entry_map = {}

	original_aggregate_list = plan[aggregate_key]
	new_aggregate_list = []

	for entry in original_aggregate_list:
		#print 'Entry within aggregate: {}'.format(entry)
		# print 'Entry keys within aggregate: {}'.format(entry.keys)

		#nested_entry_key  = plan_entry.keys()[0]

		# if nested_entry_key == 'get':
		# 	original_get_resource_name = plan_entry['get']
		#
		# 	new_nested_plan_entries = handle_get_resource_details(original_get_resource_name, job_tasks_reference)
		# 	print 'Got nested plan entries as {} for plan_entry-get: {}'.format(new_nested_plan_entries, nested_entry_key)
		# 	if new_nested_plan_entries is not None:
		# 		for nested_plan_entry in new_nested_plan_entries:
		# 			if nested_plan_entry not in plan[plan_key]:
		# 				plan[plan_key].append(nested_plan_entry)

		for nested_entry_key, nested_entry_value in entry.items():
			#print 'nested_entry key: {} and value: {}'.format(nested_entry_key, nested_entry_value)
			#print 'Saved so far: {}'.format(last_saved_plan_entry_map)
			if nested_entry_key == 'get':

				original_get_resource_name = nested_entry_value

				# Rare cases where the get is tagged as pivnet-prodcut
			    # - get: pivnet-product
			    #   resource: pivotal-container-service
			    #   params: {globs: ["pivotal-container-service*.pivotal"]}

				matching_resource = find_match_in_list(offline_pipeline['resources'], original_get_resource_name)
				if matching_resource is None:
					aliased_resource_name = original_get_resource_name
					if entry.get('resource') is not None:
						original_get_resource_name = entry.get('resource')
						entry.pop('resource', None)
						resource_lookup_map[aliased_resource_name] = original_get_resource_name

				new_nested_entries = handle_get_resource_details(original_get_resource_name, job_tasks_reference)
				#print 'Got nested plan entries as {} '.format(new_nested_entries)
				if new_nested_entries is not None:
					#for nested_entry in new_nested_entries:
						#plan[plan_key].append(nested_entry)
					for new_nested_entry  in new_nested_entries:
						for new_nested_entry_key, new_nested_entry_value  in new_nested_entry.items():

							#print 'New modified entry {}: {}\n\n'.format(new_nested_entry_key, new_nested_entry_value)
							if 'docker' not in new_nested_entry_key:
								last_saved_plan_entry_map[new_nested_entry_key] = new_nested_entry_value

								# Close out previously saved current_plan_entry_map entry
								if last_saved_plan_entry_map:
									new_aggregate_list.append(last_saved_plan_entry_map )
									last_saved_plan_entry_map = { }
							else:
								new_aggregate_list.append( { new_nested_entry_key : new_nested_entry_value } )

					#print '\nCurrent Plan key:  {}  and saved plan_entry_map: {}'.format(plan[plan_key], last_saved_plan_entry_map)
			else:
				if nested_entry_key == 'resource':
					continue

				last_saved_plan_entry_map[nested_entry_key] = nested_entry_value
				#print 'For non-get plan entry {} : {} and saved plan_entry_map: {} '.format(nested_entry_key, nested_entry_value, last_saved_plan_entry_map)


	if last_saved_plan_entry_map:
		new_aggregate_list.append(last_saved_plan_entry_map)

	# Save this as the new plan entry against the aggregate key
	plan[aggregate_key] = new_aggregate_list

def handle_get_resource_details(original_get_resource_name, job_tasks_reference):

	new_nested_plan_entries = []
	original_resource_type = 'file'

	matching_orginal_resource = find_match_in_list(src_pipeline['resources'], original_get_resource_name)
	if matching_orginal_resource is not None:
		original_resource_type = matching_orginal_resource['type']

	matching_offline_resource = find_match_in_list(offline_pipeline['resources'], original_get_resource_name)
	if matching_offline_resource is not None:
		matching_tarballed_resource = matching_offline_resource

	if matching_orginal_resource is None:
		print 'Unable to find matching resource: {}'.format(original_get_resource_name)
		return None

	# Add the github tarball as input if its a match against git resources in offline pipeline
	if original_resource_type in [ 'file-url', 'file', 's3' ]:
		# Add original input resource as is
		new_nested_plan_entries.append(  { 'get' :  original_get_resource_name } )

	elif original_resource_type in [ 'docker', 'docker-image', 'git' ]:

		resource_id = original_get_resource_name

		job_name = job_tasks_reference.keys()[0]

		# Sample job_tasks_ref
		# {'standalone-install-nsx-t': [{'file': 'nsx-t-gen-pipeline/tasks/install-nsx-t/task.yml',
   	 	#                                'git_resource': 'nsx-t-gen-pipeline',
   	 	#                                'task': 'install-nsx-t'}]},

		docker_image_tarball_name = None
		for job_task in job_tasks_reference[job_name]:
			#print 'Job tasks is {} and Task is {}'.format(job_tasks_reference, job_task)
			matching_task_name = job_task['task']

			for task_defn_map in docker_image_analysis_map['pipeline_task_docker_references'][resource_id]['task_defns']:
				for key in task_defn_map:
					if key == matching_task_name:
						task_defn = task_defn_map[key]
						docker_image_ref = task_defn['image']
						original_task_inputs = task_defn['inputs']
						original_task_outputs = task_defn['outputs']
						original_task_script = task_defn['script']

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

	elif original_resource_type in [ 'pivnet' ]:
		# Special handling for Pivnet Tiles
		new_nested_plan_entries.append( { 'get' :  original_get_resource_name } )

		# Check for stemcells associated with the tile
		matching_stemcell_resource = None
		matching_stemcell_resource = find_match_in_list(offline_pipeline['resources'], original_get_resource_name + '-stemcell')
		if matching_stemcell_resource is not None:
			new_nested_plan_entries.append( { 'get' :  matching_stemcell_resource['name'] } )

		# Check for tarball associated with the tile
		matching_tile_tarball_resource = None
		matching_tile_tarball_resource = find_match_in_list(offline_pipeline['resources'], original_get_resource_name + '-tarball')
		if matching_tile_tarball_resource is not None:
			new_nested_plan_entries.append( { 'get' :  matching_tile_tarball_resource['name'] } )


	return new_nested_plan_entries

def inline_task_details(plan, resource_lookup_map, ref_map_target_job_name, saved_plan_inputs):

	given_task_name = plan.get('task')
	given_task_file = plan.get('file')
	given_task_params = plan.get('params')

	# print 'Inline Task details for Ref map Job name:{}, for plan:{}, for task: {} with file:{} \
	# 		and given plan level inputs:{} \n\n'.format( \
	# 				ref_map_target_job_name, plan, given_task_name, \
	# 				given_task_file, saved_plan_inputs)

	# If the plan task has already been inlined, return
	if given_task_file is None and 'offlined-' in given_task_name:
		return
	elif given_task_file is None:
		handle_preinlined_task_details(plan, saved_plan_inputs)
		return

	index = given_task_file.index('/')
	git_resource_id = given_task_file[:index]

	# If the task is a match, then proceed with updating the task reference to use tarballed docker image
	# and special handling

	docker_image_tarball_name = None
	docker_tarball_regex = None

	original_task_outputs = None
	original_task_script = None
	original_task_inputs = []
	for entry in saved_plan_inputs:
		original_task_inputs.append( { 'name' : entry } )

	task_defn_found = False
	for task_defn_map in docker_image_analysis_map['pipeline_task_docker_references'][git_resource_id]['task_defns']:
		if task_defn_found:
			break

		#print 'Task Defn Map: {}, seaching for: {} and task file:{}'.format(task_defn_map, given_task_name, given_task_file)
		for key in task_defn_map:
			task_defn = task_defn_map[key]

			#print 'Task Defn : {}, seaching for: {} and task file:{}'.format(task_defn, given_task_name, given_task_file)
			if task_defn['file'] in given_task_file:
				docker_image_ref = task_defn['image']

				if task_defn['inputs'] is not None:
					original_task_inputs.extend(task_defn['inputs'])

				original_task_outputs = task_defn['outputs']
				original_task_script = task_defn['script']

				version = 'latest' if docker_image_ref.get('tag') is None else docker_image_ref.get('tag')
				docker_image_tarball_name = '%s-%s-%s-tarball' % (docker_image_ref['repository'].replace('/', '-'), version, 'docker')
				matching_tarballed_docker_resource = find_match_in_list(offline_pipeline['resources'], docker_image_tarball_name)

				docker_image_ref['tag'] = version
				docker_image_tarball_name = '%s-%s-%s' % (docker_image_ref['repository'].replace('/', '-'), version, 'docker')
				docker_tarball_regex = '%s/docker/%s.(.*)' % ( 'resources', docker_image_tarball_name)

				source_bucket_details = copy.copy(default_bucket_config)
				source_bucket_details['regexp'] = docker_tarball_regex
				#print '\n## Found Task Defn: {} Original Task Inputs: {} and original_task_script: \
				#	 		{}\n'.format(given_task_name, original_task_inputs, original_task_script)
				#

				task_defn_found = True
				break

	image_source = {
						'type': 's3',
						'source' : source_bucket_details,
						'params' : { 'unpack': True }

					}

	plan['config'] = { 'platform' : 'linux', 'image_resource': image_source }
	#print 'New Plan Entry: ####### {} #####'.format(plan)

	# Start with the docker image tarball
	new_task_inputs = [ { 'name': docker_image_tarball_name } ]
	new_task_outputs = original_task_outputs

	tarball_resources_to_extract_map = {}

	#print '\n## Task: {} Original Task Inputs: {} and original_task_script: {}\n'.format(given_task_name,
	# 														original_task_inputs, original_task_script)

	matching_tarballed_resource = None
	for original_input in original_task_inputs:

		matching_tarballed_git_resource = None
		#print 'Original Input is : {}'.format(original_input)
		matching_tarballed_git_resource = find_match_in_list(offline_pipeline['resources'], original_input['name'] + '-tarball')

		if matching_tarballed_git_resource is not None:
			# Add the github tarball as input if its a match against git resources in offline pipeline
			new_task_inputs.append( { 'name' : matching_tarballed_git_resource['name'] } )
			if new_task_outputs is None:
				new_task_outputs = []
			new_task_outputs.append( { 'name' : original_input['name'] } )

			# Use same input name in the map as coming with its registered name
			tarball_resources_to_extract_map[original_input['name'] ] = original_input['name']

		else:
			matching_resource = find_match_in_list(offline_pipeline['resources'], original_input['name'])
			if matching_resource is not None:
				# add the input as is
				new_task_inputs.append( { 'name': original_input['name'] } )
			else:
				aliased_resource_name = original_input['name']
				original_underlying_resource = resource_lookup_map[aliased_resource_name]
				if original_underlying_resource is not None:

					matching_tarballed_resource = find_match_in_list(offline_pipeline['resources'], original_underlying_resource + '-tarball')
					if matching_tarballed_resource is not None:
						new_task_inputs.append( { 'name' : matching_tarballed_resource['name'] } )
						if new_task_outputs is None:
							new_task_outputs = []
						new_task_outputs.append( { 'name' : aliased_resource_name } )
						# Map the aliased name against registered resource name
						tarball_resources_to_extract_map[aliased_resource_name ] = original_underlying_resource
					else:
						new_task_inputs.append( { 'name': original_underlying_resource } )
				else:
					print '\n## Unable to find associated Resource for : {}'.format(original_input['name'])
				#complete_plan_entry = plan['get']

			#print '\n## Task Input not a tarball: {}\n'.format(original_input)

	run_command_str = ''
	run_command_str_list = list(run_command_str)
	run_command_str_list.append('ls -lR;')

	for tarball_resource in tarball_resources_to_extract_map.keys():
		if matching_tarballed_resource is None or (matching_tarballed_resource['name'] not in tarball_resource):
			run_command_str_list.append('cd %s; tar -zxf ../%s-tarball/*; cd ..;' % (tarball_resource, tarball_resources_to_extract_map[tarball_resource]))

	run_command_str_list.append('echo Starting main task execution!!;')
	run_command_str_list.append(original_task_script)

	full_run_command = { 'path' : '/bin/bash'}
	full_run_command['args'] = [ '-exc' , "".join(run_command_str_list) ]
	plan['config']['run'] = full_run_command
	plan['config']['inputs'] = clean_list(new_task_inputs)
	plan.pop('file', None)

	plan['task'] = 'offlined-' + plan['task']

	if new_task_outputs is not None:
		plan['config']['outputs'] = clean_list(new_task_outputs)

	#print 'Final inlined task plan: {}'.format(plan)

def handle_preinlined_task_details(plan, saved_plan_inputs):

	given_task_name = plan.get('task')
	given_task_params = plan.get('params')

	# print 'Pre-inlined Task details top Job name:{}, for task:{} and given plan level inputs:{} \n\n'.format(
	# 				plan, given_task_name, saved_plan_inputs)

	# If the plan task has already been inlined, return
	if 'offlined-' in given_task_name:
		return

	# If the task is a match, then proceed with updating the task reference to use tarballed docker image
	# and special handling

	docker_image_tarball_name = None
	docker_tarball_regex = None

	original_task_script = plan['config']['run']['args'][1]
	original_task_inputs = []
	for entry in saved_plan_inputs:
		original_task_inputs.append( { 'name' : entry } )

	original_task_outputs = plan.get('outputs')
	original_task_run = plan['config']['run']

	# Start with the docker image tarball
	new_task_inputs = []
	new_task_outputs = original_task_outputs
	#print 'New Task Outputs: {}'.format(new_task_outputs)

	tarball_resources_to_extract_map = {}

	#print '\n## Task: {} Original Task Inputs: {} and original_task_script: {}\n'.format(given_task_name,
	# 														original_task_inputs, original_task_script)

	#print 'Finding matching input sources and extracting tarball'
	for original_input in original_task_inputs:

		matching_tarballed_git_resource = None
		#print 'Finding matching input source: {}'.format(original_input['name'])
		#print 'Original Input is : {}'.format(original_input)
		matching_tarballed_resource = find_match_in_list(offline_pipeline['resources'], original_input['name'])

		if matching_tarballed_resource is None:
			matching_tarballed_resource = find_match_in_list(offline_pipeline['resources'], original_input['name'] + '-tarball')

		if matching_tarballed_resource is not None:
			# Add the github tarball as input if its a match against git resources in offline pipeline
			new_task_inputs.append( { 'name' : matching_tarballed_resource['name'] } )
			if new_task_outputs is None:
				new_task_outputs = []

			if 'tarball' not in original_input['name']:
				new_task_outputs.append( { 'name' : original_input['name'] } )

			# Use same input name in the map as coming with its registered name
			tarball_resources_to_extract_map[original_input['name'] ] = original_input['name']

		else:
			matching_resource = find_match_in_list(offline_pipeline['resources'], original_input['name'])
			if matching_resource is not None:
				# add the input as is
				new_task_inputs.append( { 'name': original_input['name'] } )
			else:
				aliased_resource_name = original_input['name']
				original_underlying_resource = resource_lookup_map[aliased_resource_name]
				if original_underlying_resource is not None:

					matching_tarballed_resource = find_match_in_list(offline_pipeline['resources'], original_underlying_resource + '-tarball')
					if matching_tarballed_resource is not None:
						new_task_inputs.append( { 'name' : matching_tarballed_resource['name'] } )
						if new_task_outputs is None:
							new_task_outputs = []
						new_task_outputs.append( { 'name' : aliased_resource_name } )
						# Map the aliased name against registered resource name
						tarball_resources_to_extract_map[aliased_resource_name ] = original_underlying_resource
					else:
						new_task_inputs.append( { 'name': original_underlying_resource } )
				else:
					print '\n## Unable to find associated Resource for : {}'.format(original_input['name'])
				#complete_plan_entry = plan['get']

			#print '\n## Task Input not a tarball: {}\n'.format(original_input)

	plan['config']['image_resource'] = {
										'params': { 'unpack' : True} ,
										'type': 's3',
										'source' : matching_tarballed_resource['source']
									}
	plan['config'].pop('image', None)


	run_command_str = ''
	run_command_str_list = list(run_command_str)
	run_command_str_list.append('ls -lR;')
	for tarball_resource in tarball_resources_to_extract_map.keys():
		if matching_tarballed_resource['name'] not in tarball_resource:
			run_command_str_list.append('cd %s; tar -zxf ../%s-tarball/*; cd ..;' % (tarball_resource, tarball_resources_to_extract_map[tarball_resource]))

	run_command_str_list.append('echo Starting main task execution!!;')
	run_command_str_list.append(original_task_script)

	full_run_command = { 'path' : '/bin/bash'}
	full_run_command['args'] = [ '-exc' , "".join(run_command_str_list) ]
	plan['config']['run'] = full_run_command
	plan['config']['inputs'] = clean_list(new_task_inputs)
	plan.pop('file', None)

	plan['task'] = 'offlined-' + plan['task']

	if new_task_outputs is not None:
		plan['config']['outputs'] = clean_list(new_task_outputs)

	#print 'Final inlined task plan: {}'.format(plan)

def clean_list(given_list):
	cleanedup_list = []
	for entry in given_list:
		if entry not in cleanedup_list:
			cleanedup_list.append(entry)
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
	resource['regexp'] = '%s/docker/%s-%s-docker.(.*)' % ( 'resources', resource['name'], tag)

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
	resource['regexp'] = '%s/%s/%s-(.*).tgz' % ( 'resources', 'git', resource['name'])

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
	resource['regexp'] = '%s/pivnet-tile/%s/(.*).pivotal' % ( 'resources', resource['name'])

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
	stemcell_regexp = '%s/pivnet-tile/%s-stemcell/bosh-(.*).tgz' % ( 'resources', resource['name'])
	output_stemcell_resource = copy.copy(resource)
	output_stemcell_resource['name'] = 'output-%s-%s' % ('stemcell', resource['name'])
	output_stemcell_resource['regexp'] = stemcell_regexp
	final_output_resources.append(output_stemcell_resource)

	combined_tile_stemcell_regexp = '%s/pivnet-tile/%s-tarball/%s-(.*).tgz' % ( 'resources', resource['name'], resource['name'])
	output_tile_stemcell_resource = copy.copy(resource)
	output_tile_stemcell_resource['name'] = 'output-%s-%s' % ('tile-stemcell', resource['name'])
	output_tile_stemcell_resource['regexp'] = combined_tile_stemcell_regexp
	final_output_resources.append(output_tile_stemcell_resource)

	offline_stemcell_resource = { 'name' : resource['name'] , 'type': 's3' , 'source': default_bucket_config }
	offline_stemcell_resource['source']['regexp'] = stemcell_regexp
	offline_stemcell_resource['name'] = '%s-%s' % (resource['name'], 'stemcell')

	offline_pipeline['resources'].append(offline_stemcell_resource)

	tile_tarball_regexp = '%s/pivnet-tile/%s-tarball/(.*).tgz' % ( 'resources', resource['name'])
	offline_tile_tarball_resource = { 'name' : '%s-tarball' % resource['name'] , 'type': 's3' , 'source': default_bucket_config }
	offline_tile_tarball_resource['source']['regexp'] = tile_tarball_regexp
	offline_tile_tarball_resource['name'] = '%s-%s' % (resource['name'], 'tarball')

	offline_pipeline['resources'].append(offline_tile_tarball_resource)

	return pivnet_tile_job_resource

def handle_pivnet_non_tile_resource(resource):

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

	#print 'Job for S3 resource: {}'.format(s3_job_resource)
	return s3_job_resource

def handle_default_resource(resource):

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

	#print 'Job for File resource: {}'.format(file_job_resource)
	return file_job_resource

def read_config(input_file):
	try:
		with open(input_file) as config_file:
			yamlcontent = yaml.safe_load(config_file)
			return yamlcontent
	except IOError as e:
		print >> sys.stderr, 'Problem with file, abort!'
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
				yaml.dump(content, output_file,  Dumper=NoAliasDumper)
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
