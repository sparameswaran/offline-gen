import os
import json
import copy
import yaml, sys
from pprint import pprint
import argparse
import traceback

repo = '.'
pipeline = None
params = None
default_bucket_config =  {}

CONFIG_FILE = 'input.yml'
DEFAULT_VERSION = '1.0'

input_config_file = None

src_pipeline = None

upload_individual_group_job = None
parallel_upload_job_plan_getter_aggregate = None
parallel_upload_job_plan_copy_job_aggregate = None
parallel_upload_job_plan_putter_aggregate = None
parallel_upload_job_plan_stemcell_putter_aggregate = None

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

def add_task_handler_as_resource(pipeline):
	task_handler_resource = { 'name': 'task_handler'}
	task_handler_resource['type'] = 's3'
	task_handler_resource['source'] = copy.copy(default_bucket_config)
	task_handler_resource['source']['regexp'] = '%s/handlers/%s' % ( 'resources', 'task_handler(.*)')
	pipeline['resources'].append(task_handler_resource)

def add_pipeline_repo_converter_as_resource(pipeline):
	pipeline_repo_converter_resource = { 'name': 'pipeline_repo_converter'}
	pipeline_repo_converter_resource['type'] = 's3'
	pipeline_repo_converter_resource['source'] = copy.copy(default_bucket_config)
	pipeline_repo_converter_resource['source']['regexp'] = '%s/handlers/%s' % ( 'resources', 'pipeline_repo_converter-(.*).py')
	pipeline['resources'].append(pipeline_repo_converter_resource)

def add_docker_image_as_resource(pipeline):
	new_docker_resource = { 'name': 'test-ubuntu-docker'}
	new_docker_resource['type'] = 'docker-image'
	new_docker_resource['source'] = { 'repository' : 'ubuntu', 'tag' : '17.04' }
	pipeline['resources'].append(new_docker_resource)

def handle_pipeline():
	global src_pipeline, upload_individual_group_job, \
		parallel_upload_job_plan_getter_aggregate, \
		parallel_upload_job_plan_copy_job_aggregate, \
		parallel_upload_job_plan_putter_aggregate, \
		parallel_upload_job_plan_stemcell_putter_aggregate

	print('Got repo: {} and pipeline: {}'.format(repo, pipeline))
	src_pipeline = read_config(repo + '/' + pipeline )
	#print 'Got src pipeline: {}'.format(src_pipeline)

	# REMOVE ME - SABHA
	add_docker_image_as_resource(src_pipeline)

	src_pipeline['nsx_t_gen_params'] = None
	blobstore_upload_pipeline = copy.copy(src_pipeline)
	offline_pipeline = copy.copy(src_pipeline)
	try:
		offline_pipeline['resources'] = []
		blobstore_upload_pipeline['resources'] = []
		#add_task_handler_as_resource(blobstore_upload_pipeline)
		add_pipeline_repo_converter_as_resource(blobstore_upload_pipeline)

		blobstore_upload_pipeline['jobs'] = []
		blobstore_upload_pipeline['groups'] = [ ]
		blobstore_upload_pipeline['groups'].append({ 'name' : 'parallel-kickoff' })
		blobstore_upload_pipeline['groups'][0]['jobs'] = [ 'parallel-kickoff' ]
		upload_parallel_group_job = blobstore_upload_pipeline['groups'][0]['jobs']


		blobstore_upload_pipeline['groups'].append( {'name' : 'individual-kickoff' })
		blobstore_upload_pipeline['groups'][1]['jobs'] = [ ]
		upload_individual_group_job = blobstore_upload_pipeline['groups'][1]['jobs']

		blobstore_upload_pipeline['jobs'] = [ { 'name' : 'parallel-kickoff' } ]

		upload_parallel_job = blobstore_upload_pipeline['jobs'][0]
		upload_parallel_job['plan'] = []
		parallel_upload_job_plan = upload_parallel_job['plan']

		parallel_upload_job_plan.append( {'aggregate': [] })
		parallel_upload_job_plan.append( {'aggregate': [] })
		parallel_upload_job_plan.append( {'aggregate': [] })
		parallel_upload_job_plan.append( {'aggregate': [] })

		parallel_upload_job_plan_getter_aggregate = parallel_upload_job_plan[0]['aggregate']

		parallel_upload_job_plan_copy_job_aggregate = parallel_upload_job_plan[1]['aggregate']

		parallel_upload_job_plan_putter_aggregate = parallel_upload_job_plan[2]['aggregate']

		parallel_upload_job_plan_stemcell_putter_aggregate = parallel_upload_job_plan[3]['aggregate']

		handle_resources(src_pipeline, blobstore_upload_pipeline, offline_pipeline)
		#print 'Done handling resources: {}'.format(blobstore_upload_pipeline)

		pipeline_name_tokens = pipeline.split('/')
		target_pipeline_name = pipeline_name_tokens[len(pipeline_name_tokens) - 1]

		offline_pipeline_filename= 'offline-' + target_pipeline_name
		blobstore_upload_pipeline_filename = 'blobstore-upload-' + target_pipeline_name

		write_config(blobstore_upload_pipeline, blobstore_upload_pipeline_filename)
		#print 'offline pipeline: {}'.format(offline_pipeline)
		write_config(offline_pipeline, offline_pipeline_filename)
		print ''
		print 'Created offline pipeline: ' + offline_pipeline_filename
		print 'Created blobstore upload pipeline: ' + blobstore_upload_pipeline_filename

	except Exception as e:
		print('Error : {}'.format(e))
		print(traceback.format_exc())
		print >> sys.stderr, 'Error occured.'
		sys.exit(1)

def handle_git_docker_resources(src_pipeline, blobstore_upload_pipeline, offline_pipeline):
	for resource in src_pipeline['resources']:
		print 'Handling resource of type: {}'.format(resource)
		res_type = resource['type']

		docker_image_resources = []
		input_docker_image_resources = []
		output_docker_image_resources = []

		if res_type == 'git':
			identify_docker_resource(resource, src_pipeline,  blobstore_upload_pipeline)

def handle_git_docker_resource(resource, src_pipeline, blobstore_upload_pipeline, offline_pipeline):

	input_resource = copy.copy(resource)
	input_resource['name'] = 'input_' + resource['name']

	output_resource = { 'name' : 'output_' + resource['name'] }
	output_resource['type'] = 's3'
	output_resource['source'] = copy.copy(default_bucket_config)

	output_docker_images_resource = { 'name' : 'output_docker_image_' + resource['name'] }
	output_docker_images_resource['type'] = 's3'
	output_docker_images_resource['source'] = copy.copy(default_bucket_config)

	offline_resource = copy.copy(output_resource)
	offline_resource['name'] = resource['name']

	if offline_pipeline is not None:
		offline_pipeline['resources'].append(offline_resource)

	if blobstore_upload_pipeline is not None:
		blobstore_upload_pipeline['resources'].append(input_resource)
		blobstore_upload_pipeline['resources'].append(output_resource)
		blobstore_upload_pipeline['resources'].append(output_docker_images_resource)


	end_file = 'docker_images'
	output_docker_images_resource['source']['regexp'] = '%s/%s-docker-images/%s-(.*).yml' % ( 'resources', resource['name'], end_file)

	output_resource['source']['regexp'] = '%s/%s-tarball/%s-(.*).tgz' % ( 'resources', resource['name'], resource['name'])

	realized_output_resource_file_path = output_resource['name'] + '/' + resource['name'] + '-tarball.tgz'
	realized_output_docker_images_file_path = output_resource['name'] + '-docker-images/' + resource['name'] + '-docker-images.yml'

	copy_job = { 'name' : ( 'find_docker_images_in_%s' % (resource['name'])) }
	copy_job['plan'] = [
							{ 'get' : input_resource['name'] },
							{ 'get' : 'pipeline_repo_converter' },
							{ 'task' : 'find_docker_images' },
	 					  	{ 'put' : output_resource['name'] , 'params': { 'file' : realized_output_resource_file_path } },
							{ 'put' : output_docker_images_resource['name'] , 'params': { 'file' : realized_output_docker_images_file_path } }
						]

	task_files = locate_task_files(src_pipeline, resource)
	#task_files = str(task_files)[1:-1].replace(',' , ' ')
	#input_tasks = { 'tasks': task_files }

	task_config = { 'platform': 'linux'}
	task_config['inputs'] = [ { 'name': input_resource['name'] }, { 'name' : 'pipeline_repo_converter' } ]
	task_config['outputs'] = [ { 'name': output_resource['name'] }, { 'name': output_resource['name'] + '-docker-images' } ]
	task_config['image_resource'] = { 'type': 'docker-image' }
	task_config['image_resource']['source'] = { 'repository': 'nsxedgegen/offline-gen-worker'}


	task_config['run'] = { 'path' : '/bin/bash', 'args': [ '-exc' ] }
	task_run_command = ('echo "Searching for docker images within tasks of %s resource";  cd %s; python ../pipeline_repo_converter/pipeline_repo_converter*.py . "%s" "%s"   ../%s ;  tar cfz ../%s .; cd ..;  ls -l %s/') \
	% ( resource['name'],
		input_resource['name'],
		str(task_files),
		str(default_bucket_config),
		realized_output_docker_images_file_path,
		realized_output_resource_file_path,
		output_resource['name']
	 )


	task_config['run']['args'].append(task_run_command)

	copy_job['plan'][2] = {
	                       'task' : ('prepare-%s-bit-to-export') % (resource['name']),
	                       'config' : task_config
						  }

	blobstore_upload_pipeline['jobs'].append(copy_job)
	upload_individual_group_job.append(copy_job['name'])


def handle_resources(src_pipeline, blobstore_upload_pipeline, offline_pipeline):
	for resource in src_pipeline['resources']:
		print 'Handling resource of type: {}'.format(resource)
		res_type = resource['type']

		if res_type == 's3':
			handle_s3_resource(resource, blobstore_upload_pipeline, offline_pipeline)
		elif res_type == 'git':
			#handle_git_resource(resource, blobstore_upload_pipeline, offline_pipeline)
			handle_git_docker_resource(resource, src_pipeline, blobstore_upload_pipeline, offline_pipeline)
		elif res_type == 'docker-image':
			handle_docker_image(resource, blobstore_upload_pipeline, offline_pipeline)
		elif res_type == 'pivnet':
			if resource['source']['product_slug'] == 'ops-manager':
				handle_pivnet_non_tile_resource(resource, blobstore_upload_pipeline, offline_pipeline)
			else:
				handle_pivnet_tile_resource(resource, blobstore_upload_pipeline, offline_pipeline)
		else:
			handle_default_resource(resource, blobstore_upload_pipeline, offline_pipeline)

def clone_resource(resource, blobstore_upload_pipeline, offline_pipeline):
	input_resource = copy.copy(resource)
	input_resource['name'] = 'input_' + resource['name']

	output_resource = { 'name' : 'output_' + resource['name'] }
	output_resource['type'] = 's3'
	output_resource['source'] = copy.copy(default_bucket_config)

	offline_resource = copy.copy(output_resource)
	offline_resource['name'] = resource['name']

	if offline_pipeline is not None:
		offline_pipeline['resources'].append(offline_resource)

	if blobstore_upload_pipeline is not None:
		blobstore_upload_pipeline['resources'].append(input_resource)
		blobstore_upload_pipeline['resources'].append(output_resource)

	return [ input_resource, output_resource, offline_resource]


def handle_docker_image(resource, blobstore_upload_pipeline, offline_pipeline):
	print 'Handling docker image'


	cloned_resources = clone_resource(resource, blobstore_upload_pipeline, offline_pipeline)
	input_resource = cloned_resources[0]
	output_resource = cloned_resources[1]
	offline_resource = cloned_resources[2]

	version = resource['source']['tag']
	output_resource['source']['regexp'] = '%s/docker/%s' % ( 'resources', resource['name'] + '-(.*).tgz')

	# output_resource['source']['versioned_file']  is 'resources/test-ubuntu-docker-17.04.tgz'
	# final_file_path is output_test-ubuntu-docker/test-ubuntu-docker-17.04.tgz
	final_file_path = output_resource['name'] + '/' + resource['name'] + '-' + version + '.tgz'


	copy_job = { 'name' : ( 'copy_%s_to_blobstore' % (resource['name'])) }
	copy_job['plan'] =  [ { 'get' : input_resource['name'], 'params' : { 'rootfs': True } },
	 					  { 'task' : 'prepare-image-to-export' },
						  { 'put' : output_resource['name'] , 'params': { 'file' : final_file_path }  }
						]
	task_config = { 'platform': 'linux'}
	task_config['inputs'] = [ { 'name': input_resource['name'] } ]
	task_config['outputs'] = [ { 'name': output_resource['name'] } ]
	task_config['image_resource'] = { 'type': 'docker-image' }
	task_config['image_resource']['source'] = resource['source']
	task_config['run'] = { 'path' : '/bin/bash', 'args': [ '-exc' ] }
	task_run_command = (' \
echo "Exporting %s image"; \
mkdir export-directory; \
cd export-directory; \
cp ../%s/metadata.json .; \
mkdir rootfs && cd rootfs; \
cp ../../%s/rootfs.tar ..; \
tar -xf ../rootfs.tar --exclude="dev/*"  ;  \
echo "Packaging %s image"; \
tmp_version="%s" ; \
tar -czf   "../../%s/%s-${tmp_version}.tgz" . ;\
cd ..; \
ls -l ../%s/') \
% ( resource['name'],
    input_resource['name'],
	input_resource['name'],
	resource['name'],
	resource['source']['tag'],
	output_resource['name'],
	resource['name'],
	output_resource['name']
 )

	task_config['run']['args'].append(task_run_command)
	copy_job['plan'][1] = {
	                       'task' : ('prepare-%s-image-to-export') % (resource['name']),
	                       'config' : task_config
						  }

	blobstore_upload_pipeline['jobs'].append(copy_job)

	upload_individual_group_job.append(copy_job['name'])

	parallel_upload_job_plan_getter_aggregate.append({ 'get': input_resource['name'], 'params': {'rootfs': True} })
	parallel_upload_job_plan_copy_job_aggregate.append(copy_job['plan'][1])
	parallel_upload_job_plan_putter_aggregate.append({ 'put' : output_resource['name'] , 'params': { 'file' : final_file_path }  })


	print 'End bucket endpoint: %%{}%%'.format(output_resource['source']['endpoint'])

#
# - name: pivotal-container-service
#   type: pivnet
#   source:
#     api_token: ((pivnet_token))
#     product_slug: pivotal-container-service
#     product_version: ((pks_major_minor_version))
#     sort_by: semver

def handle_pivnet_non_tile_resource(resource, blobstore_upload_pipeline, offline_pipeline):
	print 'Handling pivnet image'
	cloned_resources = clone_resource(resource, blobstore_upload_pipeline, offline_pipeline)
	input_resource = cloned_resources[0]
	output_resource = cloned_resources[1]
	offline_resource = cloned_resources[2]

	end_file = resource['name']

	#print 'Resource is {}'.format(resource)
	#print 'End of file is : {}'.format(end_file)

	output_resource['source']['regexp'] = '%s/pivnet-non-tile/%s-(.*)' % ( 'resources', end_file)
	final_file_path = '%s/%s-*' % ( output_resource['name'], resource['name'])

	offline_resource = copy.copy(output_resource)
	offline_resource['name'] = resource['name']

	input_glob_param = { 'globs' : [ '*((iaas))*' ] }

	copy_job = { 'name' : ( 'copy_%s_to_blobstore' % (resource['name'])) }
	copy_job['plan'] = [
							{ 'get' : input_resource['name'] , 'params': input_glob_param },
							{ 'task' : 'prepare-bit-to-export' },
	 					  	{'put' : output_resource['name'] , 'params': { 'file' : final_file_path } }
						]
	task_config = { 'platform': 'linux'}
	task_config['inputs'] = [ { 'name': input_resource['name'] } ]
	task_config['outputs'] = [ { 'name': output_resource['name'] }]
	task_config['image_resource'] = { 'type': 'docker-image' }
	task_config['image_resource']['source'] = { 'repository': 'czero/cflinuxfs2'}
	task_config['params'] = { 'PIVNET_API_TOKEN': '((pivnet_token))', 'IAAS': '((iaas))'}
	task_config['run'] = { 'path' : '/bin/bash', 'args': [ '-exc' ] }
	task_run_command = (' \
echo "Copying %s bits"; \
    rm %s/version %s/metadata*; \
	file_name=$(ls %s/); \
	mv %s/* %s/%s-${file_name}; \
	ls -l %s/ ') \
	% ( resource['name'],
		input_resource['name'],
		input_resource['name'],
		input_resource['name'],
        input_resource['name'],
		output_resource['name'],
		resource['name'],
		output_resource['name']
	 )

	task_config['run']['args'].append(task_run_command)
	copy_job['plan'][1] = {
	                       'task' : ('prepare-%s-bit-to-export') % (resource['name']),
	                       'config' : task_config
						  }

	blobstore_upload_pipeline['jobs'].append(copy_job)
	upload_individual_group_job.append(copy_job['name'])

	parallel_upload_job_plan_getter_aggregate.append( { 'get' : input_resource['name'] , 'params': input_glob_param })
	parallel_upload_job_plan_copy_job_aggregate.append(copy_job['plan'][1])
	parallel_upload_job_plan_putter_aggregate.append({ 'put' : output_resource['name'] , 'params': { 'file' : final_file_path }  })

def handle_pivnet_tile_resource(resource, blobstore_upload_pipeline, offline_pipeline):

	print 'Handling pivnet image'

	cloned_resources = clone_resource(resource, blobstore_upload_pipeline, offline_pipeline)
	input_resource = cloned_resources[0]
	output_resource = cloned_resources[1]
	offline_resource = cloned_resources[2]

	end_file = resource['source']['product_slug']

	output_stemcell_resource = { 'name' : 'output_stemcell_' + resource['name'] }
	output_stemcell_resource['type'] = 's3'
	output_stemcell_resource['source'] = copy.copy(default_bucket_config)

	end_file = resource['name']
	output_resource['source']['regexp'] = '%s/pivnet-tile/%s-(.*)' % ( 'resources', end_file)
	final_file_path = '%s/%s-*' % ( output_resource['name'], resource['name'])

	output_stemcell_resource['source']['regexp'] = '%s/pivnet-stemcell/bosh-(.*).tgz' % ( 'resources')
	final_stemcell_file_path = '%s/bosh-*.tgz' % (output_stemcell_resource['name'])

	offline_stemcell_resource = copy.copy(output_stemcell_resource)
	offline_stemcell_resource['name'] = 'stemcell_' + resource['name']
	offline_pipeline['resources'].append(offline_stemcell_resource)

	blobstore_upload_pipeline['resources'].append(output_stemcell_resource)

	input_glob_param = { 'globs' : [ '*.pivotal' ] }

	copy_job = { 'name' : ( 'copy_%s_to_blobstore' % (resource['name'])) }
	copy_job['plan'] = [
							{ 'get' : input_resource['name'] , 'params': input_glob_param },
							{ 'task' : 'prepare-bit-to-export' },
	 					  	{'put' : output_resource['name'] , 'params': { 'file' : final_file_path } },
							{'put' : output_stemcell_resource['name'] , 'params': { 'file' : final_stemcell_file_path } }
						]
	task_config = { 'platform': 'linux'}
	task_config['inputs'] = [ { 'name': input_resource['name'] } ]
	task_config['outputs'] = [ { 'name': output_resource['name'] }, {'name': output_stemcell_resource['name'] } ]
	task_config['image_resource'] = { 'type': 'docker-image' }
	task_config['image_resource']['source'] = { 'repository': 'czero/cflinuxfs2'}
	task_config['params'] = { 'PIVNET_API_TOKEN': '((pivnet_token))', 'IAAS': '((iaas))'}
	task_config['run'] = { 'path' : '/bin/bash', 'args': [ '-exc' ] }
	task_run_command = (' \
echo "Copying %s bits"; \
TILE_FILE_PATH=`find ./%s -name *.pivotal | sort | head -1`; \
tile_metadata=$(unzip -l $TILE_FILE_PATH | grep "metadata" | grep "ml$" | awk \'{print $NF}\' ); \
stemcell_version_reqd=$(unzip -p $TILE_FILE_PATH $tile_metadata | grep -A4 stemcell | grep version: \
        | grep -Ei "[0-9]{4,}" | awk \'{print $NF}\' | sed "s/\'//g" ); \
pivnet-cli login --api-token=$PIVNET_API_TOKEN ; \
pivnet-cli download-product-files -p "stemcells" -r $stemcell_version_reqd -g "*${IAAS}*" --accept-eula; \
SC_FILE_PATH=`find ./ -name *.tgz`; \
if [ -f "$SC_FILE_PATH" ]; \
then  \
  echo "Stemcell file not found!";   \
else \
  echo "Stemcell file not found!";  \
  exit 1; \
fi; \
	mv $TILE_FILE_PATH %s/; \
	mv $SC_FILE_PATH %s/; \
	ls -l %s/ %s/') \
	% ( resource['name'],
		input_resource['name'],
		output_resource['name'],
		output_stemcell_resource['name'],
		output_resource['name'],
		output_stemcell_resource['name']
	 )

	task_config['run']['args'].append(task_run_command)
	copy_job['plan'][1] = {
	                       'task' : ('prepare-%s-bit-to-export') % (resource['name']),
	                       'config' : task_config
						  }

	blobstore_upload_pipeline['jobs'].append(copy_job)
	upload_individual_group_job.append(copy_job['name'])

	parallel_upload_job_plan_getter_aggregate.append( { 'get' : input_resource['name'] , 'params': input_glob_param } )
	parallel_upload_job_plan_copy_job_aggregate.append(copy_job['plan'][1])
	parallel_upload_job_plan_putter_aggregate.append({ 'put' : output_resource['name'] , 'params': { 'file' : final_file_path }  })
	parallel_upload_job_plan_stemcell_putter_aggregate.append({ 'put' : output_stemcell_resource['name'] , 'params': { 'file' : final_stemcell_file_path }  })

def handle_s3_resource(resource, blobstore_upload_pipeline, offline_pipeline):
	print 'Handling s3 resource'

	# If the source and destination are the same s3 buckets/access keys,
	# then just simply copy the resource into offline pipeline

	if resource['source']['endpoint'] == default_bucket_config['endpoint'] \
	  and resource['source']['bucket'] == default_bucket_config['bucket'] \
	  and resource['source']['access_key_id'] == \
	  default_bucket_config['access_key_id'] \
	  and resource['source']['secret_access_key'] == \
	  default_bucket_config['secret_access_key']:
	  	offline_resource = copy.copy(resource)
		offline_pipeline['resources'].append(offline_resource)
		return

	cloned_resources = clone_resource(resource, blobstore_upload_pipeline, offline_pipeline)
	input_resource = cloned_resources[0]
	output_resource = cloned_resources[1]
	offline_resource = cloned_resources[2]

	end_file = input_source.get('uri') if input_source.get('uri') is not None else input_source.get('url')
	end_file = input_source.get('filename') if end_file is None else end_file

	tag = input_source.get('branch') if input_source.get('branch') is not None else input_source.get('version')
	tag = '1.0' if tag is None else tag

	#print 'Resource is {}'.format(resource)
	#print 'End of file is : {}'.format(end_file)
	if end_file is None:
		print 'Unable to decide on end file'
		exit(-1)


	tokens = end_file.split('/')
	end_file = tokens[len(tokens) - 1]
	output_resource['source']['regexp'] = '%s/s3/%s-(.*)' % ( 'resources', end_file)
	final_file_path = output_resource['name'] + '/' + end_file + '-' + tag


	copy_job = { 'name' : ( 'copy_%s_to_blobstore' % (resource['name'])) }
	copy_job['plan'] = [
							{ 'get' : input_resource['name'] },
							{ 'task' : 'prepare-bit-to-export' },
	 					  	{'put' : output_resource['name'] , 'params': { 'file' : final_file_path } }
						]
	task_config = { 'platform': 'linux'}
	task_config['inputs'] = [ { 'name': input_resource['name'] } ]
	task_config['outputs'] = [ { 'name': output_resource['name'] } ]
	task_config['image_resource'] = { 'type': 'docker-image' }
	task_config['image_resource']['source'] = { 'repository': 'ubuntu'}
	task_config['run'] = { 'path' : '/bin/bash', 'args': [ '-exc' ] }
	task_run_command = (' \
	echo "Copying %s bits";\
	no_of_entries=$(ls %s/ | wc -l); \
	if [ $no_of_entries -ne 1 ]; then cd %s; tar cfz ../%s .; cd ..; else \
	mv %s/* %s; fi; \
	ls -l %s/') \
	% ( resource['name'],
		input_resource['name'],
		input_resource['name'],
		final_file_path,
		input_resource['name'],
		final_file_path,
		output_resource['name']
	 )

	task_config['run']['args'].append(task_run_command)
	copy_job['plan'][1] = {
	                       'task' : ('prepare-%s-bit-to-export') % (resource['name']),
	                       'config' : task_config
						  }

	blobstore_upload_pipeline['jobs'].append(copy_job)
	upload_individual_group_job.append(copy_job['name'])

	parallel_upload_job_plan_getter_aggregate.append({ 'get': input_resource['name'] })
	parallel_upload_job_plan_copy_job_aggregate.append(copy_job['plan'][1])
	parallel_upload_job_plan_putter_aggregate.append({ 'put' : output_resource['name'] , 'params': { 'file' : final_file_path }  })

def handle_git_resource(resource, blobstore_upload_pipeline, offline_pipeline):
	print 'Handling git resource'
	cloned_resources = clone_resource(resource, blobstore_upload_pipeline, offline_pipeline)
	input_resource = cloned_resources[0]
	output_resource = cloned_resources[1]
	offline_resource = cloned_resources[2]

	input_source = resource['source']
	end_file = input_source.get('uri') if input_source.get('uri') is not None else input_source.get('url')

	tag = input_source.get('branch') if input_source.get('branch') is not None else input_source.get('version')
	tag = '1.0' if tag is None else tag

	#print 'Resource is {}'.format(resource)
	#print 'End of file is : {}'.format(end_file)
	if end_file is None:
		print 'Unable to decide on end file'
		exit(-1)

	tokens = end_file.split('/')
	end_file = tokens[len(tokens) - 1]
	output_resource['source']['regexp'] = '%s/git/%s-(.*).tgz' % ( 'resources', resource['name'])
	final_file_path = output_resource['name'] + '/' + resource['name'] + '-' + tag + '.tgz'

	# end_file = resource['name']
	# output_resource['source']['regexp'] = '%s/%s/(.*)' % ( 'resources', resource['name'])
	# final_file_path = '%s/%s/%s' % ( output_resource['name'], resource['name'], end_file)


	copy_job = { 'name' : ( 'copy_%s_to_blobstore' % (resource['name'])) }
	copy_job['plan'] = [
							{ 'get' : input_resource['name'] },
							{ 'task' : 'prepare-bit-to-export' },
	 					  	{'put' : output_resource['name'] , 'params': { 'file' : final_file_path } }
						]

	task_files = locate_task_files(src_pipeline, resource)

	task_config = { 'platform': 'linux'}
	task_config['inputs'] = [ { 'name': input_resource['name'] } ]
	task_config['outputs'] = [ { 'name': output_resource['name'] } ]
	task_config['image_resource'] = { 'type': 'docker-image' }
	task_config['image_resource']['source'] = { 'repository': 'ubuntu'}


	task_config['run'] = { 'path' : '/bin/bash', 'args': [ '-exc' ] }
	task_run_command = ('echo "Copying %s bits";  cd %s; for task_file in %s; do docker_image=$(python handlers/task_handler.py read $task_file); docker_image_tgz="%s/${docker_image}.tgz" ;  python handlers/task_handler.py write $task_file %s $docker_image_tgz  ; done; tar cfz ../%s .; cd ..;  ls -l %s/') \
	% ( resource['name'],
		input_resource['name'],
		str(task_files),
		'resources/docker',
		str(default_bucket_config),
		final_file_path,
		output_resource['name']
	 )


	task_config['run']['args'].append(task_run_command)

	copy_job['plan'][1] = {
	                       'task' : ('prepare-%s-bit-to-export') % (resource['name']),
	                       'config' : task_config
						  }

	blobstore_upload_pipeline['jobs'].append(copy_job)
	upload_individual_group_job.append(copy_job['name'])

	parallel_upload_job_plan_getter_aggregate.append({ 'get': input_resource['name'] })
	parallel_upload_job_plan_copy_job_aggregate.append(copy_job['plan'][1])
	parallel_upload_job_plan_putter_aggregate.append({ 'put' : output_resource['name'] , 'params': { 'file' : final_file_path }  })


	found_task_handler = False
	for getter in parallel_upload_job_plan_getter_aggregate:
		if 'task_handler' == getter['get']:
			found_task_handler = True
			break

	if found_task_handler == False:
		parallel_upload_job_plan_getter_aggregate.append({ 'get': 'task_handler' })


def locate_task_files(src_pipeline, given_git_resource):
	task_files = []
	git_resource_name = given_git_resource['name']

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
								if entry['file'] not in task_files and \
								git_resource_name in entry['file']:
									task_files.append(entry['file'])

				elif str(plan_key) == 'task':
				 	print '^^^^ Found Task: {}'.format(plan[plan_key])
					print('^^^^ Matching task file: {}'.format(plan['file']))
					if plan['file'] not in task_files and \
					git_resource_name in plan['file']:
						task_files.append(plan['file'].replace(git_resource_name, '.'))

	print 'Complete task list: {}'.format(task_files)
	return task_files

def handle_default_resource(resource, blobstore_upload_pipeline, offline_pipeline):
	print 'Default handling of resource type: ' + resource['type']

	cloned_resources = clone_resource(resource, blobstore_upload_pipeline, offline_pipeline)
	input_resource = cloned_resources[0]
	output_resource = cloned_resources[1]
	offline_resource = cloned_resources[2]

	input_source = resource['source']
	end_file = input_source.get('uri') if input_source.get('uri') is not None else input_source.get('url')
	end_file = input_source.get('filename') if end_file is None else end_file

	tag = input_source.get('branch') if input_source.get('branch') is not None else input_source.get('version')
	tag = '1.0' if tag is None else tag

	#print 'Resource is {}'.format(resource)
	#print 'End of file is : {}'.format(end_file)
	if end_file is None:
		print 'Unable to decide on end file'
		exit(-1)


	tokens = end_file.split('/')
	end_file = tokens[len(tokens) - 1]
	output_resource['source']['regexp'] = '%s/default/%s-(.*)' % ( 'resources', end_file)
	final_file_path = output_resource['name'] + '/' + end_file + '-' + tag

	copy_job = { 'name' : ( 'copy_%s_to_blobstore' % (resource['name'])) }
	copy_job['plan'] = [
							{ 'get' : input_resource['name'] },
							{ 'task' : 'prepare-bit-to-export' },
	 					  	{'put' : output_resource['name'] , 'params': { 'file' : final_file_path } }
						]
	task_config = { 'platform': 'linux'}
	task_config['inputs'] = [ { 'name': input_resource['name'] } ]
	task_config['outputs'] = [ { 'name': output_resource['name'] } ]
	task_config['image_resource'] = { 'type': 'docker-image' }
	task_config['image_resource']['source'] = { 'repository': 'ubuntu'}
	task_config['run'] = { 'path' : '/bin/bash', 'args': [ '-exc' ] }
	task_run_command = (' \
	echo "Copying %s bits";\
	no_of_entries=$(ls %s/ | wc -l); \
	if [ $no_of_entries -ne 1 ]; then cd %s; tar cfz ../%s .; cd ..; else \
	mv %s/* %s; fi; \
	ls -l %s/') \
	% ( resource['name'],
		input_resource['name'],
		input_resource['name'],
		final_file_path,
		input_resource['name'],
		final_file_path,
		output_resource['name']
	 )

	task_config['run']['args'].append(task_run_command)
	copy_job['plan'][1] = {
	                       'task' : ('prepare-%s-bit-to-export') % (resource['name']),
	                       'config' : task_config
						  }

	blobstore_upload_pipeline['jobs'].append(copy_job)
	upload_individual_group_job.append(copy_job['name'])

	parallel_upload_job_plan_getter_aggregate.append({ 'get': input_resource['name'] })
	parallel_upload_job_plan_copy_job_aggregate.append(copy_job['plan'][1])
	parallel_upload_job_plan_putter_aggregate.append({ 'put' : output_resource['name'] , 'params': { 'file' : final_file_path }  })

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
