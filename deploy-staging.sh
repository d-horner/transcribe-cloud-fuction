#!/usr/bin/env bash

# Check if deployment variables exist
if [ -f .env.staging ]; then
  # shellcheck disable=SC1091
  source .env.staging
  else
    echo ".env.staging file was not found. The deployment script requires project variables to be defined."
    echo "Create .env.staging in the project root with the following variables: "
    echo ""
    echo "GCP_PROJECT=<your gcp project>"
    echo "GCP_REGION=<gcp region to deploy function to>"
    echo "GCP_FUNCTION_NAME=<name of gcp function>"
    exit 1
fi

# Check if in virtual env
if [ "$VIRTUAL_ENV" != "" ];
  then
    echo "You must exit the virtual env before deploying."
    echo ""
    echo "gcloud uses the hosts python (2.7) installation and is unsuitable for deployment."
    exit 1
fi

# Generate requirements.txt file
echo "Generating requirements.txt..."

# Check if a virtualenv exists and remove it for a clean installation
if [ -d ".venv" ]; then
  rm -rf .venv
fi

# Configure poetry to install virtualenv in project
poetry config virtualenvs.in-project true

# Install without the dev requirements for formatting/testing/coverage etc.
poetry install --no-interaction --no-dev --no-root
poetry export --no-interaction --without-hashes --format requirements.txt --output requirements.txt

# Check existence of file with environment variables
ENV_YAML_FILE=".env.yaml"
if [ ! -f "$ENV_YAML_FILE" ]; then
  echo "Missing $ENV_YAML_FILE file - please create one from template before trying again"
  exit 1
fi

# Upload source code to GCP
echo "Deploying to ${GCP_PROJECT} GCP... ${GCP_REGION}"
gcloud functions deploy \
  "${FUNCTION_NAME}" \
  --project "${GCP_PROJECT}" \
  --region "${GCP_REGION}" \
  --entry-point=transcribe \
  --runtime=python39 \
  --memory=256MB \
  --timeout=30s \
  --env-vars-file=$ENV_YAML_FILE \
  --allow-unauthenticated \
  --trigger-http
