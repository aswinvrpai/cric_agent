#!/bin/bash
# ============================================================
# EC2 Bootstrap Script
# Run this ONCE on a fresh Amazon Linux 2023 EC2 instance
# Usage: chmod +x ec2_setup.sh && sudo ./ec2_setup.sh
# ============================================================

set -e

echo "==> [1/6] Updating system packages..."
yum update -y

echo "==> [2/6] Installing Docker..."
yum install -y docker
systemctl enable docker
systemctl start docker
usermod -aG docker ec2-user          # allow ec2-user to run docker without sudo

echo "==> [3/6] Installing Docker Compose..."
curl -SL https://github.com/docker/compose/releases/latest/download/docker-compose-linux-x86_64 \
     -o /usr/local/bin/docker-compose
chmod +x /usr/local/bin/docker-compose

echo "==> [4/6] Installing AWS CLI v2..."
curl "https://awscli.amazonaws.com/awscli-exe-linux-x86_64.zip" -o "awscliv2.zip"
unzip -q awscliv2.zip
./aws/install
rm -rf awscliv2.zip aws/

echo "==> [5/6] Creating app directory..."
mkdir -p /home/ec2-user/cric-agent/nginx
mkdir -p /home/ec2-user/cric-agent/logs
chown -R ec2-user:ec2-user /home/ec2-user/cric-agent

echo "==> [6/6] Done!"
echo ""
echo "  Next steps:"
echo "  1. Copy docker-compose.yml and nginx/nginx.conf to /home/ec2-user/cric-agent/"
echo "  2. Create /home/ec2-user/cric-agent/.env with your GROQ_API_KEY"
echo "  3. Attach an IAM role with AmazonEC2ContainerRegistryReadOnly to this EC2"
echo "  4. Re-login: exit and SSH back in (to pick up docker group)"
