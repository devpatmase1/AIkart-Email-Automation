#!/bin/bash
# =========================================================
# AIkart LangGraph Email Automation - AWS EC2 Setup Script
# =========================================================

echo "🚀 Starting AWS EC2 Auto-Setup for LangGraph Email Automation..."

# 1. Update system packages
echo "📦 Updating system packages..."
sudo apt-get update -y && sudo apt-get upgrade -y

# 2. Install Docker & Docker Compose
echo "🐳 Installing Docker & Docker Compose..."
sudo apt-get install -y docker.io docker-compose git curl

# 3. Enable & Start Docker
sudo systemctl enable docker
sudo systemctl start docker
sudo usermod -aG docker ubuntu

# 4. Check .env file
if [ ! -f .env ]; then
    echo "⚠️ .env file not found! Creating default .env file..."
    cat <<EOF > .env
GOOGLE_API_KEY=your_gemini_api_key_here
GROQ_API_KEY=your_groq_api_key_here
MY_EMAIL=your_email@domain.com
EMAIL_PASSWORD=your_app_password_or_resend_key
RESEND_API_KEY=re_your_resend_api_key_here
PORT=9000
EOF
    echo "✏️ Please edit .env file using: nano .env"
fi

# 5. Build and Launch Docker Container
echo "🚀 Building and starting Docker container on Port 9000..."
sudo docker-compose up -d --build

echo "========================================================="
echo "✅ Deployment Successful!"
echo "🌐 App is running at: http://$(curl -s ifconfig.me):9000"
echo "========================================================="
