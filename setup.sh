#!/bin/bash

set -e
echo "Starting setup.sh..."

apt-get update && apt-get install -y texlive-latex-base latexmk
echo "Installed latexmk."

mkdir -p ~/.streamlit/
echo "\
[server]\n\
headless = true\n\
port = $PORT\n\
enableCORS = false\n\
\n\
" > ~/.streamlit/config.toml

echo "setup.sh completed successfully"
