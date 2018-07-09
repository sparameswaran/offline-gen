import os
import json
import copy
import yaml, sys

docker_list = []
DOCKER_IMAGE_PATH = 'resources/docker'

def main():
    pipeline_repo_path = sys.argv[1]
    tasks_list_arr    = sys.argv[2]
    # tasks_list_file = sys.argv[2]
    source_config_file = sys.argv[3]
    docker_images_file = sys.argv[4]

    # if os.path.isfile(tasks_list_file):
    #     tasks = read_config(tasks_list_file)['tasks']
    # else:
    #     tasks = yaml.safe_load(tasks_list_file)

    #tasks = tasks_list_arr
    if tasks_list_arr is None or tasks_list_arr == '' or tasks_list_arr == '[]' :
        docker_images = { 'docker_images' : [] }
        write_config(docker_images, docker_images_file )
        return

    #print 'Offline S3 resource: {}'.format(offline_s3_resource)    if os.path.isfile(source_config_file):
        offline_s3_resource = read_config(source_config_file)['s3_blobstore']
    else:
        offline_s3_resource = yaml.safe_load(source_config_file)


    for task in tasks_list_arr: # split(','):
        handle(task, offline_s3_resource)

    print 'Docker List: {}'.format(docker_list)
    docker_images = { 'docker_images' : docker_list }
    write_config(docker_images, docker_images_file )

def handle(task_path, offline_s3_resource):

    tokens = task_path.split('/')
    last_index_of_path_sep = task_path.rfind('/')
    path_to_file= task_path[:last_index_of_path_sep+1]
    end_file = task_path[last_index_of_path_sep+1:]

    print 'Handling Task: {}'.format(task_path)
    existing_task = read_config(task_path)
    docker_image_name = existing_task['image_resource']['source']['repository']
    version = existing_task['image_resource']['source'].get('tag')

    if version is None:
        version = 'latest'

    docker_image_repo = docker_image_name + '-' + version

    docker_resource_path = '%s/%s-(.*).tgz' % ( DOCKER_IMAGE_PATH, docker_image_name)
    realized_docker_resource_path = '%s/%s-docker.tgz' % ( DOCKER_IMAGE_PATH, docker_image_repo)

    new_docker_entry = { 'name' : docker_image_repo, 'source': existing_task['image_resource']['source'] , 'image_path' : realized_docker_resource_path }
    if new_docker_entry not in docker_list:
        docker_list.append( new_docker_entry)

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

    write_config(new_task_defn, ('%s/offline_%s') % (path_to_file, end_file) )

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
