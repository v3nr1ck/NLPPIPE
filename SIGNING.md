# SIGNING.md — Code Signing & Trust Strategies

> How to distribute the CMMS NLP Pipeline so it doesn't trigger
> security warnings on recipient machines.

---

## The Problem

When you send `.bat` (Windows) or `.command` (Mac) files, the OS flags them
because they could be malware. There are tiers of solutions:

---

## Tier 1: Free — GitHub as Trust Anchor (recommended for demos)

**Strategy:** Don't send files. Send a GitHub link.

```
"Hey — here's the CMMS pipeline demo. Clone or download from:
 https://github.com/v3nr1ck/NLPPIPE

 Then double-click launch.bat (Windows) or launch.command (Mac).
 All source is right there — nothing hidden."
```

**Why this works:**
- Recipients can inspect every line of code before running
- GitHub is a trusted domain
- No OS warnings because they explicitly chose to clone

**What they get:**
```bash
git clone git@github.com:v3nr1ck/NLPPIPE.git
cd NLPPIPE
# Windows: double-click launch.bat
# Mac:     double-click launch.command (right-click → Open first time)
```

---

## Tier 2: Almost Free — Self-Signed + Instructions

### Windows

1. Create a self-signed certificate:
```powershell
$cert = New-SelfSignedCertificate -Type CodeSigning -Subject "CN=CMMS Pipeline Demo" -CertStoreLocation Cert:\CurrentUser\My
```

2. Sign the launcher:
```powershell
Set-AuthenticodeSignature -FilePath launch.bat -Certificate $cert
```

3. Recipient must trust the cert ONCE:
```powershell
# They run this once as admin:
Import-Certificate -FilePath cmms-demo-cert.cer -CertStoreLocation Cert:\CurrentUser\TrustedPublisher
```

**Verdict:** Works but requires recipient action. Not seamless.

### macOS

1. Self-sign:
```bash
codesign --sign - --force --timestamp=none launch.command
```

2. Recipient right-clicks → Open (first time only).

**Verdict:** The "right-click → Open" dance is unavoidable without a paid Apple Developer account.

---

## Tier 3: Paid — Real Code Signing Certificates

| Platform | Provider | Cost (approx) | What You Get |
|---|---|---|---|
| Windows | DigiCert / Sectigo EV Code Signing | $300-500/year | Instant SmartScreen trust |
| macOS | Apple Developer Program | $99/year | `codesign` + notarization |

**For Windows:**
- Buy an EV Code Signing certificate
- Sign `launch.bat` (or better: bundle with PyInstaller into `.exe` and sign that)
- Windows Defender + SmartScreen instantly trust it

**For macOS:**
- Enroll in Apple Developer Program ($99/year)
- Sign with `codesign --sign "Developer ID Application: ..."`
- Notarize with `xcrun notarytool`
- Staple ticket: `xcrun stapler staple`

**Verdict:** Only worth it if you're distributing commercially.

---

## Tier 4: PyInstaller Bundle (best UX, still needs signing for full trust)

Bundle everything into a single executable:

```bash
pip install pyinstaller
pyinstaller --onefile --name "CMMS-Pipeline-Demo" --add-data "control_table.csv:." --add-data "dashboard.py:." --add-data "schemas.py:." --add-data "pipeline.py:." --add-data "pre_processor.py:." --add-data "prompt_builder.py:." --add-data "inference_engine.py:." --add-data "post_processor.py:." --hidden-import streamlit dashboard.py
```

This produces:
- Windows: `dist/CMMS-Pipeline-Demo.exe`
- Mac: `dist/CMMS-Pipeline-Demo.app`

The exe/app still triggers warnings until signed (Tier 3), but it's a single file
which is nicer for recipients.

---

## Integrity Verification (works with any tier)

A `checksums.sha256` file is included in the repo. Recipients can verify:

**Windows:**
```powershell
Get-FileHash -Algorithm SHA256 launch.bat
# Compare with checksums.sha256
```

**Mac:**
```bash
shasum -a 256 -c checksums.sha256
```

This proves the files haven't been tampered with since the maintainer
signed the checksums (via Git commit signature).

---

## Current Recommendation

For demos: **Tier 1** — send the GitHub link. It's the most transparent,
requires zero setup, and the code is right there for inspection.

If you need to email a zip: include `checksums.sha256` and tell recipients
to verify before running. Then it's just the standard "Windows protected your PC"
click-through, which everyone is used to.
