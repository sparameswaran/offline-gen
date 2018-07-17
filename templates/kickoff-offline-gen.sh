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

# Any additional target pipeline parameters go here (like github branches)
export TARGET_PIPELINE_INPUT_PARAM_FILE=target-pipeline-params.yml

fly -t $CONCOURSE_TARGET set-pipeline \
    -p $OFFLINE_GEN_PIPELINE_NAME \
    -c $OFFLINE_GEN_PIPELINE \
    -y "offline_gen_yaml_input_params=$(cat $OFFLINE_GEN_INPUT_PARAM_FILE)" \
    -y "pipeline_yaml_input_params=$(cat $TARGET_PIPELINE_INPUT_PARAM_FILE)" \
    -l input.yml \
    -l extra-params.yml


# Sample input in the offline_gen yaml params file:
# repo: workspace/nsx-t-gen                    # Path to the target pipeline repo
# pipeline: pipelines/test-nsx-t-install.yml   # Relative path to the target pipeline file from within the target pipeline repo
# params: sample-params.yml                    # Absolute or relative path to the params file
# run_name: test-run-1                              # Unique identifier to distinguish the run
#
# # Concourse Login/auth
# concourse_main_password: concourse
# concourse_main_username: concourse
#
# # Default github path to pull down raw content
# github_raw_content: raw.githubusercontent.com # Github url to retreive raw content for any associated repos referred by the pipeline
#
# # S3 blobstore details
# # Can be overridden by yet another params file when during fly -l <params-file>
# s3_endpoint: &my_s3_endpoint http://10.85.24.5:9000/                   # EDIT ME
# s3_bucket: &my_s3_bucket offline-bucket                                # EDIT ME
# s3_access_key_id: &my_s3_access_key_id my_access_id                    # EDIT ME
# s3_secret_access_key: &my_s3_secret_access_key my_secret_access_key    # EDIT ME
#
# # S3 blobstore - would use aliased values
# s3_blobstore:
#   endpoint: *my_s3_endpoint #http://127.0.0.1:9000/
#   bucket: *my_s3_bucket #offline-bucket
#   access_key_id: *my_s3_access_key_id #my_access_id
#   secret_access_key: *my_s3_secret_access_key #my_secret_access_key
#   #disable_ssl:
#   #skip_ssl_verification:
#   #use_v2_signing:
