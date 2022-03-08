#!/usr/bin/env python
import ffmpeg
import google.cloud.logging
import json
import logging
import os
import re
import requests
import subprocess
import sys
import yaml
from flask import Flask, Request, redirect, request
from google.cloud import speech
from google.cloud.logging_v2.handlers import CloudLoggingHandler
from pydantic import BaseSettings
from werkzeug.utils import secure_filename

app = Flask(__name__)
app.config["UPLOAD_FOLDER"] = "/tmp"


class CloudFunctionSettings(BaseSettings):
    # Enable debug output (logging, additional messages, etc)
    DEBUG: bool = False
    MAILGUN_API_KEY: str = ""
    MAILGUN_DOMAIN: str = "edwardsgrounds.co.uk"
    APPS_SCRIPT_TOKEN: str = ""
    SEND_FROM_EMAIL: str = "test@edwardsgrounds.co.uk"
    ACCESS_CONTROL_ORIGIN: str = "*"


def send_email(
    email_subject: str, email_body: str, email_to: str, email_cc: str, api_key: str
) -> bool:
    """Send email via MailGun API.

    Args:
        email_subject (str): Email subject
        email_body (str): Email body
        email_to (str): Mail to address
        email_cc (str): CC mail address
        api_key (str): Mailgun API Key
    Returns:
        bool
    """
    payload = {
        "from": settings.SEND_FROM_EMAIL,
        "to": [email_to],
        "cc": [email_cc],
        "subject": f"{email_subject}",
        "text": f"{email_body}",
    }
    response = requests.post(
        # Mailgun API uses EU URL, if non-eu domain change to https://api.mailgun.net/v3/<DOMAIN>/messages
        f"https://api.eu.mailgun.net/v3/{settings.MAILGUN_DOMAIN}/messages",
        auth=("api", api_key),
        data=payload,
    )
    if response.status_code == 200:
        logging.info("Sent email to %s: [%s]", email_to, email_subject)
        return True
    logging.error("Error sending email to %s: [%s]", email_to, email_subject)
    return False


def decode_audio(in_filename: str, **input_kwargs) -> bytes:
    """Decodes input audiofile."""
    try:
        out, _ = (
            ffmpeg.input(in_filename, **input_kwargs)
            .output("-", format="s16le", acodec="pcm_s16le", ac=1, ar="16k")
            .overwrite_output()
            .run(capture_stdout=True, capture_stderr=True)
        )
    except ffmpeg.Error as e:
        print(e.stderr, file=sys.stderr)
        sys.exit(1)
    return out


def get_audio_length(input_audio: bytes) -> str:
    result = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "default=noprint_wrappers=1:nokey=1",
            input_audio,
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )
    return str(float(result.stdout))


def get_transcript(audio_data: bytes) -> str:
    """Transcribes input audio file, returns transcript."""
    client = speech.SpeechClient()
    audio = speech.RecognitionAudio(content=audio_data)
    config = speech.RecognitionConfig(
        encoding=speech.RecognitionConfig.AudioEncoding.LINEAR16,
        sample_rate_hertz=16000,
        language_code="en-GB",
        use_enhanced=True,
        enable_automatic_punctuation=True,
        model="phone_call",
    )
    response = client.recognize(config=config, audio=audio)
    transcript = ["🤖 Transcript:"]
    for _, result in enumerate(response.results):
        alternative = result.alternatives[0]
        transcript.append(f"{alternative.transcript}")
    res = " ".join(transcript)
    if len(res) < 15:
        res = "🤖 No speech detected"
    return str(res)


def get_phone_number(subject: str) -> str:
    phone_regex = re.compile(r"(?:0|\+?44)(?:\d\s?){9,10}")
    # find all occurences of phone number
    res = phone_regex.findall(subject)
    # return first occurence and strip white space
    if len(res) >= 1:
        return str(res[0]).strip()
    return "Phone number not found."


def allowed_file(filename: str) -> bool:
    return "." in filename and filename.rsplit(".", 1)[1].lower() in [
        "wav",
        "mp3",
        "m4a",
        "flac",
        "mp4",
        "wma",
        "aac",
    ]


# Load environment variables
def load_settings_from_environment() -> CloudFunctionSettings:
    return CloudFunctionSettings()


def load_settings_from_yaml(yaml_path: str) -> CloudFunctionSettings:
    with open(yaml_path, "rb") as yaml_file:
        yaml_env = yaml.safe_load(yaml_file)
        return CloudFunctionSettings(**yaml_env)


# Flask
def serve_flask_endpoint(endpoint):  # pragma: no cover
    app = Flask(__name__)  # pylint ignore=C0103  redefined for local/cloud deployment.
    app.debug = settings.DEBUG
    app.route("/", methods=["GET", "POST"])(lambda: endpoint(request))
    app.run()


@app.route("/", methods=["GET", "POST"])
def transcribe(req: Request):  # pylint: disable=R0914
    """Webhook endpoint to handle facebook lead form  GET request.

    Args:
        req (Request): Flask request

    Returns:
        (flask.Response):
            success (str): success or error
            status (int): HTTP status code
            message (str): error handling
    """
    if req.method == "POST":
        # check for request token
        if request.form.get("token") != settings.APPS_SCRIPT_TOKEN:
            logging.error("No token received or is incorrect")
            return redirect(request.url)
        # check if the post request has the file part
        if "file" not in request.files:
            logging.error("No file part")
            return redirect(request.url)

        file = request.files["file"]
        if file and allowed_file(file.filename):
            # Remove the file if it exists
            if os.path.exists(os.path.join(app.config["UPLOAD_FOLDER"], file.filename)):
                os.remove(
                    os.path.join(app.config["UPLOAD_FOLDER"], file.filename)
                )  # pragma: no cover
            # Get the secure filename https://werkzeug.palletsprojects.com/en/1.0.x/utils/#werkzeug.utils.secure_filename
            filename = secure_filename(file.filename)
            file.save(os.path.join(app.config["UPLOAD_FOLDER"], filename))

            audio_data = decode_audio(
                os.path.join(app.config["UPLOAD_FOLDER"], filename)
            )
            try:
                audio_length = str(
                    get_audio_length(
                        os.path.join(app.config["UPLOAD_FOLDER"], filename)
                    )
                )
            except Exception as e:  # pragma: no cover
                audio_length = "audio length not detected"
                logging.error("Error detecting audio length: %s", e)

            phone_number = get_phone_number(str(request.form.get("subject")))
            transcription = get_transcript(audio_data)
            formatted_message = f"Voicemail from: {phone_number}\nLength: {audio_length}s\n{transcription}"

            try:
                subject = "Re: " + str(request.form.get("subject"))
                mail_from = str(request.form.get("from"))
                mail_group = str(request.form.get("group"))
                send_email(
                    email_subject=subject,
                    email_body=formatted_message,
                    email_to=mail_from,
                    email_cc=mail_group,
                    api_key=settings.MAILGUN_API_KEY,
                )
                return (
                    json.dumps({"success": True}),
                    200,
                    {
                        "ContentType": "application/json",
                        "Access-Control-Allow-Origin": settings.ACCESS_CONTROL_ORIGIN,
                    },
                )
            except Exception as e:  # pragma: no cover
                logging.error("Error: Email failed to send - %s", e)
                return (
                    json.dumps({"success": False, "message": "An error occured."}),
                    400,
                    {
                        "ContentType": "application/json",
                        "Access-Control-Allow-Origin": settings.ACCESS_CONTROL_ORIGIN,
                    },
                )
    if req.method == "GET":
        return (
            json.dumps({"success": True, "message": "Get success"}),
            200,
            {
                "ContentType": "application/json",
                "Access-Control-Allow-Origin": settings.ACCESS_CONTROL_ORIGIN,
            },
        )
    return (
        json.dumps({"success": False, "message": "An error occured."}),
        400,
        {
            "ContentType": "application/json",
            "Access-Control-Allow-Origin": settings.ACCESS_CONTROL_ORIGIN,
        },
    )


if __name__ == "__main__":  # pragma: no cover
    # Handle environment variables to configure logging, fail if errors
    if os.getenv("GOOGLE_APPLICATION_CREDENTIALS") and os.path.isfile(
        os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
    ):
        pass
    elif os.path.isfile(".gcloud-logging-credentials"):
        os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = str(
            os.path.dirname(os.path.abspath(".gcloud-logging-credentials"))
            + "/.gcloud-logging-credentials"
        )
    else:
        sys.exit(1)
    settings = load_settings_from_yaml(".env.yaml")
    serve_flask_endpoint(transcribe)
else:
    # Instantiate logging for development and cloud.
    client = google.cloud.logging.Client()
    handler = CloudLoggingHandler(client)
    logging.getLogger().setLevel(logging.INFO)
    google.cloud.logging.handlers.setup_logging(handler)
    settings = load_settings_from_environment()
