import os
import json
import copy
import yaml, sys

def main():
    # Read the task.yml
    DOCKER_IMAGE_PATH = 'resources/docker/'

    operation_type = sys.argv[1]

    existing_task = read_config(sys.argv[2])
    tokens = sys.argv[2].split('/')
    last_index_of_path_sep = sys.argv[2].rfind('/')
    path_to_file= sys.argv[2][:last_index_of_path_sep+1]
    end_file = sys.argv[2][last_index_of_path_sep+1:]

    docker_image_repo = existing_task['image_resource']['source']['repository']

    if operation_type == 'read' or operation_type == 'r':
        print(docker_image_repo)
        exit(0)

    bucket_config = read_config(sys.argv[3])['s3_blobstore']
    docker_resource_path = sys.argv[4]

    task_script = existing_task['run']['path']

    new_task_defn = { 'platform' : 'linux'}
    new_task_defn['inputs'] = existing_task['inputs']
    new_task_defn['run'] = existing_task['run']
    if existing_task.get('outputs') is not None:
        new_task_defn['outputs'] = existing_task.get('outputs')

    new_task_defn['params'] = {}
    for param in existing_task['params']:
        new_task_defn['params'][param] = ''
    new_task_defn['image_resource'] = {}
    new_task_defn['image_resource']['type'] = 's3'
    new_task_defn['image_resource']['source'] =  bucket_config
    new_task_defn['image_resource']['source']['regexp'] = docker_resource_path
    new_task_defn['image_resource']['params'] = {'unpack' : True}

    write_config(new_task_defn, ('%s/mod_%s') % (path_to_file, end_file) )

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
