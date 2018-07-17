# Offline-gen

Offline Generator for Concourse pipelines

Creates two separate pipelines that handle:
* Upload of all the contents referred by a concourse pipeline to S3 Blobstore
  * Github repositories
  * Docker images (as tarballs)
  * Files or nested folders (as tarballs for multiple files)
  * Pivnet Tiles (with stemcells)
  * Non-Pivnet Tiles (like Ops Mgr Ova file)
* Offline Pipeline that uses only offlined version of resources saved in S3 Blobstore

Usage:

* Basic usage: ```python offline-generator.py <target-pipeline-repo-path> input.yml```

  Expect the target-pipeline repo to be locally present and generate full upload and offlined pipeline versions

  See sample `sample_input.yml` template under `templates` folder for input file structure (specifies the s3 configs, pipeline file path, other general configs)

* Git repo first pass: ```python offline-generator.py -git <target-pipeline-repo-path> input.yml```

  Would generate a new pipeline that would only represent git repos to be analyzed for next step.
* Analysis pass:  ```python offline-generator.py -analyze <target-pipeline-repo-path> input.yml```
  Would generate a full report of the various docker images used by the tasks within a given pipeline across various jobs
  Sample report:
  ```
  docker_list:
- {repository: nsxedgegen/nsx-t-gen-worker}
pipeline_task_docker_references:
  nsx-t-gen-pipeline:
    docker_references:
    - {repository: nsxedgegen/nsx-t-gen-worker}
    git_path: https://raw.githubusercontent.com/sparameswaran/nsx-t-gen/master/
    task_defns:
    - install-nsx-t:
        file: tasks/install-nsx-t/task.yml
        image: {repository: nsxedgegen/nsx-t-gen-worker}
        inputs:
        - {name: nsx-t-gen-pipeline}
        - {name: nsx-mgr-ova}
        ....
        - {name: ovftool}
        outputs: null
        script: nsx-t-gen-pipeline/tasks/install-nsx-t/task.sh
     .....
  nsxt-ansible:
    docker_references: []
    git_path: https://raw.githubusercontent.com/sparameswaran/nsxt-ansible/master/
    task_defns: []
  target-pipeline:
    docker_references: []
    git_path: pipeline
    job_tasks_references:
    - install-nsx-t:
      - {file: nsx-t-gen-pipeline/tasks/install-nsx-t/task.yml, git_resource: nsx-t-gen-pipeline,
        task: install-nsx-t}
    task_defns: []
  ```
