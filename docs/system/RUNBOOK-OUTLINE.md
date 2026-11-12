# CogniSight SSH runbook editorial outline — not deployment instructions

The single draft instruction guide is [PI-RUNBOOK-DRAFT.md](../hardware/PI-RUNBOOK-DRAFT.md). This file is an editorial checklist for that guide, not a second set of instructions. If details differ, reconcile the instruction guide before use. This is the proposed shape of the final simple-English runbook. It has not been executed on a Raspberry Pi. Commands using confirmed existing CLI names below are examples for review; setup/install/GNSS commands will be completed only after the real device details are known and the plans are approved. Never paste passwords, private keys, caregiver records, face data or private logs into chat/Git.

## Details needed before the final guide

Record the Pi OS name/version and whether it is 64-bit; SSH username and hostname/IP; checkout folder; headset name; exact GNSS board, connection and antenna; phone OS; chosen dashboard hostname/IP; Caddy installation/service account. Reported: Raspberry Pi OS 64-bit; the Imager 64-bit selection is not installed-release/runtime proof. SSH username `jahnvi`; hostname `cognisight`. Actual OS release/runtime architecture and IP remain unknown. Primary SSH address is `jahnvi@cognisight.local` if mDNS resolves; `PI_IP` is the explicit fallback placeholder. GNSS pin/baud/device command, phone CA procedure and existing filesystem paths are not assumed.

Candidate supported software baseline is Raspberry Pi OS Bookworm 64-bit / Python 3.11, pending compatibility checks. An existing different OS must be inspected before proposing changes. Do not reinstall the Pi or erase its state to follow a guide.

## 1. Connect from your laptop

**On laptop:** explain how to open Terminal and what to replace in `ssh jahnvi@cognisight.local`. Explain that `.local` uses local hostname discovery (mDNS). If it does not resolve, use `ssh jahnvi@PI_IP` after replacing `PI_IP` with the Pi’s real address from the router/device, not a guessed IP. Explain the first host-key prompt and require matching the Pi's trusted host-key fingerprint before accepting. Type the password only into SSH when prompted; it may not show characters. A prompt naming the Pi means connection succeeded. If connection fails, check power, same Wi-Fi, address and SSH enabled; do not repeatedly guess passwords.

**On Pi after SSH:** use read-only checks such as `cat /etc/os-release`, `uname -m`, `python3 --version` and `pwd`. Expected result: known OS, architecture, Python version and current folder. Record differences and stop before package changes if unsupported.

## 2. Put the approved local code on the Pi

Explain that current work is local and has not been pushed. Use a Git archive of the approved local committed tree on the laptop, then `scp` it to the Pi. The instruction guide supplies concrete `git archive` and `scp` commands and the expected archive/destination. Keep this outline aligned with the actual guide; do not promise extra verification commands that have not been supplied and checked. Do not tell the user to pull GitHub main: remote main is older and these local commits have not been pushed. Archives exclude `.git` and untracked private files; confirm needed tracked model/config examples are present, while private state stays outside the archive. Preserve current Pi code/private state before updating and never copy patient data into the repository. Give exact laptop source and Pi destination after those paths are confirmed. Show one `cd` command using the real checkout path, and explain that it changes folders. Check expected source/config/example files before installing.

## 3. Install the verified software environment

**On Pi:** give OS-specific package and venv commands only after inspecting actual OS. Explain apt supplies the camera/libcamera stack and the venv supplies app packages; verify system-package visibility, Python version and compatible NumPy/OpenCV ABI. Select one OpenCV build compatible with recognition. Do not install overlapping cv2 packages. Explain each command, expected completion, and how to stop on error. Lock exact working apt/pip versions and asset hashes after validation; do not treat current broad ranges as qualification.

The model preparation step explicitly downloads permitted assets before offline use, verifies checksums and records licenses. Runtime does not download. Include existing model tooling only after checking its exact CLI. Do not guess receiver vendor utilities or install unrelated cloud software.

## 4. Make private settings and verify the AUX audio path

Owned audio is AUX earphones/headset, not USB. Existing software requires a USB sound adapter that is not yet selected/owned; verify output compatibility, whether the headset has a microphone, and any TRRS/CTIA requirements before purchase/setup. Do not promise voice commands without a verified microphone path. The guide must mark audio setup as pending until that hardware works. Create the approved private state/config location outside the checkout with restrictive permissions. Preserve any existing profiles/history/config and back them up privately before edits. Explain how to copy the provided configuration example, replace exact model paths and unique USB input/output names, and keep allowed hosts consistent. Use `.venv/bin/cognisight devices` on Pi to list actual headset routes; expected result is one unambiguous chosen USB input and output, with no default-speaker fallback.

Run `.venv/bin/cognisight password --state-dir PRIVATE_STATE_PATH` interactively, replacing the path. Tell the user the password is entered locally and is not sent to the assistant. State directory and `run` configuration must match. Do not put the password in the shell command or guide. Run `.venv/bin/cognisight doctor`; its result reports dependencies and explicitly does not certify the hardware.

## 5. Configure GNSS only after identifying the board

The reported board is “SIMA7670C MODULE WITH RS232”; positioning/GNSS capability is unverified and may be a modem board. Keep `navigation.enabled=false` and GPSD setup disabled until exact board/manual capability and compatible positioning output are verified. Give a board-specific approved setup section only after that check. Identify actual device path and permissions, local GPSD settings and antenna requirements. Never guess UART pins, voltage, baud rate, modem AT commands or device names. Keep GPSD loopback-only. Explain that first fix may need an appropriate outdoor location; unavailable/no-fix is honest status. Verified complete TPV fixes and separate historical last-known data are required; no walking directions are promised.

## 6. Start once in the foreground

**On Pi:** provide `.venv/bin/cognisight run --config PRIVATE_CONFIG_PATH` using the confirmed path. Expected result: local enrollment URL on localhost8765 and, if enabled, dashboard backend on localhost8766; modules report real readiness or a named unavailable state. Explain that Ctrl+C stops this foreground run. If it says another service is running, inspect/stop the known service instead of starting a second camera process or deleting locks blindly.

For local enrollment, either use the Pi's local browser or an explicitly documented laptop SSH tunnel to loopback8765. Give the exact tunnel only after SSH details are known; keep it laptop loopback-bound. No phone/reverse-proxy enrollment. Enroll only consented verified profiles, calibrate under the existing recognition guide, and keep personal records out of screenshots shared for help.

## 7. Set up the caregiver phone HTTPS address

**On Pi:** fill the Caddy example with the actual chosen host/IP, validate with the actual installed Caddy command/config path, and verify the proxy points only to localhost8766. Explain matching hostname among Caddy, allowed hosts and phone URL. Keep enrollment8765 and GPSD private. No router port forwarding.

Find Caddy's actual public root CA from its service account/environment. Compare its SHA-256 fingerprint through a trusted channel. Transfer only the public root certificate to the phone; never transfer CA private keys. **On phone:** provide the exact trust-store steps for the confirmed iOS/Android version. Stop on a browser certificate warning and fix trust/name/date rather than bypassing it. Open `https://CHOSEN_HOST/dashboard` on the same Wi-Fi, sign in and confirm the source statuses. Guest Wi-Fi client isolation and changing IP addresses may prevent access; explain checks in plain words.

## 8. Make it start as a service

After the foreground check passes, install the approved user systemd unit using exact checkout/config/interpreter paths; explain laptop versus Pi commands clearly. Verify camera/audio/receiver permissions for that user instead of granting broad access. Check the service deadline against coordinator shutdown behavior. Only then enable/start the unit and inspect status. State whether login persistence/lingering is needed for the intended boot behavior after inspecting the actual user session; do not assume it.

Final guide includes exact commands for `systemctl --user status cognisight`, `stop`, `start`, `restart`, and sanitized bounded `journalctl --user -u cognisight` output as appropriate to the installed unit name. Explain expected `active (running)` and that it means the process is running, not every module is qualified. Caddy/GPSD are separate services; include their real names/accounts only after inspection.

## 9. Check the system together

Separate software checks from physical tests. Confirm one camera owner and exact sensor/cable compatibility (PCB V2.0 label/free 22-contact end are insufficient), calibrated recognition, English commands only with verified microphone, audio through the selected USB adapter to AUX earphones, stop behavior, and genuine outdoor fix only if hardware qualification enables it, phone trusted HTTPS/login/logout/expiry, source expiry and reconnection. The user has deferred the entire indoor module (#5); indoor must say not integrated. Do not install markers, maps, route commands or indoor camera workers.

Phone polls while connected every 500 ms and retries failed fetches after 5 s. The displayed source age must increase even if the source freezes; a successful fetch cannot make an old location/person current. Check stale/no-fix/disconnected states honestly. Measure native stop delay, recognition behavior, combined resource/thermal use and longer-run stability under #7/#8; record actual results instead of calling every process launch a pass.

## 10. If something fails

Give one symptom → one check → expected result → next action at a time: SSH unreachable; dependency missing; camera busy/disconnected; wrong headset; GPSD no-fix; hostname not reachable; TLS untrusted; session ended; stale module; service failed to stop. Ask for sanitized state/error codes, not private data. Use confirmed service stop/start commands; do not delete profiles, change permission modes broadly, disable certificate checks or expose localhost backends to fix errors.

Recovery preserves the private state/config/model manifest and uses a verified previous code/environment version. Never run two app services or swap native libraries beneath a running process. On a stuck native worker stop the known service and verify process exit before restarting. If rollback would require a schema/data migration, stop and use the approved restore procedure with the private backup.

Final acceptance list records which checks were actually performed, on what hardware/OS/package versions, and which remain pending. Include the real approved commit identifier and local transfer version. No remote push/PR merge/issue closure is implied by this outline.
