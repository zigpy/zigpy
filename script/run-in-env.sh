#!/usr/bin/env sh
set -eu

# Activate virtualenv if present, then run the specified command

if [ -n "${VIRTUAL_ENV-}" ] && [ -f "${VIRTUAL_ENV}/bin/activate" ]; then
  . "${VIRTUAL_ENV}/bin/activate"
else
  my_path=$(git rev-parse --show-toplevel)

  for venv in .venv venv; do
    if [ -f "${my_path}/${venv}/bin/activate" ]; then
      . "${my_path}/${venv}/bin/activate"
      break
    fi
  done
fi

exec "$@"
