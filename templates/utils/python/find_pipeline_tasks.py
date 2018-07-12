import yaml
import os, sys
import copy
import requests
from pprint import *


src_pipeline = None
git_resources = {}
git_task_list = {}
docker_image_for_git_task_list = {}
full_docker_ref = []
docker_image_analysis_map = None

def main():
	pipeline_repo_path = sys.argv[1]
	analysis_output_file     = sys.argv[2]
	analyze_pipeline(pipeline_repo_path, analysis_output_file)

def analyze_pipeline_for_docker_images(pipeline_repo_path, target_pipeline, analysis_output_file):
	global docker_image_analysis_map, git_task_list

	if target_pipeline is None:
		target_pipeline = read_config(pipeline_repo_path)

	task_files = identify_all_task_files(target_pipeline)

	#write_config( { 'pipeline_tasks': task_files }, task_list_path)
	identify_associated_docker_image_for_task(git_task_list)

	print '\nFinal Docker dependency list'
	pprint(full_docker_ref)
	print '\nDependency graph of Github Repos, tasks and docker images references\n'
	pprint(docker_image_for_git_task_list)

	docker_image_analysis_map = { 'docker_list': full_docker_ref, 'pipeline_task_docker_references':  docker_image_for_git_task_list }
	write_config( docker_image_analysis_map, analysis_output_file)

	return docker_image_analysis_map

	# Sample outputs
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



def identify_all_task_files(target_pipeline):
	task_files = []
	for resource in target_pipeline['resources']:
		if resource['type'] == 'git':
			print 'Resource: {}'.format(resource)
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
				#print '#### Plan key: {}'.format(plan_key)
				if str(plan_key) == 'aggregate':
					#print 'Aggregate: {}'.format(plan[plan_key])
					aggregate = plan[plan_key]
					for entry in aggregate:
						# print 'Entry within aggregate: {}'.format(entry)
						# print 'Entry keys within aggregate: {}'.format(entry.keys)
						for nested_entry_key in entry:
							if nested_entry_key == 'task':
								#print '### nested_task_within_aggregate: {}'.format(entry['task'])
								#print('### Matching task entry: {}'.format(entry))
								task_file = entry.get('file')
								if task_file is not None:
									git_resource_id = task_file.split('/')[0]

								job_tasks.append( { 'task': entry.get('task'), 'file': task_file, 'git_resource' : git_resource_id } )

								if 	task_file is not None and task_file not in task_files:
									task_files.append(task_file)
									git_task_list[git_resource_id].append({ 'task': entry.get('task'), 'file': task_file } )

				elif str(plan_key) == 'task':
					#print '^^^^ Found Task: {}'.format(plan[plan_key])
					#print('^^^^ Matching task file: {}'.format(plan['file']))
					task_file = plan.get('file')
					if task_file is not None:
						git_resource_id = task_file.split('/')[0]

					job_tasks.append( { 'task': plan[plan_key], 'file': task_file, 'git_resource' : git_resource_id  } )
					if task_file is not None and task_file not in task_files:
						task_files.append(task_file)
						git_task_list[git_resource_id].append({ 'task': plan.get('task'), 'file': task_file })
					elif task_file is None:
						#print 'Plan is : {}'.format(plan)
						image_source = plan['config']['image_resource']
						#print 'Plan image resource is : {}'.format(plan['config']['image_resource'])
						if image_source is not None and 'docker' in image_source['type']:
							docker_repo = image_source['source']
							docker_image_task_entry['task_defns'].append( { plan.get('task') : { 'image': docker_repo } } )
							if docker_repo not in full_docker_ref:
								full_docker_ref.append(docker_repo)
							if docker_repo not in docker_image_task_entry['docker_references']:
								docker_image_task_entry['docker_references'].append(docker_repo)
							print 'Added image source: {}'.format(image_source['source'])
							print 'Top level docker_image_task_entry: {}'.format(docker_image_task_entry)

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
		git_repo_path = git_repo_path.replace('git@raw.githubusercontent.com:', 'https://raw.githubusercontent.com/')
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
			#print 'Task Path: ' + task_path
			#print 'Full path: ' + git_repo_path + task_path
			task_defn = load_github_resource(git_repo_path + task_path)
			#print 'Loaded Task Defn: {}'.format(task_defn)
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



def write_config(content, destination):
	try:
		with open(destination, 'w') as output_file:
			yaml.dump(content, output_file, Dumper = NoAliasDumper)

	except IOError as e:
		print('Error : {}'.format(e))
		print >> sys.stderr, 'Problem with writing out a yaml file.'
		sys.exit(1)

class NoAliasDumper(yaml.Dumper):
    def ignore_aliases(self, data):
        return True

if __name__ == '__main__':
	main()
