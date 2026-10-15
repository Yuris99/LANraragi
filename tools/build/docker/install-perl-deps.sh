#!/bin/sh

set -e

# Run it with increased jobs to improve performance
export MAKEFLAGS="-j$(nproc)"

# Redirect perl dependencies to the home directory
eval "$(perl -Mlocal::lib)"

# Install cpanm
# Fail on HTTP errors instead of executing a partial/error response.
bootstrap="$(mktemp)"
trap 'rm -f "$bootstrap"' EXIT
curl --fail --show-error --silent --location https://cpanmin.us -o "$bootstrap"
perl "$bootstrap" App::cpanminus

cd ./tools

# Manually download modules
cpanm --notest ETHER/Net-IDN-Encode-2.501-TRIAL.tar.gz

# Install the LRR dependencies proper
cpanm --notest --installdeps . --configure-timeout 300

cd ..

perl ./tools/install.pl install-back
