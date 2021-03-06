#!/bin/bash

# Concourse target
export CONCOURSE_TARGET=concourse-test

# MODIFY based on run/target pipeline
export OFFLINE_GEN_PIPELINE_NAME=kickoff-offline-gen-test-pipeline

# Use the provided kickoff-offline-gen-pipeline.yml template
export OFFLINE_GEN_PIPELINE=kickoff-offline-gen-pipeline.yml


# All offline-gen parameters go here (like s3 blobstore details, run name,
#                                 target pipeline github repo, pipeline file)
export OFFLINE_GEN_INPUT_PARAM_FILE=offline-gen-input-params.yml

# Sample input in the offline_gen yaml params file (refer to sample_input.yml):
# repo: workspace/nsx-t-gen                    # Path to the target pipeline repo
# pipeline: pipelines/test-nsx-t-install.yml   # Relative path to the target pipeline file from within the target pipeline repo
#
# # Default github path to pull down raw content
# github_raw_content: raw.githubusercontent.com # Github url to retreive raw content for any associated repos referred by the pipeline
#
# # Target pipeline details - EDIT ME
# target_pipeline_name: install-nsx-t
# target_pipeline_uri: https://github.com/sparameswaran/nsx-t-gen
# target_pipeline_branch: master
# pipeline: pipelines/nsx-t-install.yml   # Relative path to the target pipeline file from within the target pipeline repo
# repo: workspace/nsx-t-gen                    # Path to the target pipeline repo if its local
#
# # Run Id - EDIT ME
# run_name: install-product-run-1                         # Unique identifier to distinguish the run
#
# # Concourse Login/auth
# concourse_team: main
# concourse_password: concourse
# concourse_username: concourse
#
# S3 blobstore details
# This would be used by the offline-gen to save its artifacts
# Add any aditional parameter required like region or ssl or v2 signing
# and update also in the kickoff-offline-gen-pipeline.yml
# Following is <param-name>: &alias <param-value>
# EDIT the param-value section
# offline_gen_s3_endpoint: &my_s3_endpoint http://10.85.24.5:9000/                   # EDIT ME
# offline_gen_s3_bucket: &my_s3_bucket offline-bucket                                # EDIT ME
# offline_gen_s3_access_key_id: &my_s3_access_key_id my_access_id                    # EDIT ME
# offline_gen_s3_secret_access_key: &my_s3_secret_access_key my_secret_access_key    # EDIT ME
#
# # Change parameters in final generated offline pipeline s3 source to be s3_blobstore_parameterized_tokens
# # for porting across S3 blobstore_source. This will allow replacement of actual s3 configs to parameterized list
# # Sample generated S3 source
# #source: {access_key_id: my_access_id, bucket: offline-bucket, endpoint: 'http://10.85.24.5:9000/',
# #    regexp: test1/resources/docker/czero-cflinuxfs2-latest-docker.(.*), secret_access_key: my_secret_access_key}
# # Modified to
# #source: {access_key_id: ((final_s3_access_key_id)), bucket: ((final_s3_bucket)), endpoint: ((final_s3_endpoint)),
# #  regexp: test1/resources/docker/czero-cflinuxfs2-latest-docker.(.*), secret_access_key: ((final_s3_secret_access_key))}
# #
# Setting following flag to true will make both blob-upload and offline pipeline would refer to s3 stubbed values described below
# # Set it to false and then the same s3 blobstore used by offline-gen would be used in all s3 source references
# parameterize_s3_bucket_params: "true"
# s3_blobstore_parameterized_tokens:
#  endpoint: final_s3_endpoint
#  bucket: final_s3_bucket
#  access_key_id: final_s3_access_key_id
#  secret_access_key: final_s3_secret_access_key
# # Add any additional parameter that needs to be overriden from generated s3 source
#
# # S3 blobstore details
# # This would be used by the offline-gen to save its artifacts
# # Add any aditional parameter required like region or ssl or v2 signing
# # and update also in the kickoff-offline-gen-pipeline.yml
# # Following is <param-name>: &alias <param-value>
# # EDIT the param-value section
# offline_gen_s3_endpoint: &my_s3_endpoint http://10.85.24.5:9000/                   # EDIT ME
# offline_gen_s3_bucket: &my_s3_bucket offline-bucket                                # EDIT ME
# offline_gen_s3_access_key_id: &my_s3_access_key_id my_access_id                    # EDIT ME
# offline_gen_s3_secret_access_key: &my_s3_secret_access_key my_secret_access_key    # EDIT ME
#
# # S3 blobstore for actual generated pipelines
# s3_blobstore:
#   endpoint: *my_s3_endpoint
#   bucket: *my_s3_bucket
#   access_key_id: *my_s3_access_key_id
#   secret_access_key: *my_s3_secret_access_key
#   # Add any additional parameter
#   #disable_ssl: true
#   #skip_ssl_verification: true
#   #use_v2_signing: true

# Any additional target pipeline parameters go here (like github branches)
export TARGET_PIPELINE_INPUT_PARAM_FILE=target-pipeline-params.yml
# Refer to sample_pipeline_paras.yml
# Sample target-pipeline-params.yml -> actual values to be used for blobstore upload and offline pipeline (only for iaas/github branches/product versions)
# s3_endpoint: http://10.85.24.5:9000/
# s3_bucket: offline-bucket
# s3_access_key_id: my_access_id
# s3_secret_access_key: my_secret_access_key
# iaas: vsphere

fly -t $CONCOURSE_TARGET set-pipeline \
    -p $OFFLINE_GEN_PIPELINE_NAME \
    -c $OFFLINE_GEN_PIPELINE \
    -y "offline_gen_yaml_input_params=$(cat $OFFLINE_GEN_INPUT_PARAM_FILE)" \
    -y "pipeline_yaml_input_params=$(cat $TARGET_PIPELINE_INPUT_PARAM_FILE)" \
    -l offline-gen-input-params.yml \
    -l target-pipeline-params.yml
