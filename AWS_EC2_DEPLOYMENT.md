# 🚀 AWS EC2 Deployment Guide

Follow this step-by-step guide to deploy **LangGraph Email Automation** on an AWS EC2 Instance.

---

## Step 1: Launch EC2 Instance on AWS Console

1. Open [AWS EC2 Console](https://console.aws.amazon.com/ec2/).
2. Click **Launch Instance**.
3. **Name**: `langgraph-email-automation`
4. **OS (AMI)**: **Ubuntu 22.04 LTS** or **24.04 LTS** (64-bit x86).
5. **Instance Type**: `t2.micro` or `t3.micro` (AWS Free Tier eligible).
6. **Key Pair**: Select existing key pair or create a new one (e.g. `my-ec2-key.pem`).
7. **Network Settings (Security Group)**:
   - Allow SSH (`Port 22`) from Any/Your IP.
   - Allow HTTP (`Port 80`).
   - Allow HTTPS (`Port 443`).
   - Add Custom TCP Rule: **Port `9000`** -> `0.0.0.0/0` (Custom TCP Rule for App API/UI).
8. Click **Launch Instance**.

---

## Step 2: Connect to EC2 via SSH

Open Terminal or Command Prompt on your computer:

```bash
chmod 400 my-ec2-key.pem
ssh -i "my-ec2-key.pem" ubuntu@<YOUR_EC2_PUBLIC_IP>
```

---

## Step 3: Clone Code & Run Auto-Setup Script

Once logged in to EC2 terminal:

```bash
# 1. Clone your GitHub Repository (or upload files)
git clone https://github.com/<your-username>/langgraph-email-automation.git
cd langgraph-email-automation

# 2. Make setup script executable and run it
chmod +x ec2-setup.sh
./ec2-setup.sh
```

---

## Step 4: Configure API Keys in `.env`

Edit `.env` file on EC2:

```bash
nano .env
```

Paste your API Keys:
```env
GOOGLE_API_KEY=AIzaSy...
RESEND_API_KEY=re_123456789...
MY_EMAIL=your_email@domain.com
EMAIL_PASSWORD=re_123456789...
```

Save and exit (`Ctrl + O`, `Enter`, `Ctrl + X`).

Restart container after editing `.env`:
```bash
sudo docker-compose restart
```

---

## Step 5: Access Your Live Web App

Open your browser and navigate to:
`http://<YOUR_EC2_PUBLIC_IP>:9000`

---

## 🛠️ Useful Management Commands on EC2

* **View live app logs:**
  ```bash
  sudo docker-compose logs -f
  ```
* **Restart App:**
  ```bash
  sudo docker-compose restart
  ```
* **Stop App:**
  ```bash
  sudo docker-compose down
  ```
