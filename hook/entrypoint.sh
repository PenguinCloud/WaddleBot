#!/bin/bash
ansible-playbook entrypoint.yml  -c local --tag "run"
echo "Sleeping awaiting action!"
python3 entrypoint.py