# Transcribe Voicemail to Email Google Cloud Function

An open source function for transcribing incoming audio files to email.

The function was written with to receive voicemail via email (Google Groups for Business) and transcribe the voicemail content, then reply to the thread with the transcript to reduce time taken to handle out of hours staff communication.



## Features

- Google Cloud Function hosted Flask HTTP endpoint
- Google Cloud Speech to Text recognition
- Google Groups for Business thread continuation with transcription
- Emails sent via Mailgun API
- FFmpeg audio conversion
- Audio length inspection via FFprobe
- Logging via google.cloud.logging
- Secret based authentication between trigger and endpoint



## Installation

Install python 3.7+ on your machine ([GCP cloud function uses 3.7+](https://cloud.google.com/functions/docs/concepts/python-runtime))

Install [gcloud commandline tools](https://cloud.google.com/sdk/docs/install)

Use pip to install poetry: `pip install poetry` (or `pip3 install poetry` if your default python installation is the legacy 2.7 version).

Create virtualenv using poetry [https://python-poetry.org/docs/basic-usage/](https://python-poetry.org/docs/basic-usage/)
~~~~bash
poetry install
~~~~

Activate the virtual environment
~~~~bash
poetry shell
~~~~



## Configuration

Configuration for the flask application differs depending on which environment the application is being run in. Ultimately, GCP Cloud Functions are configured via environment variables following the [12-factor app configuration best practice princples](https://12factor.net/config). As such, a yaml template is provided with sensitive information inserted during CI/CD or by the developer.

The configuration files are ommited from git commits in `.gitignore` to prevent sensitive information such as API keys being accidentally leaked.

Configuration files:

- `.env.yaml` - configures flask variables. `MAILGUN_API_KEY`, `MAILGUN_DOMAIN`, `SEND_FROM_EMAIL` and `APPS_SCRIPT_TOKEN` must be configured for all deployments.
- `.env.production` - configures `deploy-production.sh` production GCP Cloud Function deployment. Set your project, region and function name.
- `.env.staging` - configures `deploy-staging.sh` development GCP Cloud Function deployment. Set your project, region and function name.



## Quickstart

Copy `.env.yaml.template` to `.env.yaml` and configure the environment variables for the HTTP endpoint.
~~~~bash
cp .env.yaml.template .env.yaml
~~~~

Run the server
~~~~bash
poetry run ./main.py
~~~~

Send an audio file via HTTP POST request to the endpoint using python requests (substitute variables)
~~~~python
import requests
url = "http://localhost:5000/"
file = "/path/to/file.mp3"
data = {
    "token": "APPS-SCRIPT-TOKEN",
    "subject": "Voice Message Attached from 07712345678 - name unavailable",
    "from": "my@email-address.com",
    "group": "the@google-group.com",
}
with open(file, 'rb') as f:
    r = requests.post(url,data=data,files={'file': f})
    print(r.status_code)
    print(r)
~~~~



## Deployment

Scripts (`deploy-production.sh` and `deploy-staging.sh`) are provided to deploy functions to Google Cloud.

The scripts check if a virtual enviroment exists within the project structure, if found, delete it to ensure that developer packages aren't exported into the cloud based deployments and encourage only necessary packages are installed for both maintainability and security.

Poetry is configured to install the virtual environment inside the project directory within the `.venv` directory.

1. Edit the project, region and name variables in the respective `.env.production` or `.env.staging`.

Production:
~~~~bash
cp .env.template .env.production
~~~~

Development:
~~~~bash
cp .env.template .env.staging
~~~~

2. Copy `.env.yaml.template` to `.env.yaml` and configure the environment variables for the HTTP endpoint.
~~~~bash
cp .env.yaml.template .env.yaml
~~~~


### Google Cloud Logging

Google Cloud Logging requires authentication with the IAM [Logs Writer role](https://cloud.google.com/logging/docs/access-control#permissions_and_roles). Most GCP environments provide this role by default. Development environments are likely to leverage your user account permissions via gcloud's commandline OAuth API.

Development, CI/CD builds, testing and deployment in ephemeral environments (e.g. GitLab's CI/CD, CircliCI, Travis, Gitpod etc.) must make available a [JSON encoded service account](https://cloud.google.com/iam/docs/creating-managing-service-account-keys) with the Logs Writer Role in order to authenticate via the Cloud Logging library in the following 2 ways:

- Configuration via the environment variable `GOOGLE_APPLICATION_CREDENTIALS` to the absolute path of the JSON encoded Service Account key file.
- Piping or copying the JSON encoded Service Account key file to `.gcloud-logging-credentials` file in the project root (the location of the repository or execution of `main.py`)


### GitLab CI/CD

A CI/CD pipeline for testing and deployment is provided in `.gitlab-ci.yml`

[Enable Cloud Services](https://cloud.google.com/endpoints/docs/openapi/enable-api) for Cloud Build, Logging, App Engine and Cloud Functions
~~~~bash
gcloud services enable cloudbuild.googleapis.com
gcloud services enable logging.googleapis.com
gcloud services enable appengine.googleapis.com
gcloud services enable cloudfunctions.googleapis.com
gcloud services enable speech.googleapis.com
~~~~


Create Google Cloud Service Accounts for the project(s) you wish to deploy to via the pipeline.

Create service account policy bindings with roles `Cloud Functions Service Agent` and `Cloud Build Service Agent`


#### CI/CD Example Configuration

Get the project name and number
~~~~bash
$ gcloud projects list
PROJECT_ID                      NAME                            PROJECT_NUMBER
my-dev                          my-dev                          168491158423
~~~~

Fill in the variables
~~~~bash
# Modify the variables
SA_NAME="gitlab-function-deploy-staging"
PROJECT_ID="my-dev"
PROJECT_NUMBER="168491158423"
KEY_FILE="${PROJECT_ID}-${PROJECT_NUMBER}_${SA_NAME}.json"
# Set project
gcloud config set project $PROJECT_ID
# Create SA
gcloud iam service-accounts create $SA_NAME \
    --description="Gitlab CI/CD Service Account for Cloud Function Deployment and Logging" \
    --display-name="${SA_NAME//-/ }"
# Get SA key
gcloud iam service-accounts keys create $KEY_FILE \
    --iam-account=$SA_NAME@$PROJECT_ID.iam.gserviceaccount.com
~~~~

Add roles to the service account
~~~~bash
# Add SA roles for Cloud Build
gcloud iam service-accounts add-iam-policy-binding $PROJECT_ID@appspot.gserviceaccount.com \
 --member serviceAccount:$PROJECT_NUMBER@cloudbuild.gserviceaccount.com \
 --role=roles/iam.serviceAccountUser
# Add SA roles for Cloud Functions
gcloud projects add-iam-policy-binding $PROJECT_ID \
 --member serviceAccount:$PROJECT_NUMBER@cloudbuild.gserviceaccount.com \
 --role roles/cloudfunctions.developer
# Add SA roles for App Engine
gcloud iam service-accounts add-iam-policy-binding $PROJECT_ID@appspot.gserviceaccount.com \
 --member=serviceAccount:$SA_NAME@$PROJECT_ID.iam.gserviceaccount.com \
 --role=roles/iam.serviceAccountUser
# Add SA roles for Cloud Functions Developer
gcloud projects add-iam-policy-binding $PROJECT_ID \
 --member=serviceAccount:$SA_NAME@$PROJECT_ID.iam.gserviceaccount.com \
 --role=roles/cloudfunctions.developer
# Add SA roles for speech-to-text
gcloud projects add-iam-policy-binding $PROJECT_ID \
 --member=serviceAccount:$SA_NAME@$PROJECT_ID.iam.gserviceaccount.com \
 --role=roles/speech.client
# Add SA roles for Log Writer
gcloud projects add-iam-policy-binding $PROJECT_ID \
 --member=serviceAccount:$SA_NAME@$PROJECT_ID.iam.gserviceaccount.com \
 --role=roles/logging.logWriter
~~~~


The following project variables must be configured for the pipeline to succeed:

- `GCP_STAGING_PROJECT` - GCP staging project name
- `GCP_STAGING_REGION` - GCP staging function deployment region
- `GCP_STAGING_FUNCTION_NAME` - Function name for staging deployment
- `GCP_PRODUCTION_PROJECT` - GCP production project name
- `GCP_PRODUCTION_REGION` - GCP production function deployment region
- `GCP_PRODUCTION_FUNCTION_NAME` - Function name for production deployment
- `GCLOUD_SERVICE_ACCOUNT_STAGING_FUNCTION` - Service account email (e.g: `gitlab-staging-function-deploy@your-staging-project.iam.gserviceaccount.com`)
- `GCLOUD_SERVICE_KEY_STAGING_FUNCTION` - Service account key (json encoded 'file' type variable)
- `GCLOUD_SERVICE_ACCOUNT_PRODUCTION_FUNCTION` - Service account email (e.g: `gitlab-production-function-deploy@your-production-project.iam.gserviceaccount.com`)
- `GCLOUD_SERVICE_KEY_PRODUCTION_FUNCTION` - Service account key (json encoded 'file' type variable)
- `MAILGUN_DOMAIN` - Mailgun domain to send emails from
- `MAILGUN_API_KEY` - [Mailgun API key](https://help.mailgun.com/hc/en-us/articles/203380100-Where-Can-I-Find-My-API-Key-and-SMTP-Credentials-)
- `SEND_FROM_EMAIL` - Email to send transcripts from
- `APPS_SCRIPT_TOKEN` - App Script Token configured in your trigger (see below)


Remove or alter `HOST: "https://allied.sh/api/v4/projects/"` to `https://gitlab.com/api/v4/projects/` or your own Gitlab deployment.


## Limitations

This function was written with the purpose of using a time based Google App Script trigger to query unread emails with mp3/wav attachments, extract *UK* phone numbers (other countries and formats would require modification of the regex in `get_phone_number()`), get the transcript and email the content within the same Google Group thread.

Audio files are transcribed synchronously via the Speech-To-Text API, thus they are limited to 60 seconds of audio. Audio is trimmed for files exceeding 60 seconds due to the intended use case. Refer to [https://cloud.google.com/speech-to-text/docs/async-recognize](https://cloud.google.com/speech-to-text/docs/async-recognize) for transcription of longer files.

Mailgun is hardcoded within the script, although any transactional ESP could be substituted.


## Google Apps Script Example

Below is an example trigger configured to run every minute to filter unread emails from our VoIP provider containing audio attachments, extract the phone number, subject and sender info (emails are CC'd to the Google Group, this would need to be modified for your use case). Transcribed emails are labelled 'TranscribedVoicemail' and marked as read.

Configure:
- `transcribeUrl`: with the Google Cloud Function endpoint after deployment.
- `labelName`: with the name you with transcribed voicemails to be labelled with.
- Modify the query string to filter emails according to your requirements
  ~~~~javascript
  query =  'from:our@voip-provider.co.uk is:unread ' +query; //'category:forums is:unread ' + query; //in:inbox..or.. has:userLabels ..or.. has:nouserlabels ' + query;
  ~~~~

~~~~javascript
// GLOBALS

//URL of transcribe-cloud-function http service, e.g: 'https://europe-west2-myproject-234235.cloudfunctions.net/transcribe-voicemail'
var transcribeUrl = 'https://your-project-.cloudfunctions.net/transcribe-voicemail';

// Name of the label which will be applied after processing the mail message
var labelName = 'TranscribedVoicemail';

//Array of file extension which you would like to extract
var fileTypesToExtract = [ 'wav', 'mp3', 'm4a', 'flac', 'mp4', 'wma', 'aac' ];

function TranscribeVoicemail(){
  //build query to search emails
  var query = '';
  //filename:jpg OR filename:tif OR filename:gif OR fileName:png OR filename:bmp OR filename:svg'; //'after:'+formattedDate+
  for(var i in fileTypesToExtract){
    query += (query === '' ?('filename:'+fileTypesToExtract[i]) : (' OR filename:'+fileTypesToExtract[i]));
  }
  query =  'from:our@voip-provider.co.uk is:unread ' +query; //'category:forums is:unread ' + query; //in:inbox..or.. has:userLabels ..or.. has:nouserlabels ' + query;
  var threads = GmailApp.search(query);
  var label = getGmailLabel_(labelName);
  for(var i in threads){
    var mesgs = threads[i].getMessages();
    for(var j in mesgs){
      //Check if message is from voicemail
      if(mesgs[j].isUnread()){
        //get attachments
        var attachments = mesgs[j].getAttachments();
        for(var k in attachments){
          var attachment = attachments[k];
          //check if file is of the defined type
          var isDefinedType = checkIfDefinedType_(attachment);
          if(!isDefinedType) continue;
          var attachmentBlob = attachment.copyBlob();
          var emailSubject = mesgs[j].getSubject();
          var emailGroup = mesgs[j].getCc();
          var emailFrom = mesgs[j].getFrom();
          var payload = {
            'token': 'APPS-SCRIPT-TOKEN',
            'subject': emailSubject,
            'from': emailFrom,
            'group': emailGroup,
            'file': attachmentBlob
          };
          var params = {
              'method': 'POST',
              'payload': payload
          };
          var response = UrlFetchApp.fetch(transcribeUrl, params);
        }
      }
      //mark message as read
      mesgs[j].markRead()
    }
    //add TranscribedVoicemail label
    threads[i].addLabel(label);
  }
}

//getDate n days back for use with query filter containing 'after:'+formattedDate+
// n must be an integer
function getDateNDaysBack_(n){
  n = parseInt(n);
  var date = new Date();
  date.setDate(date.getDate() - n);
  return Utilities.formatDate(date, Session.getScriptTimeZone(), 'yyyy/MM/dd');
}

function getGmailLabel_(name){
  var label = GmailApp.getUserLabelByName(name);
  if(!label){
    label = GmailApp.createLabel(name);
  }
  return label;
}

//this function will check for filextension type.
// and return boolean
function checkIfDefinedType_(attachment){
  var fileName = attachment.getName();
  var temp = fileName.split('.');
  var fileExtension = temp[temp.length-1].toLowerCase();
  if(fileTypesToExtract.indexOf(fileExtension) !== -1) return true;
  else return false;
}
~~~~


## Contributing as a developer


### Development environment

These are the typical commands needed to get started:

~~~~bash
poetry install  # Create virtualenv using https://python-poetry.org/docs/basic-usage/
poetry shell  # Activate the virtual environment
pre-commit install  # Install pre-commit hook framework
cp .env.yaml.template .env.yaml  # Copy the .env.yaml.template and fill in variable information
poetry run ./main.py  # Launch server
~~~~


### Linting

This project makes use of both flake8 and pylint to ensure code quality and identify erroneous or dangerous code.

~~~~bash
poetry run flake8  # Invokes flake8 - will pass without any errors.
poetry run pylint *.py  # Invokes pylint - will report code quality score.
~~~~


### Testing

Testing comprises of `pytest`, `coverage` and `bandit`.

~~~~bash
peotry run pytest -cov  # Makes use of the pytest-cov plugin to execute tests and report code coverage.
poetry run bandit -v -r . -c "pyproject.toml"  # Bandit searches for common security issues in python code (https://bandit.readthedocs.io/en/latest/)
~~~~

Gitlab's CI/CD pipeline makes use of bandit via Static Application Security Testing ([SAST](https://docs.gitlab.com/ee/user/application_security/sast/))


### Committing

Please note that `pre-commit` will permit to fix a lot of linting errors
automatically. An example workflow is included below:

~~~~bash
git checkout -b <branch name>  # Checkout a new branch name
git add .  # Add the files to the staging area
poetry run pre-commit run  # Run the pre-commit hooks, linting and testing. If this step fails, run `git add .` to add the linted files for each step.
git commit -m "<commit message>"  # Commit changes to repository
git push --set upstream origin <branch name>  # Push your development branch and create a merge request.
~~~~
