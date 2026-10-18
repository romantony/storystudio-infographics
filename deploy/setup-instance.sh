#!/bin/bash
# First-boot setup of the EC2 instance (Ubuntu 24.04 arm64). Used as user data; safe to run again as root.
# The instance profile must allow: SSM core, pull from the infogen ECR repository, read parameters under /infogen/,
# ec2:DescribeTags, and ec2:StopInstances on itself.
set -euxo pipefail
export DEBIAN_FRONTEND=noninteractive
apt-get update
apt-get install -y docker.io docker-compose-v2 jq git
snap install aws-cli --classic || snap refresh aws-cli
ln -sf /snap/bin/aws /usr/local/bin/aws
mkdir -p /opt/infogen /data/infogen/data /data/infogen/home
chown -R 1000:1000 /data/infogen
rm -rf /opt/infogen/src
git clone --depth 1 https://github.com/romantony/storystudio-infographics.git /opt/infogen/src
cd /opt/infogen/src/deploy
install -m 644 docker-compose.yml /opt/infogen/
install -m 755 fetch-env.sh deadman.sh /opt/infogen/
install -m 644 infogen.service infogen-deadman.service infogen-deadman.timer /etc/systemd/system/
systemctl daemon-reload
systemctl enable --now docker
systemctl enable infogen.service infogen-deadman.timer
systemctl start infogen-deadman.timer
systemctl restart infogen.service
