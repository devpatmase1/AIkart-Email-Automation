import uvicorn
from fastapi import FastAPI, HTTPException, UploadFile, File, Form
from fastapi.responses import HTMLResponse, JSONResponse, FileResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from src.graph import Workflow
from src.tools.GmailTools import GmailToolsClass
from dotenv import load_dotenv
import time
import os
import io
import re
import pandas as pd
import socket

load_dotenv()

def connect_smtp_ipv4(host: str, port: int, timeout: float = 15.0):
    """
    Connects to an SMTP server forcing IPv4 address resolution to prevent 
    'Errno 101 Network is unreachable' errors on cloud hosts like Render/AWS.
    """
    host = host.strip()
    target_host = host
    
    try:
        ipv4_addrs = [res[4][0] for res in socket.getaddrinfo(host, port, socket.AF_INET, socket.SOCK_STREAM)]
        if ipv4_addrs:
            target_host = ipv4_addrs[0]
    except Exception as dns_err:
        print(f"[SMTP IPv4 DNS] Warning: Could not resolve IPv4 for {host}: {dns_err}")

    try:
        if port == 465:
            server = smtplib.SMTP_SSL(target_host, port, timeout=timeout)
            server.server_hostname = host
        else:
            server = smtplib.SMTP(target_host, port, timeout=timeout)
            server.starttls()
        return server
    except Exception as primary_err:
        if target_host != host:
            if port == 465:
                server = smtplib.SMTP_SSL(host, port, timeout=timeout)
            else:
                server = smtplib.SMTP(host, port, timeout=timeout)
                server.starttls()
            return server
        raise primary_err

app = FastAPI(
    title="AI Email Broadcast & Multi-Sender Outreach Platform",
    version="2.5",
    description="Multi-Sender Dynamic Email Automation Platform",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

workflow_instance = None

def get_workflow():
    global workflow_instance
    if workflow_instance is None:
        workflow_instance = Workflow()
    return workflow_instance

class DynamicBulkEmailRequest(BaseModel):
    sender_email: str = Field(..., example="your_email@gmail.com")
    sender_password: str = Field(..., example="abcd efgh ijkl mnop")
    smtp_host: str = Field(default="smtp.gmail.com")
    smtp_port: int = Field(default=587)
    recipients: list[str]
    subject: str
    body: str

class DynamicInboxRequest(BaseModel):
    sender_email: str = Field(..., example="your_email@gmail.com")
    sender_password: str = Field(..., example="abcd efgh ijkl mnop")
    imap_host: str = Field(default="imap.gmail.com")
    smtp_host: str = Field(default="smtp.gmail.com")

@app.post("/api/parse-excel")
async def parse_excel_file(file: UploadFile = File(...)):
    """Extracts email addresses and metadata from uploaded Excel (.xlsx/.xls) or CSV files."""
    try:
        contents = await file.read()
        filename = file.filename.lower()

        if filename.endswith(".csv"):
            df = pd.read_csv(io.BytesIO(contents))
        elif filename.endswith(".xlsx") or filename.endswith(".xls"):
            df = pd.read_excel(io.BytesIO(contents))
        else:
            raise HTTPException(status_code=400, detail="Unsupported file format. Please upload .xlsx, .xls, or .csv file.")

        email_regex = r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}'
        
        extracted = []
        email_set = set()

        for idx, row in df.iterrows():
            row_str = " ".join(row.astype(str).values)
            matches = re.findall(email_regex, row_str)
            for email_addr in matches:
                email_addr = email_addr.lower().strip()
                if email_addr not in email_set:
                    email_set.add(email_addr)
                    name = str(row.iloc[0]) if len(row) > 0 else "Valued Contact"
                    extracted.append({
                        "row": idx + 1,
                        "email": email_addr,
                        "name": name
                    })

        return {
            "status": "success",
            "filename": file.filename,
            "total_emails": len(extracted),
            "emails": extracted
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/send-bulk-dynamic")
async def send_bulk_dynamic(req: DynamicBulkEmailRequest):
    """Sends bulk emails from ANY custom email address and App Password provided by the user in the UI."""
    if not req.sender_email or not req.sender_password:
        raise HTTPException(status_code=400, detail="Sender Email Address and App Password are required!")

    results = []
    sent_count = 0
    failed_count = 0

    try:
        server = connect_smtp_ipv4(req.smtp_host, req.smtp_port)
        server.login(req.sender_email.strip(), req.sender_password.strip())

        for recipient in req.recipients:
            try:
                msg = MIMEMultipart()
                msg["From"] = req.sender_email.strip()
                msg["To"] = recipient.strip()
                msg["Subject"] = req.subject
                msg.attach(MIMEText(req.body, "plain"))

                server.send_message(msg)
                sent_count += 1
                results.append({"email": recipient, "status": "sent", "error": None})
                time.sleep(0.3)
            except smtplib.SMTPAuthenticationError as auth_err:
                failed_count += 1
                results.append({"email": recipient, "status": "failed", "error": f"Authentication failed: {str(auth_err)}"})
            except Exception as mail_err:
                failed_count += 1
                results.append({"email": recipient, "status": "failed", "error": str(mail_err)})

        server.quit()

        return {
            "status": "completed",
            "sender": req.sender_email,
            "total_recipients": len(req.recipients),
            "sent_count": sent_count,
            "failed_count": failed_count,
            "results": results
        }
    except smtplib.SMTPAuthenticationError as auth_err:
        raise HTTPException(
            status_code=400,
            detail=f"Google Authentication Error (535 Bad Credentials) for '{req.sender_email}'.\n\nTo fix this:\n1. Enable 2-Step Verification on '{req.sender_email}'.\n2. Generate a 16-character App Password at https://myaccount.google.com/apppasswords.\n3. Enter the 16-character App Password in the Password field instead of your main Google password."
        )
    except Exception as e:
        if "535" in str(e) or "BadCredentials" in str(e) or "Username and Password not accepted" in str(e):
            raise HTTPException(
                status_code=400,
                detail=f"Google Authentication Error (535 Bad Credentials) for '{req.sender_email}'.\n\nTo fix this:\n1. Enable 2-Step Verification on '{req.sender_email}'.\n2. Generate a 16-character App Password at https://myaccount.google.com/apppasswords.\n3. Enter the 16-character App Password in the Password field instead of your main Google password."
            )
        raise HTTPException(status_code=500, detail=f"SMTP Login/Connection Error for '{req.sender_email}': {str(e)}")

@app.post("/api/process-inbox-dynamic")
async def process_inbox_dynamic(req: DynamicInboxRequest):
    """Checks inbox and replies dynamically using the user-configured email and app password."""
    try:
        # Temporarily set environment for GmailTools
        os.environ["MY_EMAIL"] = req.sender_email.strip()
        os.environ["EMAIL_PASSWORD"] = req.sender_password.strip()
        os.environ["IMAP_SERVER"] = req.imap_host.strip()
        os.environ["SMTP_SERVER"] = req.smtp_host.strip()

        start_time = time.time()
        initial_state = {
            "emails": [],
            "current_email": {
              "id": "", "threadId": "", "messageId": "", "references": "",
              "sender": "", "subject": "", "body": ""
            },
            "email_category": "", "generated_email": "", "rag_queries": [],
            "retrieved_documents": "", "writer_messages": [], "sendable": False, "trials": 0
        }

        wf = get_workflow()
        final_state = wf.app.invoke(initial_state, {'recursion_limit': 100})
        total_time = round(time.time() - start_time, 2)

        return {
            "status": "success",
            "sender": req.sender_email,
            "elapsed_seconds": total_time,
            "category": final_state.get("email_category", "product_enquiry"),
            "generated_email": final_state.get("generated_email", "Processed inbox successfully!")
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/logo-full.png")
async def get_logo_full():
    return FileResponse("logo-full.png")

@app.get("/logo-icon.png")
async def get_logo_icon():
    return FileResponse("logo-icon.png")

@app.get("/", response_class=HTMLResponse)
async def get_dashboard():
    html_content = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>aiKart — Multi-Sender AI Email Outreach & Automation</title>
    <link rel="icon" type="image/png" href="/logo-icon.png">
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;500;600;700;800&family=Outfit:wght@500;600;700;800&family=JetBrains+Mono:wght@400;500;600&display=swap" rel="stylesheet">
    <style>
        :root {
            --bg-color: #f8fafc;
            --card-bg: rgba(255, 255, 255, 0.92);
            --card-border: rgba(226, 232, 240, 0.9);
            --primary: #2563eb;
            --primary-gradient: linear-gradient(135deg, #2563eb 0%, #4f46e5 100%);
            --primary-hover: linear-gradient(135deg, #1d4ed8 0%, #4338ca 100%);
            --accent-blue: #0284c7;
            --accent-green: #16a34a;
            --accent-red: #e11d48;
            --text-primary: #0f172a;
            --text-secondary: #475569;
            --text-muted: #64748b;
            --input-bg: #ffffff;
            --input-border: #cbd5e1;
            --input-focus: #2563eb;
        }

        * { box-sizing: border-box; margin: 0; padding: 0; }

        body {
            font-family: 'Plus Jakarta Sans', -apple-system, BlinkMacSystemFont, sans-serif;
            background-color: var(--bg-color);
            background-image: 
                radial-gradient(circle at 10% 10%, rgba(37, 99, 235, 0.08) 0%, transparent 45%),
                radial-gradient(circle at 90% 20%, rgba(139, 92, 246, 0.08) 0%, transparent 45%),
                radial-gradient(circle at 50% 90%, rgba(14, 165, 233, 0.06) 0%, transparent 50%);
            background-attachment: fixed;
            color: var(--text-primary);
            min-height: 100vh;
            display: flex;
            justify-content: center;
            align-items: flex-start;
            padding: 2.5rem 1.5rem;
        }

        .container {
            width: 100%;
            max-width: 960px;
            display: flex;
            flex-direction: column;
            gap: 1.75rem;
        }

        /* Header */
        .header {
            text-align: center;
            display: flex;
            flex-direction: column;
            align-items: center;
            gap: 0.75rem;
            margin-bottom: 0.5rem;
        }

        .brand-logo-badge {
            display: inline-flex;
            align-items: center;
            justify-content: center;
            background: #ffffff;
            padding: 0.65rem 2.2rem;
            border-radius: 9999px;
            border: 1px solid var(--card-border);
            box-shadow: 0 4px 20px rgba(37, 99, 235, 0.1);
            transition: transform 0.3s cubic-bezier(0.4, 0, 0.2, 1), box-shadow 0.3s ease;
        }

        .brand-logo-badge:hover {
            transform: translateY(-2px) scale(1.02);
            box-shadow: 0 8px 30px rgba(37, 99, 235, 0.18);
        }

        .animated-gradient {
            background: linear-gradient(135deg, #1e40af 0%, #3b82f6 50%, #6366f1 100%);
            -webkit-background-clip: text;
            background-clip: text;
            -webkit-text-fill-color: transparent;
            font-family: 'Outfit', sans-serif;
            font-size: 2.6rem;
            font-weight: 800;
            letter-spacing: -0.02em;
        }

        .header p {
            color: var(--text-secondary);
            font-size: 1.05rem;
            font-weight: 500;
        }

        /* Cards */
        .glass-card, .sender-config-box {
            background: var(--card-bg);
            backdrop-filter: blur(20px) saturate(180%);
            -webkit-backdrop-filter: blur(20px) saturate(180%);
            border: 1px solid var(--card-border);
            border-radius: 24px;
            padding: 1.75rem;
            display: flex;
            flex-direction: column;
            gap: 1.4rem;
            box-shadow: 0 10px 30px -5px rgba(0, 0, 0, 0.04), 0 4px 12px -2px rgba(0, 0, 0, 0.02);
        }

        .sender-header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            padding-bottom: 0.5rem;
            border-bottom: 1px solid #f1f5f9;
        }

        .sender-title {
            color: var(--primary);
            font-weight: 700;
            font-size: 0.95rem;
            letter-spacing: 0.03em;
            display: flex;
            align-items: center;
            gap: 0.5rem;
        }

        .btn-clear {
            background: rgba(225, 29, 72, 0.08);
            border: 1px solid rgba(225, 29, 72, 0.2);
            color: #e11d48;
            padding: 0.4rem 0.9rem;
            border-radius: 9999px;
            font-size: 0.8rem;
            font-weight: 600;
            cursor: pointer;
            transition: all 0.2s ease;
        }

        .btn-clear:hover {
            background: #e11d48;
            color: #fff;
            transform: translateY(-1px);
        }

        .sender-row {
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 1.25rem;
        }

        @media (max-width: 640px) {
            .sender-row { grid-template-columns: 1fr; }
        }

        .sender-col, .form-group {
            display: flex;
            flex-direction: column;
            gap: 0.55rem;
        }

        label {
            font-size: 0.875rem;
            font-weight: 600;
            color: var(--text-secondary);
            letter-spacing: 0.01em;
        }

        input[type="email"], input[type="password"], input[type="text"], textarea {
            width: 100%;
            background: var(--input-bg);
            border: 1px solid var(--input-border);
            border-radius: 14px;
            padding: 0.8rem 1.1rem;
            color: var(--text-primary);
            font-family: inherit;
            font-size: 0.95rem;
            outline: none;
            transition: all 0.2s ease;
            box-shadow: inset 0 1px 2px rgba(0, 0, 0, 0.02);
        }

        input[type="email"]:focus, input[type="password"]:focus, input[type="text"]:focus, textarea:focus {
            border-color: var(--input-focus);
            box-shadow: 0 0 0 3.5px rgba(37, 99, 235, 0.15);
        }

        textarea {
            min-height: 130px;
            resize: vertical;
            line-height: 1.6;
        }

        /* File Upload */
        input[type="file"] {
            background: #f8fafc;
            border: 2px dashed #93c5fd;
            border-radius: 16px;
            padding: 1.25rem;
            color: var(--text-secondary);
            cursor: pointer;
            transition: all 0.2s ease;
        }

        input[type="file"]:hover {
            border-color: var(--primary);
            background: #eff6ff;
        }

        input[type="file"]::file-selector-button {
            background: var(--primary-gradient);
            border: none;
            color: white;
            padding: 0.55rem 1.25rem;
            border-radius: 10px;
            font-weight: 600;
            cursor: pointer;
            margin-right: 1rem;
            transition: all 0.2s ease;
            box-shadow: 0 2px 8px rgba(37, 99, 235, 0.25);
        }

        input[type="file"]::file-selector-button:hover {
            opacity: 0.95;
            transform: scale(1.02);
        }

        /* Tabs */
        .tabs {
            display: flex;
            background: #e2e8f0;
            border: 1px solid rgba(203, 213, 225, 0.8);
            padding: 0.4rem;
            border-radius: 18px;
            gap: 0.5rem;
        }

        .tab-btn {
            flex: 1;
            background: transparent;
            border: none;
            color: var(--text-secondary);
            padding: 0.85rem 1.25rem;
            font-family: inherit;
            font-size: 0.95rem;
            font-weight: 600;
            border-radius: 14px;
            cursor: pointer;
            transition: all 0.25s cubic-bezier(0.4, 0, 0.2, 1);
            display: flex;
            align-items: center;
            justify-content: center;
            gap: 0.5rem;
        }

        .tab-btn:hover {
            color: var(--text-primary);
            background: rgba(255, 255, 255, 0.5);
        }

        .tab-btn.active {
            background: #ffffff;
            color: var(--primary);
            box-shadow: 0 4px 15px rgba(0, 0, 0, 0.08);
        }

        /* Table */
        .email-table {
            width: 100%;
            border-collapse: separate;
            border-spacing: 0;
            font-size: 0.9rem;
        }

        .email-table th {
            background: #f1f5f9;
            color: var(--text-secondary);
            font-weight: 600;
            text-align: left;
            padding: 0.85rem 1rem;
            border-bottom: 1px solid #e2e8f0;
        }

        .email-table th:first-child { border-top-left-radius: 12px; }
        .email-table th:last-child { border-top-right-radius: 12px; }

        .email-table td {
            padding: 0.85rem 1rem;
            border-bottom: 1px solid #f1f5f9;
            color: var(--text-primary);
        }

        .email-table tr:hover td {
            background: #f8fafc;
        }

        /* Button */
        .btn-send {
            background: var(--primary-gradient);
            border: none;
            color: white;
            padding: 1.1rem 1.8rem;
            font-family: inherit;
            font-size: 1.05rem;
            font-weight: 700;
            border-radius: 16px;
            cursor: pointer;
            transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
            display: flex;
            align-items: center;
            justify-content: center;
            gap: 0.75rem;
            box-shadow: 0 6px 20px rgba(37, 99, 235, 0.3);
            margin-top: 0.5rem;
        }

        .btn-send:hover:not(:disabled) {
            transform: translateY(-2px);
            box-shadow: 0 10px 28px rgba(37, 99, 235, 0.45);
            background: var(--primary-hover);
        }

        .btn-send:disabled {
            opacity: 0.45;
            cursor: not-allowed;
            box-shadow: none;
            transform: none;
        }

        /* Spinner */
        .spinner {
            width: 22px;
            height: 22px;
            border: 3px solid rgba(255, 255, 255, 0.35);
            border-radius: 50%;
            border-top-color: white;
            animation: spin 0.8s linear infinite;
            display: none;
        }

        @keyframes spin {
            to { transform: rotate(360deg); }
        }

        /* Log Terminal Box */
        .log-box {
            background: #0f172a;
            border: 1px solid #1e293b;
            border-radius: 16px;
            padding: 1.25rem;
            font-family: 'JetBrains Mono', monospace;
            font-size: 0.85rem;
            color: #38bdf8;
            white-space: pre-wrap;
            max-height: 260px;
            overflow-y: auto;
            display: none;
            line-height: 1.6;
            box-shadow: inset 0 2px 10px rgba(0, 0, 0, 0.3);
        }

        /* Custom Scrollbar */
        ::-webkit-scrollbar { width: 8px; height: 8px; }
        ::-webkit-scrollbar-track { background: #f1f5f9; border-radius: 4px; }
        ::-webkit-scrollbar-thumb { background: #cbd5e1; border-radius: 4px; }
        ::-webkit-scrollbar-thumb:hover { background: #94a3b8; }
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <div class="brand-logo-badge">
                <img src="/logo-full.png" alt="aiKart" style="height: 38px; width: auto; display: block;" />
            </div>
            <h1><span class="animated-gradient">Multi-Sender AI Email Platform</span></h1>
            <p>Automate Bulk Campaigns & Inbox Workflows with AI Financial Agents</p>
        </div>

        <!-- DYNAMIC SENDER CONFIGURATION HEADER -->
        <div class="sender-config-box">
            <div class="sender-header">
                <div class="sender-title">⚡ SENDER ACCOUNT CREDENTIALS (Custom Email)</div>
                <button type="button" class="btn-clear" onclick="clearSenderFields()">🗑️ Clear Credentials</button>
            </div>
            <div class="sender-row">
                <div class="sender-col">
                    <label>Sender Email Address</label>
                    <input type="email" id="activeSenderEmail" value="" placeholder="your_email@domain.com" autocomplete="off">
                </div>
                <div class="sender-col">
                    <label>Sender App Password / Pass</label>
                    <input type="password" id="activeSenderPassword" value="" placeholder="16-character App Password" autocomplete="off">
                </div>
            </div>
        </div>

        <div class="tabs">
            <button class="tab-btn active" id="tabExcelBtn" onclick="switchTab('excel')">📊 Excel Bulk Campaign</button>
            <button class="tab-btn" id="tabInboxBtn" onclick="switchTab('inbox')">📬 Live Inbox Monitor</button>
        </div>

        <!-- TAB 1: EXCEL BULK CAMPAIGN -->
        <div class="glass-card" id="excelCard">
            <div class="form-group">
                <label>1. Upload Excel or CSV File (.xlsx, .xls, .csv)</label>
                <input type="file" id="excelFile" accept=".xlsx, .xls, .csv" onchange="uploadExcel()">
            </div>

            <div id="previewSection" style="display: none;">
                <label style="color: var(--accent-green); font-weight: 700;" id="extractedCountLabel">Extracted 0 Emails</label>
                <div style="max-height: 200px; overflow-y: auto; margin-top: 0.5rem; border-radius: 12px; border: 1px solid var(--card-border);">
                    <table class="email-table">
                        <thead>
                            <tr>
                                <th>#</th>
                                <th>Name / Info</th>
                                <th>Extracted Email Address</th>
                            </tr>
                        </thead>
                        <tbody id="emailTableBody"></tbody>
                    </table>
                </div>
            </div>

            <div class="form-group">
                <label>2. Email Subject Line</label>
                <input type="text" id="campaignSubject" value="Special Announcement & Agency Updates">
            </div>

            <div class="form-group">
                <label>3. Email Body (Sent to all extracted recipient addresses)</label>
                <textarea id="campaignBody">Dear Valued Partner,

I hope this email finds you well. I am reaching out from Agentia to share our latest service plans and agency updates.

Please feel free to reply directly to this email if you have any questions or would like to schedule a consultation!

Best regards,
The Agentia Team</textarea>
            </div>

            <button class="btn-send" id="sendBulkBtn" onclick="sendBulkCampaign()" disabled>
                <div class="spinner" id="bulkSpinner"></div>
                <span id="bulkBtnText">🚀 Upload Excel File First</span>
            </button>

            <div class="log-box" id="campaignLogBox"></div>
        </div>

        <!-- TAB 2: INBOX MONITOR -->
        <div class="glass-card" id="inboxCard" style="display: none;">
            <button class="btn-send" id="inboxBtn" onclick="processInbox()">
                <div class="spinner" id="inboxSpinner"></div>
                <span id="inboxBtnText">📬 Check & Process Configured Inbox</span>
            </button>

            <div style="display: flex; justify-content: space-between; align-items: center; background: #f8fafc; padding: 1.1rem 1.4rem; border-radius: 16px; border: 1px solid #e2e8f0;">
                <div>
                    <strong style="color: var(--text-primary); font-size: 0.98rem;">Auto-Poll Inbox (Every 60s)</strong>
                    <p style="font-size: 0.85rem; color: var(--text-muted); margin-top: 0.15rem;">Continuously read and reply to incoming customer emails</p>
                </div>
                <input type="checkbox" id="autoPoll" onchange="toggleAutoPoll(this)" style="width: 20px; height: 20px; cursor: pointer; accent-color: var(--primary);">
            </div>

            <div id="inboxReport" style="display: none; background: #ffffff; border: 1px solid #e2e8f0; padding: 1.25rem; border-radius: 16px; box-shadow: 0 4px 12px rgba(0, 0, 0, 0.03);">
                <h4 style="color: var(--accent-green); margin-bottom: 0.5rem; font-weight: 700;">Inbox Workflow Complete</h4>
                <div id="inboxOutput" style="white-space: pre-wrap; font-size: 0.95rem; line-height: 1.6; color: var(--text-primary);"></div>
            </div>
        </div>
    </div>

    <script>
        let extractedEmailsList = [];
        let pollInterval = null;

        function clearSenderFields() {
            document.getElementById('activeSenderEmail').value = '';
            document.getElementById('activeSenderPassword').value = '';
        }

        function switchTab(tab) {
            if (tab === 'excel') {
                document.getElementById('excelCard').style.display = 'flex';
                document.getElementById('inboxCard').style.display = 'none';
                document.getElementById('tabExcelBtn').classList.add('active');
                document.getElementById('tabInboxBtn').classList.remove('active');
            } else {
                document.getElementById('excelCard').style.display = 'none';
                document.getElementById('inboxCard').style.display = 'flex';
                document.getElementById('tabExcelBtn').classList.remove('active');
                document.getElementById('tabInboxBtn').classList.add('active');
            }
        }

        async function uploadExcel() {
            const fileInput = document.getElementById('excelFile');
            if (!fileInput.files.length) return;

            const formData = new FormData();
            formData.append('file', fileInput.files[0]);

            try {
                const res = await fetch('/api/parse-excel', {
                    method: 'POST',
                    body: formData
                });
                const data = await res.json();
                if (res.ok) {
                    extractedEmailsList = data.emails.map(e => e.email);
                    document.getElementById('extractedCountLabel').innerText = `✅ Found ${data.total_emails} Recipient Email Addresses in ${data.filename}`;
                    
                    const tbody = document.getElementById('emailTableBody');
                    tbody.innerHTML = data.emails.map(e => `
                        <tr>
                            <td>${e.row}</td>
                            <td>${e.name}</td>
                            <td style="color: var(--primary); font-weight: 600;">${e.email}</td>
                        </tr>
                    `).join('');

                    document.getElementById('previewSection').style.display = 'block';
                    const btn = document.getElementById('sendBulkBtn');
                    btn.disabled = false;
                    document.getElementById('bulkBtnText').innerText = `🚀 Send Campaign to ${data.total_emails} Recipients`;
                } else {
                    alert("Parsing Error: " + data.detail);
                }
            } catch (err) {
                alert("Upload failed: " + err.message);
            }
        }

        async function sendBulkCampaign() {
            if (!extractedEmailsList.length) return alert("Please upload an Excel file first!");

            const sender_email = document.getElementById('activeSenderEmail').value;
            const sender_password = document.getElementById('activeSenderPassword').value;
            const subject = document.getElementById('campaignSubject').value;
            const body = document.getElementById('campaignBody').value;

            if (!sender_email || !sender_password) {
                return alert("Please enter the Sender Email Address and App Password in the top Sender Account Settings box!");
            }

            const btn = document.getElementById('sendBulkBtn');
            const btnText = document.getElementById('bulkBtnText');
            const spinner = document.getElementById('bulkSpinner');
            const logBox = document.getElementById('campaignLogBox');

            btn.disabled = true;
            btnText.innerText = "Broadcasting Emails...";
            spinner.style.display = "block";
            logBox.style.display = "block";
            logBox.innerText = `[START] Sending campaign to ${extractedEmailsList.length} recipients directly from ${sender_email}...\n`;

            try {
                const res = await fetch('/api/send-bulk-dynamic', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ sender_email, sender_password, recipients: extractedEmailsList, subject, body })
                });

                const data = await res.json();
                if (res.ok) {
                    logBox.innerText += `\n[COMPLETED] Successfully sent ${data.sent_count} / ${data.total_recipients} emails!\n\nDelivery Logs:\n`;
                    data.results.forEach(r => {
                        logBox.innerText += ` • ${r.email} ➔ ${r.status.toUpperCase()}\n`;
                    });
                    alert(`🎉 Campaign Complete! Sent ${data.sent_count} emails directly from ${sender_email}!`);
                } else {
                    alert("Sending Failed: " + data.detail);
                }
            } catch (err) {
                alert("Failed to send campaign: " + err.message);
            } finally {
                btn.disabled = false;
                btnText.innerText = `🚀 Send Campaign to ${extractedEmailsList.length} Recipients`;
                spinner.style.display = "none";
            }
        }

        async function processInbox() {
            const sender_email = document.getElementById('activeSenderEmail').value;
            const sender_password = document.getElementById('activeSenderPassword').value;

            if (!sender_email || !sender_password) {
                return alert("Please enter the Sender Email Address and App Password in the top Sender Account Settings box!");
            }

            const btn = document.getElementById('inboxBtn');
            const spinner = document.getElementById('inboxSpinner');
            const btnText = document.getElementById('inboxBtnText');
            const report = document.getElementById('inboxReport');
            const output = document.getElementById('inboxOutput');

            btn.disabled = true;
            spinner.style.display = 'block';
            btnText.innerText = "Checking & Processing Inbox...";

            try {
                const res = await fetch('/api/process-inbox-dynamic', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ sender_email, sender_password })
                });
                const data = await res.json();
                if (res.ok) {
                    output.innerText = data.generated_email || `Processed inbox for ${sender_email}!`;
                    report.style.display = 'block';
                } else {
                    alert("Inbox Error: " + data.detail);
                }
            } catch (err) {
                alert("Error: " + err.message);
            } finally {
                btn.disabled = false;
                spinner.style.display = 'none';
                btnText.innerText = `📬 Check & Process Inbox (${sender_email})`;
            }
        }

        function toggleAutoPoll(checkbox) {
            if (checkbox.checked) {
                processInbox();
                pollInterval = setInterval(processInbox, 60000);
            } else {
                if (pollInterval) clearInterval(pollInterval);
            }
        }
    </script>
</body>
</html>
"""
    return html_content

def main():
    port = int(os.getenv("PORT", 9000))
    uvicorn.run(app, host="0.0.0.0", port=port)

if __name__ == "__main__":
    main()