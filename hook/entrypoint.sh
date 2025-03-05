#!/bin/bash
. venv/bin/activate
ansible-playbook entrypoint.yml  -c local --tag "run"
echo "Running captain hook applications!"
python3 entrypoint.py