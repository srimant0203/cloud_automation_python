#!/usr/bin/env bash
export FLASK_APP=app:create_app
export FLASK_DEBUG=1
flask run --port=8080
