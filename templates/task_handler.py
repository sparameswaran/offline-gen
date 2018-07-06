import os
import json
import copy
import yaml, sys

docker_list = []

def main():
    # Read the task.yml
    DOCKER_IMAGE_PATH = 'resources/docker/'


    pipeline_repo_path = sys.argv[1]
    tasks_list_file = sys.argv[2]
    source_config_file = sys.argv[3]
    docker_list_file = './docker-list'

    tasks = read_config(tasks_list_file)
    offline_s3_resource = read_config(source_config_file)

    for task in tasks:
        handle(task, offline_s3_resource)


def handle(task_path, offline_s3_resource):

    tokens = task_path.split('/')
    last_index_of_path_sep = task_path.rfind('/')
    path_to_file= task_path[:last_index_of_path_sep+1]
    end_file = task_path[last_index_of_path_sep+1:]

    existing_task = read_config(task_path)
    docker_image_repo = existing_task['image_resource']['source']['repository']
    version = existing_task['image_resource']['source'].get('tag')

    if version is not None:
        docker_image_repo += '-' + version

    if docker_image_repo not in docker_list:
        docker_list.append(docker_image_repo)

    docker_resource_path = '%s/%s.tgz' % ( DOCKER_IMAGE_PATH, docker_image_repo)

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
    new_task_defn['image_resource']['source'] =  offline_s3_resource
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