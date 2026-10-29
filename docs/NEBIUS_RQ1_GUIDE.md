# Nebius setup and payment guide for RQ1

Checked against official documentation on 29 October 2026. Prices and availability must be checked again in your own console before creating a VM.

**Current checkpoint: prepare the account, SSH key and VM configuration; pause at the VM review screen before clicking Create.** Later sections are a reference for subsequent checkpoints, not an instruction to run the whole experiment now.

## 1. The configuration to use

Use one standalone Compute VM for Q generation. Our prepared runtime uses one GPU. Joern, slicing, assessment preparation and reporting stay on your laptop.

| Setting | Selection |
|---|---|
| Product | Compute → Virtual machines → standalone VM |
| Name | rq1-q-development |
| Billing | Pay-as-you-go, regular/on-demand |
| Region | eu-north1, Finland |
| Platform | NVIDIA H100 NVLink, gpu-h100-sxm |
| Preset | 1gpu-16vcpu-200gb |
| GPU memory | One 80 GB GPU |
| CPU / host memory | 16 vCPUs / 200 GiB RAM |
| Boot image | Ubuntu 24.04 for NVIDIA GPUs, stable CUDA 13.0 family ubuntu24.04-cuda13.0 |
| Boot disk | 250 GiB, ordinary Network SSD |
| Additional volumes | None for the first run |
| Network | Public IPv4 for SSH; use the existing/default network and subnet if available |
| SSH username | rq1 |
| GPU cluster / InfiniBand | Leave unselected |
| Software on GPU VM | Pinned Q inference environment |
| Local laptop storage | Existing D:\Dissertation-RQ1 layout |

The H100 preset and its Finland availability are documented in [platforms and presets](https://docs.nebius.com/compute/virtual-machines/types). The GPU image is Nebius's current recommended stable H100 image; see [boot images](https://docs.nebius.com/compute/storage/boot-disk-images). Our Python environment remains Python 3.11, independently of Ubuntu's system Python.

The 250 GiB disk is my sizing recommendation: it leaves room for CUDA/system files, the Python environment, the approximately 65.5 GB Q checkpoint and the readiness check's free-space allowance. GPU VM storage is a separately charged cloud disk; laptop downloads and returned results still belong on D:.

Choose H100 to stay close to the prepared older vLLM/PyTorch configuration. If H100 is unavailable, pause and return the available options. A single H200 is a possible fallback to review; changing GPU generations or software versions needs a compatibility check. Live capacity is not guaranteed by the public catalogue.

## 2. Create the account and check availability

1. Open https://console.nebius.com and sign up with Google, GitHub or Microsoft.
2. Enter your contact details. Nebius creates a tenant and project during signup.
3. Use a dedicated project named rq1-dissertation if the console lets you create/rename it.
4. Inspect the H100 option in eu-north1 and the project quotas before funding, if the console permits this.
5. Open Administration → Limits → Quotas. Check that Compute allows at least one H100 and the selected CPU/RAM/disk resources. If necessary, request a quota change for one GPU. A quota is permission to allocate resources, not a capacity reservation.

Sources: [signup](https://docs.nebius.com/signup-billing/sign-up), [quotas](https://docs.nebius.com/overview/quotas). If regular H100 is unavailable or the console requires a capacity commitment, stop and return that screen. We have not selected a long-term commitment or an eight-GPU machine.

## 3. Payment: what happens and what to budget

### Card setup

If you pay personally, choose Individual in Billing, enter your actual country of residence and billing address, and add your card directly in Nebius's payment form. Use institutional/company details only if that organisation is actually paying.

The documented first card payment is **$25**, credited to your PAYG balance. Manual top-ups have the same minimum. Payments are processed through Stripe. Inspect the displayed amount, currency and taxes before saving billing details. [Card payments](https://docs.nebius.com/signup-billing/payments/card)

Individuals use the card route; bank transfers are available to companies. Enter payment details only in Nebius's payment form, rather than sharing them in chat.

**The initial balance is not a spending cap.** Usage can create a negative balance. Nebius can then automatically charge the card at the monthly billing point or a billing threshold; that threshold depends on the account. Do not rely on the balance reaching zero to stop a VM. [PAYG](https://docs.nebius.com/signup-billing/billing-models/payg), [billing threshold](https://docs.nebius.com/signup-billing/payments/threshold)

### Taxes, currency and receipts

The illustrations below use published USD rates. Confirm your billing account's actual currency and your card issuer's GBP conversion and foreign-transaction fees.

Nebius lists VAT as applicable to UK individuals. The UK standard rate is 20%; check the tax actually displayed on your checkout/invoice. This guide does not assume that being a student provides a tax exemption. [Nebius taxes](https://docs.nebius.com/signup-billing/payments/taxes), [UK VAT rates](https://www.gov.uk/vat-rates)

Download PDF invoices from Billing → Payments → Documents and retain them with your experiment expense records. PAYG invoices cover monthly usage and can arrive in the following month. Keep receipts separately from research packets. [Invoices](https://docs.nebius.com/signup-billing/payments/invoices)

If you already have a promo code, the documented flow is to add the card/initial credit first, then use Billing → Apply promo code. Check its expiry and credited balance; it does not settle an already outstanding invoice. No promotional credit is assumed in this plan. [Promo codes](https://docs.nebius.com/signup-billing/payments/promo-codes)

### Cost illustrations

The published H100 on-demand rate is **$4.50 per GPU-hour**, checked today. These are examples of paid VM uptime, including installation, downloads and idle time; they are not predictions of experiment runtime.

Compute usage is billed by the second, with prices displayed per hour.

| Running time, one H100 | Compute before tax | Compute with illustrative 20% VAT |
|---|---:|---:|
| 1 hour | $4.50 | $5.40 |
| 2 hours | $9.00 | $10.80 |
| 4 hours | $18.00 | $21.60 |
| 6 hours | $27.00 | $32.40 |

Ordinary Network SSD is listed at $0.071 per GiB per 730 hours. A 250 GiB disk therefore costs $17.75 per 730 hours, approximately $0.58 per day before tax, including days when the VM is stopped. The final console estimate must include the disk and the actual preset. Sources: [public prices](https://nebius.com/prices), [Compute billing and storage prices](https://docs.nebius.com/compute/resources/pricing).

For planning, review progress within the first two hours of paid VM uptime. Start with the documented $25 credit if that amount is acceptable to you; the total needed will depend on measured runtime and any debugging. A $50 planning allowance would provide headroom, but is neither a price guarantee nor an authorisation to spend it.

### Set alerts before creating the VM

In Billing → Budgets, create an All usage daily budget of $10, with alerts at $5 and $10, and select your own email as recipient. Optionally add a monthly budget matching the amount you are comfortable spending.

**Budgets only alert; they do not cap spending or stop resources.** Their amounts exclude VAT, and updates can lag by hours. Daily/monthly periods reset on the UTC calendar; our October–November work crosses a monthly reset. Track cumulative experiment spending separately. Monitor elapsed VM uptime during the first session instead of waiting for an email. [Budgets](https://docs.nebius.com/signup-billing/budgets)

## 4. Create the SSH key on your laptop

Run only in your D-backed Ubuntu-24.04 terminal:

~~~bash
mkdir -p ~/.ssh
chmod 700 ~/.ssh
if [[ -e ~/.ssh/nebius_rq1 || -e ~/.ssh/nebius_rq1.pub ]]; then
    printf '%s\n' 'An experiment key already exists; retaining it.'
else
    ssh-keygen -t ed25519 -a 64 -f ~/.ssh/nebius_rq1 -C rq1-nebius
fi
cat ~/.ssh/nebius_rq1.pub
~~~

Enter a passphrase known only to you when prompted. Copy the public key ending in .pub into the VM configuration. The matching file without .pub is the private key and stays on your laptop.

## 5. Configure the VM and pause before purchase

1. In Compute → Virtual machines, start Create resource → Virtual machine.
2. Select the regular/on-demand H100 platform, one-GPU preset and eu-north1 project.
3. In Storage, set the stable GPU image and 250 GiB ordinary Network SSD boot disk. Review whether the disk is VM-managed or standalone and whether deletion of the VM also deletes it.
4. In Network, select the network/subnet and assign a public IPv4. If security-group settings are offered, restrict inbound TCP 22 to your current public IP; Q generation needs outbound internet access.
5. In Configuration → Access, create username rq1 and paste the public SSH key. Leave extra service accounts and custom startup scripts unused for this first VM.
6. Reach the review/price screen. Confirm one GPU, the disk size/type, regular billing, image, region and total estimated price.

**Pause here.** Return a screenshot of the configuration/price summary and state your intended spending allowance. Hide payment information. Do not send card numbers, authentication codes or the private SSH key.

These steps follow the [VM creation wizard](https://docs.nebius.com/compute/virtual-machines/create). The remaining sections are for later, after this checkpoint is reviewed.

## 6. Later: launch and inspect the VM

When ready to start the paid session, create the VM and wait for Running. Record the VM ID, disk ID, region, image and displayed hourly estimate.

On the laptop, substitute the actual public IP:

~~~bash
rq1_ip=REPLACE_WITH_VM_PUBLIC_IP
ssh -i ~/.ssh/nebius_rq1 "rq1@$rq1_ip"
~~~

Confirm the host key using the console's SSH information where available. On the VM run:

~~~bash
cloud-init status --wait
nvidia-smi
free -h
df -h /
cat /etc/os-release
~~~

**Pause and return that output before installing the inference environment.** Expected: one H100 with approximately 80 GB VRAM, the chosen OS, and ample disk space. Unexpected GPU, driver errors or a smaller disk should be investigated first.

Use Nebius's console Stop action if waiting for a lengthy review, then verify Stopped. On restart, read the VM's current public IP again. A dynamic address can change.

## 7. Later: prepare Python and copy the verified inputs

The validated experiment source is pinned to commit 81a7a8a7543a8c5bc9fab4ffc759b9e9f202b643. This guide is stored separately from the hashed RQ1 corpus; adding it does not invalidate the accepted token audit.

On the VM, after the hardware checkpoint:

~~~bash
sudo apt-get update
sudo apt-get install -y git curl ca-certificates libgomp1 tmux
curl -LsSf https://astral.sh/uv/0.13.6/install.sh -o /tmp/rq1-uv-install.sh
sh /tmp/rq1-uv-install.sh
"$HOME/.local/bin/uv" python install 3.11
git clone --branch codex/rq1-execution https://github.com/TheArchiviste/MSc-Thesis-Project.git ~/rq1-project
cd ~/rq1-project
git checkout --detach 81a7a8a7543a8c5bc9fab4ffc759b9e9f202b643
"$HOME/.local/bin/uv" venv --python 3.11 --seed .venv-q
.venv-q/bin/python -m pip install --no-cache-dir -r rq1/requirements-gpu.txt
.venv-q/bin/python -m pip install --no-cache-dir --no-deps -e .
.venv-q/bin/python -m pip check
mkdir -p ~/rq1-storage/huggingface work/rq1/development
~~~

Stop at the first failed command and retain its output. This installs the already prepared candidate GPU package versions; it has not yet been validated on rented hardware. The official [uv installation](https://docs.astral.sh/uv/getting-started/installation/) and [Python installation](https://docs.astral.sh/uv/guides/install-python/) guides document managed Python installation.

In a separate laptop Ubuntu terminal:

~~~bash
cd ~/projects/MSc-Thesis-Project
tar -czf /mnt/d/Dissertation-RQ1/exports/rq1-nebius-inputs.tgz \
    work/rq1-config.json \
    work/rq1-token-audit.json \
    work/rq1/development/witness_validation.jsonl
rq1_ip=REPLACE_WITH_CURRENT_VM_PUBLIC_IP
scp -i ~/.ssh/nebius_rq1 /mnt/d/Dissertation-RQ1/exports/rq1-nebius-inputs.tgz "rq1@$rq1_ip:/home/rq1/"
~~~

This transfers the laptop's actual configuration, audit and witness records. Do not substitute the checked-in workspace witness logs.

Back on the fresh VM checkout:

~~~bash
cd ~/rq1-project
tar -tzf ~/rq1-nebius-inputs.tgz
tar -xzf ~/rq1-nebius-inputs.tgz
export HF_HOME="$HOME/rq1-storage/huggingface"
.venv-q/bin/python -m pip freeze > work/rq1/gpu-pip-freeze.txt
nvidia-smi > work/rq1/gpu-nvidia-smi.txt
.venv-q/bin/python -m rq1.setup doctor --profile gpu --work work/rq1/gpu-readiness
~~~

**Pause before loading Q.** Return the readiness report and diagnostic output; stop the VM in the console during a long wait. This gate checks CUDA/BF16, memory, packages, the source pin and configuration. It does not prove that Q can load. Model weights have not been deliberately downloaded by these setup commands.

## 8. Later: six development queries, export and stop

Only after the GPU readiness checkpoint is accepted, use tmux so an SSH disconnect does not kill the command:

~~~bash
tmux new -s rq1-dev
~~~

Inside tmux on the VM:

~~~bash
cd ~/rq1-project
export HF_HOME="$HOME/rq1-storage/huggingface"
set -o pipefail
.venv-q/bin/python -m evidence_experiment query --manifest rq1/development.jsonl --config work/rq1-config.json --work work/rq1/development --repeats 1 2>&1 | tee work/rq1/development/query-command.log
~~~

This is the first command that loads the original Q weights, downloading them to the cloud disk if absent. Expected collection: six terminal Q records for three U/F pairs. Model load/OOM errors require diagnosis; malformed model output is retained, rather than regenerated to obtain a preferred answer.

After the command finishes, including a failed or partial run, retain the complete directory. Prepare the return archive:

~~~bash
cd ~/rq1-project
tar -czf ~/rq1-development-return.tgz \
    work/rq1/development \
    work/rq1/gpu-readiness \
    work/rq1/gpu-pip-freeze.txt \
    work/rq1/gpu-nvidia-smi.txt \
    work/rq1-config.json \
    work/rq1-token-audit.json
~~~

Download from the laptop:

~~~bash
rq1_ip=REPLACE_WITH_CURRENT_VM_PUBLIC_IP
scp -i ~/.ssh/nebius_rq1 "rq1@$rq1_ip:/home/rq1/rq1-development-return.tgz" /mnt/d/Dissertation-RQ1/exports/
tar -tzf /mnt/d/Dissertation-RQ1/exports/rq1-development-return.tgz
~~~

Once the download succeeds, **stop the VM in the Nebius console and verify Stopped** before returning the archive for inspection. Do not leave the GPU running during local slicing or AI-assisted assessment.

Development results are then sliced on the laptop, assessed and checked before the pre-main freeze. Main Q generation is a separate checkpoint for 24 inputs. It must use the accepted environment and frozen configuration; do not run it immediately after development.

## 9. How to stop charges and close the project

- A finished Python process, closed SSH session or closed browser does not stop a running VM.
- Use Compute → Virtual machines → your VM → Stop, then check its status is Stopped. Avoid Linux shutdown/poweroff: Nebius documents that guest shutdown can trigger recovery and continued billing.
- Stopping ends compute charges, while the retained disk continues to accrue storage charges.
- Between development and main, retaining the stopped VM/disk preserves the environment and Q cache. Confirm this modest storage cost is acceptable.
- After final outputs are copied to D: and verified, delete the VM when it is no longer needed. VM-managed disks are deleted with it; standalone disks/filesystems may remain and must be checked separately. Review Disks, Snapshots, any separately created services and Billing → Usage for leftovers.
- Keep the source commit, configs, complete raw outputs, package/GPU metadata and invoice records before deleting cloud storage. Confirm any outstanding balance and later invoice in Billing; closing the browser or deleting a local SSH key does not settle usage.

Sources: [proper VM stop/start](https://docs.nebius.com/compute/virtual-machines/stop-start), [VM deletion and disk ownership](https://docs.nebius.com/compute/virtual-machines/delete), [PAYG charges](https://docs.nebius.com/signup-billing/billing-models/payg).

No Nebius resource, payment or reservation has been created by the assistant. For now, stop at the VM configuration/price review checkpoint in section 5.
