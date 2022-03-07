#!/usr/bin/env python
import os
import ffmpeg
import json
import pytest
import re
import requests
from google.cloud import speech
from main import (
    app,
    CloudFunctionSettings,
    load_settings_from_yaml,
    send_email,
    decode_audio,
    get_audio_length,
    get_transcript,
    allowed_file,
    get_phone_number,
)
from functions_framework import create_app
from unittest.mock import patch


def test_load_settings_from_yaml():
    settings = load_settings_from_yaml(".env.yaml")
    assert settings.ACCESS_CONTROL_ORIGIN == "*"  # nosec
    assert type(settings) == CloudFunctionSettings  # nosec


def test_decode_audio__success():
    audio = decode_audio(os.path.join("tests/test_audio.mp3"))
    assert type(audio) is bytes  # nosec


def test_decode_audio__failure():
    with pytest.raises(SystemExit) as pytest_wrapped_e:
        decode_audio("no_file.mp3")
    assert pytest.raises(ffmpeg._run.Error)  # nosec
    assert pytest_wrapped_e.type == SystemExit  # nosec
    assert pytest_wrapped_e.value.code == 1  # nosec


def test_get_audio_length():
    assert type(get_audio_length(os.path.join("tests/test_audio.mp3"))) == str  # nosec


def test_get_audio_length__failure():
    with pytest.raises(ValueError) as pytest_wrapped_e:
        get_audio_length("no_file.mp3")
    assert pytest.raises(ValueError)  # nosec
    assert pytest_wrapped_e.type == ValueError  # nosec


def test_get_transcript__audio():
    transcript = get_transcript(decode_audio(os.path.join("tests/test_audio.mp3")))
    assert (
        transcript
        == "🤖 Transcript: to listen to the message please hold or to save it just hang up  hi"
    )  # nosec


def test_get_transcript__no_audio():
    transcript = get_transcript(decode_audio(os.path.join("tests/test_no_audio.wav")))
    assert transcript == "🤖 No speech detected"  # nosec


def test_allowed_file__success():
    file = allowed_file("/path/to/file.wav")
    assert file  # nosec


def test_allowed_file__failure():
    file = allowed_file("/path/to/file.pdf")
    assert not file  # nosec


def test_get_phone_number__success():
    phone_number = get_phone_number(
        "Voice Message Attached from 07712345678 - name unavailable"
    )
    assert phone_number == "07712345678"  # nosec


def test_get_phone_number__failure():
    phone_number = get_phone_number(
        "Voice Message Attached from 077123456 - name unavailable"
    )
    assert phone_number == "Phone number not found."  # nosec


phone_regex = re.compile(r"(?:0|\+?44)(?:\d\s?){9,10}")


@pytest.mark.parametrize(
    "test_subject", ["Voice Message Attached from 07712345678 - name unavailable"]
)
def test_phone_number_regex(test_subject):
    assert phone_regex.findall(test_subject) is not None  # nosec


def test_get_route__failure__method_not_allowed():
    load_settings_from_yaml(".env.yaml")
    client = app.test_client()
    response = client.get("/")
    assert response.status_code == 500  # nosec


def test_put_route__failure__method_not_allowed():
    load_settings_from_yaml(".env.yaml")
    client = app.test_client()
    response = client.put("/")
    assert response.status_code == 405  # nosec


def test_head_route__failure__method_not_allowed():
    load_settings_from_yaml(".env.yaml")
    client = app.test_client()
    response = client.head("/")
    assert response.status_code == 500  # nosec


def test_options_route__success():
    load_settings_from_yaml(".env.yaml")
    client = app.test_client()
    response = client.options("/")
    assert response.status_code == 200  # nosec


def test_route__method_defined():
    load_settings_from_yaml(".env.yaml")
    adapter = app.url_map.bind("")
    assert adapter.match("/", method="POST")  # nosec


@pytest.fixture(scope="module")
def test_client():
    """ Test client """
    return create_app("transcribe", "main.py", "http").test_client()


def test_get_route__success(test_client):
    settings = load_settings_from_yaml(".env.yaml")
    response = test_client.get("/")
    assert response.status_code == 200  # nosec


def test_head_route__failure(test_client):
    settings = load_settings_from_yaml(".env.yaml")
    response = test_client.head("/")
    assert response.status_code == 400  # nosec


def test_post_route__failure__missing_token(test_client):
    response = test_client.post("/", data={})
    assert response.status_code == 302  # nosec


def test_post_route__failure__missing_file(test_client):
    settings = load_settings_from_yaml(".env.yaml")
    response = test_client.post("/", data={"token": "", "file": None})
    assert response.status_code == 302  # nosec


def test_post_route__failure__file_type_not_allowed(test_client):
    settings = load_settings_from_yaml(".env.yaml")
    test_file = open("tests/test_file.pdf", "rb")
    response = test_client.post("/", data={
        "token": settings.APPS_SCRIPT_TOKEN,
        "file": test_file,
    })
    test_file.close()
    assert response.status_code == 302  # nosec


def test_post_route__success(test_client):
    settings = load_settings_from_yaml(os.path.join(".env.yaml"))
    with patch("main.transcribe") as mock_post:
        test_file = open("tests/test_audio.mp3", "rb")
        mock_post.return_value.status_code = 200    
        response = test_client.post("/", data={
            "token": "",
            "file": test_file,
            "subject": "test",
            "from": "d.horner@edwardsgrounds.co.uk",
            "group": "test-branch@edwardsgrounds.co.uk",
        })
        test_file.close()
        assert response.status_code == 200  # nosec


def test_send_email__success():
    with patch("main.send_email") as mock_post:    
        settings = load_settings_from_yaml(".env.yaml")
        mock_post.return_value == True
        response = send_email(
            email_subject="subject",
            email_body="body",
            email_to="test@email.com",
            email_cc="cc@email.com",
            api_key=settings.MAILGUN_API_KEY,
        )
        assert response  # nosec


def test_send_email__failure():
    with patch("main.send_email") as mock_post:    
        settings = load_settings_from_yaml(".env.yaml")
        mock_post.return_value.status_code == 400
        response = send_email(
            email_subject="subject",
            email_body="body",
            email_to="test@email.com",
            email_cc="",
            api_key="wrong",
        )
        assert not response  # nosec